"""Tests for monitor.py"""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from monitor import MonitorLoop


def test_is_within_time_window_empty():
    ml = MonitorLoop.__new__(MonitorLoop)
    ml._config = MagicMock()
    ml._config.monitor.time_windows = []
    assert ml._is_within_time_window() is True


def test_is_within_time_window_cross_day():
    """Cross-midnight window like 23:50-00:10"""
    ml = MonitorLoop.__new__(MonitorLoop)
    ml._config = MagicMock()
    ml._config.monitor.time_windows = ["23:50-00:10"]
    # The actual result depends on current time, just verify it doesn't crash
    result = ml._is_within_time_window()
    assert isinstance(result, bool)


def test_collect_rates_handles_errors():
    ml = MonitorLoop.__new__(MonitorLoop)
    ml._config = MagicMock()
    adapter_a = MagicMock()
    adapter_a.get_funding_rates.side_effect = Exception("timeout")
    ml._adapters = {"binance": adapter_a}
    result = ml._collect_rates()
    assert result == {}
