"""Tests for the MEXC exchange adapter."""

import pytest
from unittest.mock import MagicMock, patch

from exchanges.mexc import MexcAdapter


def test_get_funding_rates():
    """Test that funding rates are fetched and symbols are normalized."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": [
            {"symbol": "BTC_USDT", "fundingRate": 0.00011, "nextSettleTime": 1700000000000},
        ]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("exchanges.mexc.requests.get", return_value=mock_resp):
        with patch("exchanges.mexc.ccxt.mexc"):
            adapter = MexcAdapter("key", "secret")
            result = adapter.get_funding_rates()

    assert "BTC-USDT" in result
    assert result["BTC-USDT"].rate == 0.00011


def test_get_account_balance():
    """Test that USDT swap balance is returned as a float."""
    mock_exchange = MagicMock()
    mock_exchange.fetch_balance.return_value = {"USDT": {"free": "2000.00"}}

    with patch("exchanges.mexc.ccxt.mexc", return_value=mock_exchange):
        adapter = MexcAdapter("key", "secret")
        balance = adapter.get_account_balance()

    assert balance == 2000.0


def test_place_fok_order_success():
    """Test that a FOK order returns the order ID."""
    mock_exchange = MagicMock()
    mock_exchange.create_order.return_value = {"id": "mexc_order_1"}

    with patch("exchanges.mexc.ccxt.mexc", return_value=mock_exchange):
        adapter = MexcAdapter("key", "secret")
        order_id = adapter.place_fok_order("BTC-USDT", "BUY", 1, 50000)

    assert order_id == "mexc_order_1"


def test_get_order_status_filled():
    """Test that a closed order is reported as filled."""
    mock_exchange = MagicMock()
    mock_exchange.fetch_order.return_value = {
        "status": "closed",
        "filled": 1.0,
        "amount": 1.0,
    }

    with patch("exchanges.mexc.ccxt.mexc", return_value=mock_exchange):
        adapter = MexcAdapter("key", "secret")
        status = adapter.get_order_status("BTC-USDT", "order1")

    assert status == "filled"
