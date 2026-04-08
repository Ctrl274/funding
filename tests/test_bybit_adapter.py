import pytest
from unittest.mock import MagicMock, patch
from exchanges.bybit import BybitAdapter


def test_get_funding_rates():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "result": {
            "list": [
                {"symbol": "BTCUSDT", "fundingRate": "0.00012", "nextFundingTime": "1700000000000"},
            ]
        }
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("exchanges.bybit.httpx.get", return_value=mock_resp):
        with patch("ccxt.bybit"):
            adapter = BybitAdapter("key", "secret")
            result = adapter.get_funding_rates()

    assert "BTC-USDT" in result
    assert result["BTC-USDT"].rate == 0.00012
    assert abs(result["BTC-USDT"].rate_percent - 0.012) < 1e-10


def test_get_account_balance():
    mock_exchange = MagicMock()
    mock_exchange.fetch_balance.return_value = {"USDT": {"free": "3000.00"}}

    with patch("ccxt.bybit", return_value=mock_exchange):
        adapter = BybitAdapter("key", "secret")
        balance = adapter.get_account_balance()

    assert balance == 3000.0


def test_place_fok_order_success():
    mock_exchange = MagicMock()
    mock_exchange.create_order.return_value = {"id": "bybit_order_1"}

    with patch("ccxt.bybit", return_value=mock_exchange):
        adapter = BybitAdapter("key", "secret")
        order_id = adapter.place_fok_order("BTC-USDT", "SELL", 1, 50001)

    assert order_id == "bybit_order_1"


def test_cancel_order():
    mock_exchange = MagicMock()
    mock_exchange.cancel_order.return_value = True

    with patch("ccxt.bybit", return_value=mock_exchange):
        adapter = BybitAdapter("key", "secret")
        result = adapter.cancel_order("BTC-USDT", "order1")

    assert result is True


def test_get_order_status_filled():
    mock_exchange = MagicMock()
    mock_exchange.fetch_order.return_value = {"status": "closed", "filled": 1.0, "amount": 1.0}

    with patch("ccxt.bybit", return_value=mock_exchange):
        adapter = BybitAdapter("key", "secret")
        status = adapter.get_order_status("BTC-USDT", "order1")

    assert status == "filled"


def test_get_order_status_filled_when_status_is_open():
    """
    Bug fix: IOC 订单撮合成功后，ccxt 可能返回 status='open' 而非 'closed'，
    此时仍应根据 filled == amount 判断为 filled。
    """
    mock_exchange = MagicMock()
    # Bybit IOC 订单撮合后，ccxt 可能返回 "open" 但 filled == amount
    mock_exchange.fetch_order.return_value = {"status": "open", "filled": 5.0, "amount": 5.0}

    with patch("ccxt.bybit", return_value=mock_exchange):
        adapter = BybitAdapter("key", "secret")
        status = adapter.get_order_status("BTC-USDT", "order1")

    assert status == "filled"


def test_get_order_status_returns_unknown_on_api_error():
    """
    Bug fix: API 请求失败（rate limit / 网络抖动）时不应静默返回 'unfilled'，
    应返回 'unknown' 以便 executor 正确处理。
    """
    import logging
    mock_exchange = MagicMock()
    mock_exchange.fetch_order.side_effect = Exception("rate limit exceeded")

    with patch("ccxt.bybit", return_value=mock_exchange):
        adapter = BybitAdapter("key", "secret")
        status = adapter.get_order_status("BTC-USDT", "order1")

    assert status == "unknown"
