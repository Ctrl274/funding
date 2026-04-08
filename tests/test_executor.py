"""
Tests for Execution Engine.
"""
import pytest
from unittest.mock import MagicMock
from executor import ExecutionEngine, OrderResult


def make_mock_adapter(name):
    adapter = MagicMock()
    adapter.NAME = name
    return adapter


class TestExecuteArbitrage:
    def test_both_orders_filled(self):
        """两边 FOK 订单都成交 -> status=filled"""
        adapter_a = make_mock_adapter("binance")
        adapter_a.place_fok_order.return_value = "order_a"
        adapter_a.get_order_status.return_value = "filled"

        adapter_b = make_mock_adapter("bybit")
        adapter_b.place_fok_order.return_value = "order_b"
        adapter_b.get_order_status.return_value = "filled"

        engine = ExecutionEngine(timeout=5, poll_interval=0.01)
        result = engine.execute_arbitrage(
            symbol="BTC-USDT",
            adapter_a=adapter_a,
            adapter_b=adapter_b,
            side_a="BUY",
            side_b="SELL",
            quantity=1,
            price_a=50000,
            price_b=50001,
        )

        assert result.status == "filled"
        assert result.order_a_id == "order_a"
        assert result.order_b_id == "order_b"
        assert result.fill_price_a == 50000
        assert result.fill_price_b == 50001

    def test_order_a_submit_failed_cancels_b(self):
        """A 下单失败 -> 取消 B，返回 failed"""
        adapter_a = make_mock_adapter("binance")
        adapter_a.place_fok_order.return_value = None

        adapter_b = make_mock_adapter("bybit")
        adapter_b.place_fok_order.return_value = "order_b"

        engine = ExecutionEngine(timeout=5, poll_interval=0.01)
        result = engine.execute_arbitrage(
            symbol="BTC-USDT",
            adapter_a=adapter_a,
            adapter_b=adapter_b,
            side_a="BUY",
            side_b="SELL",
            quantity=1,
            price_a=50000,
            price_b=50001,
        )

        assert result.status == "failed"
        assert result.error_a == "order_a_submit_failed"
        adapter_b.cancel_order.assert_called_once_with("BTC-USDT", "order_b")

    def test_order_b_submit_failed_cancels_a(self):
        """B 下单失败 -> 取消 A，返回 failed"""
        adapter_a = make_mock_adapter("binance")
        adapter_a.place_fok_order.return_value = "order_a"

        adapter_b = make_mock_adapter("bybit")
        adapter_b.place_fok_order.return_value = None

        engine = ExecutionEngine(timeout=5, poll_interval=0.01)
        result = engine.execute_arbitrage(
            symbol="BTC-USDT",
            adapter_a=adapter_a,
            adapter_b=adapter_b,
            side_a="BUY",
            side_b="SELL",
            quantity=1,
            price_a=50000,
            price_b=50001,
        )

        assert result.status == "failed"
        assert result.error_b == "order_b_submit_failed"
        adapter_a.cancel_order.assert_called_once_with("BTC-USDT", "order_a")

    def test_a_filled_b_unfilled_cancels_a(self):
        """A 成交 B 未成交 -> 取消 A，返回 partial_fill"""
        adapter_a = make_mock_adapter("binance")
        adapter_a.place_fok_order.return_value = "order_a"
        adapter_a.get_order_status.return_value = "filled"
        adapter_a.cancel_order.return_value = True

        adapter_b = make_mock_adapter("bybit")
        adapter_b.place_fok_order.return_value = "order_b"
        # B 总是未成交
        adapter_b.get_order_status.return_value = "unfilled"

        engine = ExecutionEngine(timeout=5, poll_interval=0.01)
        result = engine.execute_arbitrage(
            symbol="BTC-USDT",
            adapter_a=adapter_a,
            adapter_b=adapter_b,
            side_a="BUY",
            side_b="SELL",
            quantity=1,
            price_a=50000,
            price_b=50001,
        )

        assert result.status == "partial_fill"
        adapter_a.cancel_order.assert_called_once_with("BTC-USDT", "order_a")

    def test_b_filled_a_unfilled_cancels_b(self):
        """B 成交 A 未成交 -> 取消 B，返回 partial_fill"""
        adapter_a = make_mock_adapter("binance")
        adapter_a.place_fok_order.return_value = "order_a"
        adapter_a.get_order_status.return_value = "unfilled"

        adapter_b = make_mock_adapter("bybit")
        adapter_b.place_fok_order.return_value = "order_b"
        adapter_b.get_order_status.return_value = "filled"
        adapter_b.cancel_order.return_value = True

        engine = ExecutionEngine(timeout=5, poll_interval=0.01)
        result = engine.execute_arbitrage(
            symbol="BTC-USDT",
            adapter_a=adapter_a,
            adapter_b=adapter_b,
            side_a="BUY",
            side_b="SELL",
            quantity=1,
            price_a=50000,
            price_b=50001,
        )

        assert result.status == "partial_fill"
        adapter_b.cancel_order.assert_called_once_with("BTC-USDT", "order_b")

    def test_a_partial_cancels_b(self):
        """A 部分成交 -> 取消 B"""
        adapter_a = make_mock_adapter("binance")
        adapter_a.place_fok_order.return_value = "order_a"
        adapter_a.get_order_status.return_value = "partial"
        adapter_a.cancel_order.return_value = True

        adapter_b = make_mock_adapter("bybit")
        adapter_b.place_fok_order.return_value = "order_b"
        adapter_b.get_order_status.return_value = "filled"

        engine = ExecutionEngine(timeout=5, poll_interval=0.01)
        result = engine.execute_arbitrage(
            symbol="BTC-USDT",
            adapter_a=adapter_a,
            adapter_b=adapter_b,
            side_a="BUY",
            side_b="SELL",
            quantity=1,
            price_a=50000,
            price_b=50001,
        )

        assert result.status == "partial_fill"
        adapter_b.cancel_order.assert_called_once_with("BTC-USDT", "order_b")

    def test_timeout_both_unfilled(self):
        """超时两边都未成交 -> timeout"""
        adapter_a = make_mock_adapter("binance")
        adapter_a.place_fok_order.return_value = "order_a"
        adapter_a.get_order_status.return_value = "unfilled"
        adapter_a.cancel_order.return_value = True

        adapter_b = make_mock_adapter("bybit")
        adapter_b.place_fok_order.return_value = "order_b"
        adapter_b.get_order_status.return_value = "unfilled"
        adapter_b.cancel_order.return_value = True

        engine = ExecutionEngine(timeout=0.1, poll_interval=0.01)
        result = engine.execute_arbitrage(
            symbol="BTC-USDT",
            adapter_a=adapter_a,
            adapter_b=adapter_b,
            side_a="BUY",
            side_b="SELL",
            quantity=1,
            price_a=50000,
            price_b=50001,
        )

        assert result.status == "timeout"
        adapter_a.cancel_order.assert_called()
        adapter_b.cancel_order.assert_called()


class TestOrderResult:
    def test_default_values(self):
        """OrderResult 默认值正确"""
        result = OrderResult(status="filled")
        assert result.status == "filled"
        assert result.order_a_id is None
        assert result.order_b_id is None
        assert result.fill_price_a is None
        assert result.fill_price_b is None
        assert result.error_a is None
        assert result.error_b is None
        assert result.timestamp > 0
