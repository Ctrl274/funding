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
