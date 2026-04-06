import pytest
from unittest.mock import MagicMock
from executor import ExecutionEngine, OrderResult


def test_both_orders_filled():
    adapter_a = MagicMock()
    adapter_a.NAME = "binance"
    adapter_a.place_fok_order.return_value = "order_a"
    adapter_a.get_order_status.return_value = "filled"

    adapter_b = MagicMock()
    adapter_b.NAME = "bybit"
    adapter_b.place_fok_order.return_value = "order_b"
    adapter_b.get_order_status.return_value = "filled"

    engine = ExecutionEngine(timeout=5, poll_interval=0.1)
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


def test_partial_fill_cancels_other_side():
    adapter_a = MagicMock()
    adapter_a.NAME = "binance"
    adapter_a.place_fok_order.return_value = "order_a"
    adapter_a.get_order_status.return_value = "filled"
    adapter_a.cancel_order.return_value = True

    adapter_b = MagicMock()
    adapter_b.NAME = "bybit"
    adapter_b.place_fok_order.return_value = "order_b"
    adapter_b.get_order_status.return_value = "unfilled"
    adapter_b.cancel_order.return_value = True

    engine = ExecutionEngine(timeout=5, poll_interval=0.1)
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
    assert result.error_b == "status=unfilled"
    adapter_a.cancel_order.assert_called_once()


def test_order_a_submit_failed():
    adapter_a = MagicMock()
    adapter_a.NAME = "binance"
    adapter_a.place_fok_order.return_value = None

    adapter_b = MagicMock()
    adapter_b.NAME = "bybit"
    adapter_b.place_fok_order.return_value = "order_b"

    engine = ExecutionEngine(timeout=5, poll_interval=0.1)
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
    assert result.order_a_id is None


def test_timeout_cancels_both():
    adapter_a = MagicMock()
    adapter_a.NAME = "binance"
    adapter_a.place_fok_order.return_value = "order_a"
    adapter_a.get_order_status.return_value = "pending"
    adapter_a.cancel_order.return_value = True

    adapter_b = MagicMock()
    adapter_b.NAME = "bybit"
    adapter_b.place_fok_order.return_value = "order_b"
    adapter_b.get_order_status.return_value = "pending"
    adapter_b.cancel_order.return_value = True

    engine = ExecutionEngine(timeout=1, poll_interval=0.5)
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
    assert result.order_a_id == "order_a"
    assert result.order_b_id == "order_b"
    adapter_a.cancel_order.assert_called_once()
    adapter_b.cancel_order.assert_called_once()
