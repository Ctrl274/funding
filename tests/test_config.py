import pytest
from config import Config


def test_load_config():
    cfg = Config("tests/fixtures/valid_config.yaml")
    assert cfg.exchanges["binance"].enabled == True
    assert cfg.exchanges["binance"].api_key == "testkey"
    assert cfg.strategy.min_rate_diff == 0.01
    assert cfg.monitor.polling_interval == 60


def test_get_enabled_exchanges():
    cfg = Config("tests/fixtures/valid_config.yaml")
    enabled = cfg.get_enabled_exchanges()
    assert "binance" in enabled
    assert "bybit" in enabled
    assert "bydfi" in enabled
    assert "mexc" in enabled
    assert len(enabled) == 4


def test_strategy_config():
    cfg = Config("tests/fixtures/valid_config.yaml")
    s = cfg.strategy
    assert s.position_mode == "fixed"
    assert s.position_value == 1000
    assert s.max_concurrent == 3


def test_notification_config():
    cfg = Config("tests/fixtures/valid_config.yaml")
    n = cfg.notification
    assert n.enabled == True
    assert n.lark_webhook == "https://test.com"
    assert n.detail_level == "detailed"
