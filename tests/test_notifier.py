"""
Tests for Lark Notifier.
"""
import pytest
from unittest.mock import MagicMock, patch
from notifier import Notifier
from strategy import ArbitrageOpportunity
from executor import OrderResult


def make_opp(**kwargs):
    defaults = dict(
        symbol="BTC-USDT",
        high_exchange="bybit",
        low_exchange="binance",
        high_rate=0.0003,
        low_rate=0.0001,
        rate_diff_percent=0.02,
        estimated_profit=0,
        side_a="BUY",
        side_b="SELL",
        next_settlement=1700000000,
    )
    defaults.update(kwargs)
    return ArbitrageOpportunity(**defaults)


def make_result(**kwargs):
    defaults = dict(status="filled")
    defaults.update(kwargs)
    return OrderResult(**defaults)


class TestNotifierSend:
    def test_send_success_returns_true(self):
        """发送成功返回 True"""
        with patch("httpx.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            notifier = Notifier(webhook="http://test", detail_level="detailed")
            result = notifier.send("test message")
            assert result is True
            mock_post.assert_called_once()

    def test_send_empty_webhook_returns_false(self):
        """空 webhook 不发送，返回 False"""
        notifier = Notifier(webhook="", detail_level="detailed")
        result = notifier.send("test message")
        assert result is False

    def test_send_failure_returns_false(self):
        """发送失败返回 False"""
        with patch("httpx.post", side_effect=Exception("network error")):
            notifier = Notifier(webhook="http://test", detail_level="detailed")
            result = notifier.send("test message")
            assert result is False


class TestNotifierBuildMessage:
    def test_detailed_message_contains_all_fields(self):
        """详细模式消息包含所有关键字段"""
        notifier = Notifier(webhook="http://test", detail_level="detailed")
        msg = notifier._build_message(
            symbol="BTC-USDT",
            high_ex="bybit",
            low_ex="binance",
            rate_diff=0.02,
            result=make_result(status="filled", order_a_id="123", order_b_id="456"),
        )
        assert "BTC-USDT" in msg
        assert "bybit" in msg
        assert "binance" in msg
        assert "0.0200" in msg or "0.02" in msg
        assert "filled" in msg

    def test_partial_fill_message_contains_error(self):
        """部分成交消息包含错误信息"""
        notifier = Notifier(webhook="http://test", detail_level="detailed")
        msg = notifier._build_message(
            symbol="ETH-USDT",
            high_ex="mexc",
            low_ex="binance",
            rate_diff=0.015,
            result=make_result(status="partial_fill", error_a="status=unfilled"),
        )
        assert "ETH-USDT" in msg
        assert "partial_fill" in msg.lower()

    def test_summary_message_short(self):
        """摘要模式消息简洁"""
        notifier = Notifier(webhook="http://test", detail_level="summary")
        msg = notifier._build_message(
            symbol="BTC-USDT",
            high_ex="bybit",
            low_ex="binance",
            rate_diff=0.02,
            result=make_result(status="filled"),
        )
        # 摘要模式不包含详情
        assert "BTC-USDT" in msg
        assert "bybit" in msg


class TestNotifierSendArbitrageResult:
    def test_sends_result_notification(self):
        """发送套利结果通知"""
        with patch("httpx.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            notifier = Notifier(webhook="http://test", detail_level="detailed")
            opp = make_opp()
            result = make_result(status="filled")
            notifier.send_arbitrage_result(opp, result)
            mock_post.assert_called_once()
