"""
Tests for Flask Web App.
"""
import pytest
import tempfile
import os
from web.app import create_app


class TestWebAppRoutes:
    def test_status_endpoint_returns_json(self):
        """GET /api/status 返回 JSON"""
        app = create_app()
        client = app.test_client()
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "monitor_enabled" in data

    def test_rates_endpoint_returns_list(self):
        """GET /api/rates 返回列表"""
        app = create_app()
        client = app.test_client()
        resp = client.get("/api/rates")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_positions_endpoint_returns_list(self):
        """GET /api/positions 返回列表"""
        app = create_app()
        client = app.test_client()
        resp = client.get("/api/positions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_history_endpoint_returns_list(self):
        """GET /api/history 返回分页字典"""
        app = create_app()
        client = app.test_client()
        resp = client.get("/api/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        assert "items" in data
        assert "total" in data

    def test_config_endpoint_returns_dict(self):
        """GET /api/config 返回配置字典"""
        app = create_app()
        client = app.test_client()
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)

    def test_status_endpoint_works(self):
        """状态端点正常工作"""
        app = create_app()
        client = app.test_client()
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "monitor_enabled" in data


class TestWebAppWithMockMonitor:
    def test_status_with_monitor_ref(self):
        """有 monitor_ref 时 status 返回更多字段"""
        mock_monitor = MockMonitor()
        app = create_app(monitor_ref=mock_monitor)
        client = app.test_client()
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "monitor_enabled" in data
        assert "next_settlement" in data


class MockMonitor:
    """Minimal mock for MonitorLoop."""
    def get_next_settlement(self):
        return None
    def get_positions(self):
        return {}
    def get_current_rates(self):
        return {}


class TestConfigValidation:
    """Regression: ISSUE-002 config corruption prevention."""

    def _make_app_with_config(self):
        """Create app with a real Config backed by a temp file."""
        import yaml
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        )
        yaml.dump(
            {"monitor": {"enabled": True}, "strategy": {"min_rate_diff": 0.01}, "notification": {}},
            tmp,
        )
        tmp.close()
        from config import Config
        cfg = Config(tmp.name)
        app = create_app(config_ref=cfg)
        app._tmp_config_path = tmp.name
        return app

    def teardown_method(self, method):
        if hasattr(self, "_app") and hasattr(self._app, "_tmp_config_path"):
            os.unlink(self._app._tmp_config_path)

    def test_rejects_unknown_config_key(self):
        """POST /api/config rejects keys outside allowed set."""
        self._app = self._make_app_with_config()
        client = self._app.test_client()
        resp = client.post(
            "/api/config",
            json={"_config_path": "/tmp/evil"},
        )
        assert resp.status_code == 400
        assert "unknown config key" in resp.get_json()["error"]

    def test_rejects_non_dict_value(self):
        """POST /api/config rejects non-dict values for known keys."""
        self._app = self._make_app_with_config()
        client = self._app.test_client()
        resp = client.post(
            "/api/config",
            json={"strategy": "corrupt"},
        )
        assert resp.status_code == 400
        assert "must be an object" in resp.get_json()["error"]

    def test_accepts_valid_config_update(self):
        """POST /api/config accepts well-formed updates."""
        self._app = self._make_app_with_config()
        client = self._app.test_client()
        resp = client.post(
            "/api/config",
            json={"strategy": {"min_rate_diff": 0.05}},
        )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"


class TestHistoryLimitValidation:
    """Regression: ISSUE-007 history limit parameter."""

    def test_history_with_none_limit_defaults_to_100(self):
        """GET /api/history?limit=abc returns 200 with default limit."""
        app = create_app()
        client = app.test_client()
        resp = client.get("/api/history?limit=abc")
        assert resp.status_code == 200

    def test_history_with_negative_limit_defaults_to_100(self):
        """GET /api/history?limit=-1 returns 200 with default limit."""
        app = create_app()
        client = app.test_client()
        resp = client.get("/api/history?limit=-1")
        assert resp.status_code == 200


class TestSecurityHeaders:
    """Regression: ISSUE-006 security headers."""

    def test_response_has_security_headers(self):
        app = create_app()
        client = app.test_client()
        resp = client.get("/")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
