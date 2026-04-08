"""
Tests for Monitor Loop.
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from monitor import MonitorLoop


class TestIsWithinTimeWindow:
    def test_empty_time_windows_returns_true(self):
        """空 time_windows -> 24h 全天候"""
        ml = MonitorLoop.__new__(MonitorLoop)
        ml._config = MagicMock()
        ml._config.monitor.time_windows = []
        assert ml._is_within_time_window() is True

    def test_parse_time_window(self):
        """时间窗口解析正确"""
        ml = MonitorLoop.__new__(MonitorLoop)
        ml._config = MagicMock()
        # 测试正常的窗口解析
        # "08:00-08:30" -> (8.0, 8.5)
        start, end = ml._parse_time_window("08:00-08:30")
        assert start == 8.0
        assert end == 8.5


class TestNextSettlement:
    def test_next_settlement_returns_utc_hour(self):
        """下次结算返回未来最近的 UTC 结算时间"""
        import time
        from exchanges.base import FundingRate
        ml = MonitorLoop.__new__(MonitorLoop)
        future_ts = int(time.time()) + 3600
        all_rates = {
            "binance": {
                "BTC-USDT": FundingRate(symbol="BTC-USDT", rate=0.0001, next_settlement=future_ts),
            }
        }
        result = ml._get_next_settlement_from_rates(all_rates)
        assert result is not None
        # Verify it returns the exact timestamp we provided
        assert int(result.timestamp()) == future_ts
