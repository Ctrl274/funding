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
        adapter = MexcAdapter("key", "secret")
        result = adapter.get_funding_rates()

    assert "BTC-USDT" in result
    assert result["BTC-USDT"].rate == 0.00011


def test_get_account_balance():
    """Test that USDT swap balance is returned as a float."""
    mock_http = MagicMock()
    mock_http.signed_get.return_value = {
        "data": {
            "asset_list": [
                {"asset": "USDT", "available_balance": "2000.00"},
            ]
        }
    }

    with patch("exchanges.mexc.HttpClient", return_value=mock_http):
        adapter = MexcAdapter("key", "secret")
        balance = adapter.get_account_balance()

    assert balance == 2000.0


def test_place_fok_order_success():
    """Test that a FOK order returns the order ID."""
    mock_http = MagicMock()
    mock_http.signed_post.return_value = {
        "data": {"order_id": "mexc_order_1"}
    }

    with patch("exchanges.mexc.HttpClient", return_value=mock_http):
        adapter = MexcAdapter("key", "secret")
        order_id = adapter.place_fok_order("BTC-USDT", "BUY", 1, 50000)

    assert order_id == "mexc_order_1"


def test_get_order_status_filled():
    """Test that a filled order is reported as filled."""
    mock_http = MagicMock()
    mock_http.signed_get.return_value = {
        "data": {
            "status": "filled",
            "filled_qty": "1.0",
            "qty": "1.0",
        }
    }

    with patch("exchanges.mexc.HttpClient", return_value=mock_http):
        adapter = MexcAdapter("key", "secret")
        status = adapter.get_order_status("BTC-USDT", "order1")

    assert status == "filled"


def test_get_position_returns_dict():
    """Test that get_position returns a dict with expected fields."""
    mock_http = MagicMock()
    mock_http.signed_get.return_value = {
        "data": [
            {
                "available_quantity": "1.5",
                "side": "BUY",
                "unrealized_pnl": "50.25",
            }
        ]
    }

    with patch("exchanges.mexc.HttpClient", return_value=mock_http):
        adapter = MexcAdapter("key", "secret")
        pos = adapter.get_position("BTC-USDT")

    assert pos is not None
    assert pos["symbol"] == "BTC-USDT"
    assert pos["quantity"] == 1.5
    assert pos["side"] == "BUY"
    assert pos["unrealized_pnl"] == 50.25


def test_get_position_no_position():
    """Test that get_position returns None when no position exists."""
    mock_http = MagicMock()
    mock_http.signed_get.return_value = {"data": []}

    with patch("exchanges.mexc.HttpClient", return_value=mock_http):
        adapter = MexcAdapter("key", "secret")
        pos = adapter.get_position("BTC-USDT")

    assert pos is None


def test_place_fok_order_failure():
    """Test that a failed FOK order returns None."""
    mock_http = MagicMock()
    mock_http.signed_post.side_effect = Exception("API error")

    with patch("exchanges.mexc.HttpClient", return_value=mock_http):
        adapter = MexcAdapter("key", "secret")
        order_id = adapter.place_fok_order("BTC-USDT", "BUY", 1, 50000)

    assert order_id is None


def test_cancel_order_success():
    """Test that cancel_order returns True on success."""
    mock_http = MagicMock()
    mock_http.signed_post.return_value = {"data": {}}

    with patch("exchanges.mexc.HttpClient", return_value=mock_http):
        adapter = MexcAdapter("key", "secret")
        result = adapter.cancel_order("BTC-USDT", "order1")

    assert result is True


def test_set_leverage_success():
    """Test that set_leverage returns True on success."""
    mock_http = MagicMock()
    mock_http.signed_post.return_value = {"data": {}}

    with patch("exchanges.mexc.HttpClient", return_value=mock_http):
        adapter = MexcAdapter("key", "secret")
        result = adapter.set_leverage("BTC-USDT", 10)

    assert result is True


def test_get_ticker_price():
    """Test that get_ticker_price returns the last price."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {"last": "50000.5"}
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("exchanges.mexc.requests.get", return_value=mock_resp):
        adapter = MexcAdapter("key", "secret")
        price = adapter.get_ticker_price("BTC-USDT")

    assert price == 50000.5


def test_get_contract_size():
    """Test that get_contract_size returns the contract multiplier."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {"contract_size": 0.0001}
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("exchanges.mexc.requests.get", return_value=mock_resp):
        adapter = MexcAdapter("key", "secret")
        cs = adapter.get_contract_size("BTC-USDT")

    assert cs == 0.0001


def test_get_fee_rate():
    """Test that get_fee_rate returns maker/taker fees."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {"taker_fee": 0.0006, "maker_fee": 0.0004}
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("exchanges.mexc.requests.get", return_value=mock_resp):
        adapter = MexcAdapter("key", "secret")
        fees = adapter.get_fee_rate("BTC-USDT")

    assert fees["maker"] == 0.0004
    assert fees["taker"] == 0.0006
