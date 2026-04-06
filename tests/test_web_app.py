"""Tests for web app"""
import pytest
from web.app import create_app


def test_status_endpoint():
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "monitor_enabled" in data


def test_rates_endpoint_no_monitor():
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/rates")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_config_endpoint_no_config():
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/config")
    assert resp.status_code == 200


def test_dashboard_page():
    app = create_app()
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
