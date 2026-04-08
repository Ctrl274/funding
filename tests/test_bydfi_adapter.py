import pytest
from unittest.mock import patch, MagicMock
from exchanges.bydfi import BydfiAdapter


def test_get_funding_rates():
    # Mock two endpoints: ticker (all symbols) + funding_rate (per symbol)
    def side_effect(url, **kwargs):
        m = MagicMock()
        if "ticker" in url:
            m.status_code = 200
            m.raise_for_status = MagicMock()
            m.json.return_value = {
                "data": [
                    {"symbol": "BTC-USDT"},
                    {"symbol": "ETH-USDT"},
                    {"symbol": "BTC-USD"},
                ]
            }
        else:
            m.status_code = 200
            m.raise_for_status = MagicMock()
            sym = kwargs.get("params", {}).get("symbol", "")
            rates = {
                "BTC-USDT": {"lastFundingRate": "0.00010000", "nextFundingTime": 1700000000000},
                "ETH-USDT": {"lastFundingRate": "-0.00003000", "nextFundingTime": 1700000000000},
                "BTC-USD": {"lastFundingRate": "0.00005000", "nextFundingTime": 1700000000000},
            }
            m.json.return_value = {"code": 200, "data": rates.get(sym, {})}
        return m

    with patch("exchanges.bydfi.requests.get", side_effect=side_effect):
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
            {"coin": "USDT", "available": "4000.50"},
            {"coin": "BTC", "available": "0.5"},
        ]
    }

    with patch("requests.get", return_value=mock_resp):
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
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"status": "filled"}}

    with patch("requests.get", return_value=mock_resp):
        adapter = BydfiAdapter("key", "secret")
        status = adapter.get_order_status("BTC-USDT", "order1")

    assert status == "filled"


def test_testnet_url():
    adapter = BydfiAdapter("key", "secret", testnet=True)
    assert "bydtms" in adapter._base_url


def test_prod_url():
    adapter = BydfiAdapter("key", "secret", testnet=False)
    assert "bydfi" in adapter._base_url
