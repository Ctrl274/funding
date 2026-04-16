import pytest
from unittest.mock import patch, MagicMock
from exchanges.bydfi import BydfiAdapter


def test_get_funding_rates():
    # Mock the batch funding rate endpoint
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "code": 200,
        "data": [
            {"symbol": "BTC-USDT", "fundRate": 0.0001, "feeTime": 1700000000000},
            {"symbol": "ETH-USDT", "fundRate": -0.00003, "feeTime": 1700000000000},
            {"symbol": "BTC-USD", "fundRate": 0.00005, "feeTime": 1700000000000},
        ]
    }

    with patch("exchanges.bydfi.requests.get", return_value=mock_resp):
        adapter = BydfiAdapter("key", "secret")
        result = adapter.get_funding_rates()

    assert "BTC-USDT" in result
    assert result["BTC-USDT"].rate == 0.0001
    assert "ETH-USDT" in result
    assert result["ETH-USDT"].rate == -0.00003
    assert "BTC-USD" not in result


def test_get_account_balance():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {"account": "UMFUTURE", "asset": "USDT", "available": "4000.50"},
            {"account": "UMFUTURE", "asset": "BTC", "available": "0.5"},
        ]
    }

    with patch("exchanges.bydfi.requests.get", return_value=mock_resp):
        adapter = BydfiAdapter("key", "secret")
        balance = adapter.get_account_balance()

    assert balance == 4000.50


def test_place_fok_order_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"code": 200, "data": {"orderId": "bydfi_order_1"}}

    with patch("requests.post", return_value=mock_resp):
        adapter = BydfiAdapter("key", "secret")
        order_id = adapter.place_fok_order("BTC-USDT", "BUY", 1, 50000)

    assert order_id == "bydfi_order_1"


def test_place_fok_order_failure():
    mock_resp = MagicMock()
    mock_resp.status_code = 400

    with patch("requests.post", return_value=mock_resp):
        adapter = BydfiAdapter("key", "secret")
        order_id = adapter.place_fok_order("BTC-USDT", "BUY", 1, 50000)

    assert order_id is None


def test_cancel_order():
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("requests.post", return_value=mock_resp):
        adapter = BydfiAdapter("key", "secret")
        result = adapter.cancel_order("BTC-USDT", "order1")

    assert result is True


def test_get_order_status_filled():
    """open_order returns code!=200, falls back to get_position."""
    mock_open_order = MagicMock()
    mock_open_order.status_code = 200
    mock_open_order.json.return_value = {"code": 101103, "message": "IP restricted"}

    mock_position = MagicMock()
    mock_position.status_code = 200
    mock_position.json.return_value = {
        "code": 200, "data": [
            {"volume": "5", "avgPrice": "50000", "side": "BUY"},
        ]
    }

    def side_effect(*args, **kwargs):
        if "open_order" in args[0]:
            return mock_open_order
        return mock_position

    with patch("exchanges.bydfi.requests.get", side_effect=side_effect):
        adapter = BydfiAdapter("key", "secret")
        status = adapter.get_order_status("BTC-USDT", "order1")

    assert status == "filled"


def test_testnet_url():
    adapter = BydfiAdapter("key", "secret", testnet=True)
    assert "bydtms" in adapter._base_url


def test_prod_url():
    adapter = BydfiAdapter("key", "secret", testnet=False)
    assert "bydfi" in adapter._base_url
