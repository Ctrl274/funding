import pytest
from unittest.mock import MagicMock, patch
from exchanges.bybit import BybitAdapter
from exchanges.base import CloseResult


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
        adapter = BybitAdapter("key", "secret")
        result = adapter.get_funding_rates()

    assert "BTC-USDT" in result
    assert result["BTC-USDT"].rate == 0.00012
    assert abs(result["BTC-USDT"].rate_percent - 0.012) < 1e-10


def test_get_account_balance():
    """get_account_balance uses V5 wallet-balance, extracting available equity."""
    mock_http = MagicMock()
    mock_http.signed_get.return_value = {
        "retCode": 0,
        "result": {
            "list": [{
                "coin": [
                    {"coin": "USDT", "available": "3000.00", "equity": "3000.00", "walletBalance": "3000.00"}
                ]
            }]
        }
    }

    with patch("exchanges.bybit.HttpClient", return_value=mock_http):
        adapter = BybitAdapter("key", "secret")
        balance = adapter.get_account_balance()

    assert balance == 3000.0


def test_get_account_balance_falls_back_to_equity():
    """When available is null, falls back to walletBalance then equity."""
    mock_http = MagicMock()
    mock_http.signed_get.return_value = {
        "retCode": 0,
        "result": {
            "list": [{
                "coin": [
                    {"coin": "USDT", "available": None, "equity": "50928.52730486", "walletBalance": "50928.52730486"}
                ]
            }]
        }
    }

    with patch("exchanges.bybit.HttpClient", return_value=mock_http):
        adapter = BybitAdapter("key", "secret")
        balance = adapter.get_account_balance()

    assert balance == 50928.52730486


def test_get_account_balance_returns_zero_on_error():
    """Returns 0.0 when the API call fails."""
    mock_http = MagicMock()
    mock_http.signed_get.side_effect = Exception("network error")

    with patch("exchanges.bybit.HttpClient", return_value=mock_http):
        adapter = BybitAdapter("key", "secret")
        balance = adapter.get_account_balance()

    assert balance == 0.0


def test_place_fok_order_success():
    mock_http = MagicMock()
    mock_http.signed_post.return_value = {
        "retCode": 0,
        "result": {"orderId": "bybit_order_1"}
    }

    with patch("exchanges.bybit.HttpClient", return_value=mock_http):
        adapter = BybitAdapter("key", "secret")
        order_id = adapter.place_fok_order("BTC-USDT", "SELL", 1, 50001)

    assert order_id == "bybit_order_1"
    # Verify the correct params were passed
    call_params = mock_http.signed_post.call_args
    assert call_params[0][0] == "/v5/order/create"
    assert call_params[1]["params"]["symbol"] == "BTCUSDT"
    assert call_params[1]["params"]["side"] == "Sell"
    assert call_params[1]["params"]["timeInForce"] == "FOK"


def test_place_fok_order_returns_none_on_error():
    mock_http = MagicMock()
    mock_http.signed_post.side_effect = Exception("API error")

    with patch("exchanges.bybit.HttpClient", return_value=mock_http):
        adapter = BybitAdapter("key", "secret")
        order_id = adapter.place_fok_order("BTC-USDT", "BUY", 0.5, 60000)

    assert order_id is None


def test_cancel_order():
    mock_http = MagicMock()
    mock_http.signed_post.return_value = {"retCode": 0}

    with patch("exchanges.bybit.HttpClient", return_value=mock_http):
        adapter = BybitAdapter("key", "secret")
        result = adapter.cancel_order("BTC-USDT", "order1")

    assert result is True
    mock_http.signed_post.assert_called_once()


def test_cancel_order_returns_false_on_error():
    mock_http = MagicMock()
    mock_http.signed_post.side_effect = Exception("cancel failed")

    with patch("exchanges.bybit.HttpClient", return_value=mock_http):
        adapter = BybitAdapter("key", "secret")
        result = adapter.cancel_order("BTC-USDT", "order1")

    assert result is False


def test_get_order_status_filled():
    mock_http = MagicMock()
    mock_http.signed_get.return_value = {
        "retCode": 0,
        "result": {
            "list": [{
                "orderId": "order1",
                "qty": "1.0",
                "filledQty": "1.0",
                "orderStatus": "Filled"
            }]
        }
    }

    with patch("exchanges.bybit.HttpClient", return_value=mock_http):
        adapter = BybitAdapter("key", "secret")
        status = adapter.get_order_status("BTC-USDT", "order1")

    assert status == "filled"


def test_get_order_status_filled_when_status_is_open():
    """
    IOC 订单撮合成功后，即使 orderStatus 返回 'New' 或 'Open',
    只要 filledQty == qty 就应判断为 filled。
    """
    mock_http = MagicMock()
    mock_http.signed_get.return_value = {
        "retCode": 0,
        "result": {
            "list": [{
                "orderId": "order1",
                "qty": "5.0",
                "filledQty": "5.0",
                "orderStatus": "New"
            }]
        }
    }

    with patch("exchanges.bybit.HttpClient", return_value=mock_http):
        adapter = BybitAdapter("key", "secret")
        status = adapter.get_order_status("BTC-USDT", "order1")

    assert status == "filled"


def test_get_order_status_returns_unknown_on_api_error():
    """API 请求失败时应返回 'unknown' 以便 executor 正确处理。"""
    mock_http = MagicMock()
    mock_http.signed_get.side_effect = Exception("rate limit exceeded")

    with patch("exchanges.bybit.HttpClient", return_value=mock_http):
        adapter = BybitAdapter("key", "secret")
        status = adapter.get_order_status("BTC-USDT", "order1")

    assert status == "unknown"


def test_set_leverage():
    mock_http = MagicMock()
    mock_http.signed_post.return_value = {"retCode": 0}

    with patch("exchanges.bybit.HttpClient", return_value=mock_http):
        adapter = BybitAdapter("key", "secret")
        result = adapter.set_leverage("BTC-USDT", 10)

    assert result is True
    call_params = mock_http.signed_post.call_args
    assert call_params[0][0] == "/v5/position/set-leverage"
    assert call_params[1]["params"]["buyLeverage"] == "10"
    assert call_params[1]["params"]["sellLeverage"] == "10"


def test_get_position_with_open_position():
    mock_http = MagicMock()
    mock_http.signed_get.return_value = {
        "retCode": 0,
        "result": {
            "list": [{
                "symbol": "BTCUSDT",
                "size": "0.001",
                "avgPrice": "72000.00",
                "side": "Buy"
            }]
        }
    }

    with patch("exchanges.bybit.HttpClient", return_value=mock_http):
        adapter = BybitAdapter("key", "secret")
        pos = adapter.get_position("BTC-USDT")

    assert pos is not None
    assert pos["side"] == "BUY"
    assert pos["quantity"] == 0.001
    assert pos["entry_price"] == 72000.0


def test_get_position_no_position():
    mock_http = MagicMock()
    mock_http.signed_get.return_value = {
        "retCode": 0,
        "result": {
            "list": [{
                "symbol": "BTCUSDT",
                "size": "0",
                "side": "Buy"
            }]
        }
    }

    with patch("exchanges.bybit.HttpClient", return_value=mock_http):
        adapter = BybitAdapter("key", "secret")
        pos = adapter.get_position("BTC-USDT")

    assert pos is None


def test_close_position():
    mock_http = MagicMock()
    # get_position -> signed_get returns a position (first call)
    # then returns empty (position closed after fill)
    mock_http.signed_get.side_effect = [
        {  # first call: get_position
            "retCode": 0,
            "result": {
                "list": [{
                    "symbol": "BTCUSDT",
                    "size": "1",
                    "side": "Buy",
                    "avgPrice": "50000",
                }]
            }
        },
        {  # second call: position closed -> empty
            "retCode": 0,
            "result": {"list": []}
        },
    ]
    # place_market_order -> signed_post returns order ID
    mock_http.signed_post.return_value = {
        "retCode": 0,
        "result": {"orderId": "close-order-1"}
    }

    with patch("exchanges.bybit.HttpClient", return_value=mock_http):
        adapter = BybitAdapter("key", "secret")
        adapter.get_order_status = MagicMock(return_value="filled")
        result = adapter.close_position("BTC-USDT")

    assert isinstance(result, CloseResult)
    assert result.success is True


def test_close_position_timeout_but_order_pending():
    """Poll times out but order is still new/pending -> treat as success."""
    mock_http = MagicMock()
    mock_http.signed_get.return_value = {
        "retCode": 0,
        "result": {
            "list": [{
                "symbol": "BTCUSDT",
                "size": "1",
                "side": "Buy",
                "avgPrice": "50000",
            }]
        }
    }
    mock_http.signed_post.return_value = {
        "retCode": 0,
        "result": {"orderId": "pending-order-1"}
    }

    with patch("exchanges.bybit.HttpClient", return_value=mock_http):
        adapter = BybitAdapter("key", "secret")
        # Simulate: order placed but never fills within 5s -> timeout -> still "new"
        adapter.get_order_status = MagicMock(return_value="new")
        result = adapter.close_position("BTC-USDT")

    assert isinstance(result, CloseResult)
    assert result.success is True  # pending order treated as success
    assert result.close_price_a == 50000.0  # entry price as proxy


def test_close_position_timeout_and_order_cancelled():
    """Poll times out and order was cancelled -> return failure."""
    mock_http = MagicMock()
    mock_http.signed_get.return_value = {
        "retCode": 0,
        "result": {
            "list": [{
                "symbol": "BTCUSDT",
                "size": "1",
                "side": "Buy",
                "avgPrice": "50000",
            }]
        }
    }
    mock_http.signed_post.return_value = {
        "retCode": 0,
        "result": {"orderId": "cancelled-order-1"}
    }

    with patch("exchanges.bybit.HttpClient", return_value=mock_http):
        adapter = BybitAdapter("key", "secret")
        adapter.get_order_status = MagicMock(return_value="cancelled")
        result = adapter.close_position("BTC-USDT")

    assert isinstance(result, CloseResult)
    assert result.success is False


def test_get_ticker_price():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "result": {
            "list": [{"lastPrice": "50000.00"}]
        }
    }

    with patch("exchanges.bybit.httpx.get", return_value=mock_resp):
        adapter = BybitAdapter("key", "secret")
        price = adapter.get_ticker_price("BTC-USDT")

    assert price == 50000.0


def test_symbol_conversion():
    """Verify symbol format conversion between our format and Bybit V5 format."""
    adapter = BybitAdapter("key", "secret")

    assert adapter._to_bybit_symbol("BTC-USDT") == "BTCUSDT"
    assert adapter._from_bybit_symbol("BTCUSDT") == "BTC-USDT"


def test_get_fee_rate():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "result": {
            "list": [{
                "makerFeeRate": "0.0002",
                "takerFeeRate": "0.00055"
            }]
        }
    }

    with patch("exchanges.bybit.httpx.get", return_value=mock_resp):
        adapter = BybitAdapter("key", "secret")
        fees = adapter.get_fee_rate("BTC-USDT")

    assert fees["maker"] == 0.0002
    assert fees["taker"] == 0.00055
