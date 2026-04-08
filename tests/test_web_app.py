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
        """GET /api/history 返回列表"""
        app = create_app()
        client = app.test_client()
        resp = client.get("/api/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

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
