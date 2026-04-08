import pytest
from unittest.mock import MagicMock, patch
from exchanges.binance import BinanceAdapter


def test_get_funding_rates():
    mock_resp = MagicMock()
    mock_resp.json.return_value = [
        {"symbol": "BTCUSDT", "lastFundingRate": "0.00010000", "nextFundingTime": 1700000000000},
        {"symbol": "ETHUSDT", "lastFundingRate": "-0.00005000", "nextFundingTime": 1700000000000},
    ]
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_resp):
        adapter = BinanceAdapter("key", "secret")
        result = adapter.get_funding_rates()

    assert "BTC-USDT" in result
    assert result["BTC-USDT"].rate == 0.0001
    assert result["BTC-USDT"].rate_percent == 0.01
    assert "ETH-USDT" in result
    assert result["ETH-USDT"].rate == -0.00005


def test_get_account_balance():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "assets": [{"asset": "USDT", "availableBalance": "5000.50"}]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_resp):
        adapter = BinanceAdapter("key", "secret")
        balance = adapter.get_account_balance()

    assert balance == 5000.50


def test_account_balance_returns_zero_on_error():
    """When the API call fails (e.g. testnet deprecated), balance should be 0."""
    with patch("requests.get", side_effect=Exception("API error")):
        adapter = BinanceAdapter("key", "secret")
        balance = adapter.get_account_balance()

    assert balance == 0.0


def test_place_fok_order_success():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"orderId": "12345"}
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_resp):
        adapter = BinanceAdapter("key", "secret")
        order_id = adapter.place_fok_order("BTC-USDT", "BUY", 1, 50000)

    assert order_id == "12345"


def test_place_fok_order_failure():
    with patch("requests.post", side_effect=Exception("Order failed")):
        adapter = BinanceAdapter("key", "secret")
        order_id = adapter.place_fok_order("BTC-USDT", "BUY", 1, 50000)

    assert order_id is None


def test_get_order_status_filled():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"status": "FILLED"}
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_resp):
        adapter = BinanceAdapter("key", "secret")
        status = adapter.get_order_status("BTC-USDT", "order123")

    assert status == "filled"


def test_get_order_status_unfilled():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"status": "NEW"}
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_resp):
        adapter = BinanceAdapter("key", "secret")
        status = adapter.get_order_status("BTC-USDT", "order123")

    assert status == "unfilled"


def test_get_ticker_price():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"symbol": "BTCUSDT", "price": "68500.00"}
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_resp):
        adapter = BinanceAdapter("key", "secret")
        price = adapter.get_ticker_price("BTC-USDT")

    assert price == 68500.0


def test_get_ticker_price_returns_none_on_error():
    with patch("requests.get", side_effect=Exception("API error")):
        adapter = BinanceAdapter("key", "secret")
        price = adapter.get_ticker_price("BTC-USDT")

    assert price is None


def test_get_order_status_returns_unknown_on_api_error():
    """
    Bug fix: API 请求失败（rate limit / 网络抖动）时不应静默返回 'unfilled'，
    应返回 'unknown' 以便 executor 正确处理。
    """
    with patch("requests.get", side_effect=Exception("rate limit exceeded")):
        adapter = BinanceAdapter("key", "secret")
        status = adapter.get_order_status("BTC-USDT", "order123")

    assert status == "unknown"
