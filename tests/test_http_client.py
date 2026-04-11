"""Tests for exchanges/http_client.py — all 4 signing modes."""

import time
import pytest
from unittest.mock import MagicMock, patch, call
import hmac
import hashlib

from exchanges.http_client import HttpClient, ExchangeApiError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hmac_sha256(secret: str, msg: str) -> str:
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Binance signing tests
# ---------------------------------------------------------------------------

class TestBinanceSigning:
    """Verify Binance HMAC-SHA256(query_string) signature format."""

    def test_sign_binance_adds_timestamp_recvwindow_signature(self):
        """Signed params should include timestamp, recvWindow, and signature."""
        client = HttpClient(
            "https://fapi.binance.com",
            "test_key",
            "test_secret",
            sign_mode="binance",
            recv_window="5000",
        )
        params = {"symbol": "BTCUSDT", "leverage": "10"}
        signed = client._sign_binance(params)

        assert "timestamp" in signed
        assert "recvWindow" in signed
        assert "signature" in signed
        assert signed["recvWindow"] == "5000"
        assert signed["symbol"] == "BTCUSDT"
        assert signed["leverage"] == "10"

    def test_sign_binance_sorted_alphabetically(self):
        """Params must be sorted alphabetically before signing."""
        client = HttpClient(
            "https://fapi.binance.com",
            "test_key",
            "test_secret",
            sign_mode="binance",
        )
        params = {"z_param": "z_val", "a_param": "a_val", "m_param": "m_val"}
        signed = client._sign_binance(params)

        # Signature should be HMAC-SHA256 of "a_param=a_val&m_param=m_val&..." +
        # timestamp + recvWindow
        ts = signed["timestamp"]
        rw = signed["recvWindow"]
        # Expected query string sorted alphabetically
        expected_qs = (
            f"a_param=a_val&m_param=m_val&recvWindow={rw}"
            f"&timestamp={ts}&z_param=z_val"
        )
        expected_sig = _hmac_sha256("test_secret", expected_qs)
        assert signed["signature"] == expected_sig

    def test_sign_binance_timestamp_is_recent(self):
        """timestamp should be within 5 seconds of now."""
        client = HttpClient(
            "https://fapi.binance.com",
            "test_key",
            "test_secret",
            sign_mode="binance",
        )
        signed = client._sign_binance({})
        ts = int(signed["timestamp"])
        now_ms = int(time.time() * 1000)
        assert abs(ts - now_ms) < 5000

    def test_signed_get_binance_url(self):
        """signed_get should call the URL with signed query params."""
        client = HttpClient(
            "https://fapi.binance.com",
            "test_key",
            "test_secret",
            sign_mode="binance",
        )
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"balance": "1000"}

        with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
            result = client.signed_get("/fapi/v1/account", {"symbol": "BTCUSDT"})

        mock_get.assert_called_once()
        url = mock_get.call_args[0][0]
        assert "fapi/v1/account" in url
        assert "signature=" in url
        assert "X-MBX-APIKEY" in mock_get.call_args[1]["headers"]
        assert result["balance"] == "1000"

    def test_signed_post_binance_url(self):
        """signed_post should include signed params in the URL query string."""
        client = HttpClient(
            "https://fapi.binance.com",
            "test_key",
            "test_secret",
            sign_mode="binance",
        )
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"orderId": "12345"}

        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            result = client.signed_post(
                "/fapi/v1/order",
                {"symbol": "BTCUSDT", "side": "BUY"},
                body="",
            )

        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        assert "fapi/v1/order" in url
        assert "signature=" in url
        assert result["orderId"] == "12345"


# ---------------------------------------------------------------------------
# Bybit signing tests
# ---------------------------------------------------------------------------

class TestBybitSigning:
    """Verify Bybit HMAC-SHA256(TIMESTAMP + API_KEY + RECV_WINDOW + query + body) format."""

    def test_sign_bybit_adds_api_key_timestamp_recvwindow_sign(self):
        """Signed params should include api_key, timestamp, recv_window, and sign."""
        client = HttpClient(
            "https://api.bybit.com",
            "test_key",
            "test_secret",
            sign_mode="bybit",
            recv_window="5000",
        )
        params = {"symbol": "BTCUSDT"}
        signed = client._sign_bybit(params, body="")

        assert "api_key" in signed
        assert "timestamp" in signed
        assert "recv_window" in signed
        assert "sign" in signed
        assert signed["api_key"] == "test_key"
        assert signed["recv_window"] == "5000"

    def test_sign_bybit_params_sorted(self):
        """Query params must be sorted alphabetically before signing."""
        client = HttpClient(
            "https://api.bybit.com",
            "test_key",
            "test_secret",
            sign_mode="bybit",
            recv_window="5000",
        )
        params = {"z_param": "z", "a_param": "a"}
        signed = client._sign_bybit(params, body="")

        ts = signed["timestamp"]
        # sign_str = ts + api_key + recv_window + "a_param=a&z_param=z" + body
        expected_str = ts + "test_key" + "5000" + "a_param=a&z_param=z"
        expected_sig = _hmac_sha256("test_secret", expected_str)
        assert signed["sign"] == expected_sig

    def test_sign_bybit_with_body(self):
        """Body is appended to the signing string."""
        client = HttpClient(
            "https://api.bybit.com",
            "test_key",
            "test_secret",
            sign_mode="bybit",
            recv_window="5000",
        )
        params = {"symbol": "BTCUSDT"}
        body = '{"side":"BUY","qty":"1"}'
        signed = client._sign_bybit(params, body=body)

        ts = signed["timestamp"]
        # sign_str = ts + api_key + recv_window + "symbol=BTCUSDT" + body
        expected_str = ts + "test_key" + "5000" + "symbol=BTCUSDT" + body
        expected_sig = _hmac_sha256("test_secret", expected_str)
        assert signed["sign"] == expected_sig

    def test_signed_post_bybit_headers(self):
        """Bybit POST should include X-BAPI-* headers."""
        client = HttpClient(
            "https://api.bybit.com",
            "test_key",
            "test_secret",
            sign_mode="bybit",
        )
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"retCode": 0, "retMsg": "OK", "result": {}}

        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            client.signed_post("/v5/order/create", {"category": "linear"}, body='{}')

        headers = mock_post.call_args[1]["headers"]
        assert headers["X-BAPI-API-KEY"] == "test_key"
        assert headers["X-BAPI-SIGN-TYPE"] == "2"
        assert "X-BAPI-TIMESTAMP" in headers
        assert "X-BAPI-RECV-WINDOW" in headers
        assert "X-BAPI-SIGN" in headers


# ---------------------------------------------------------------------------
# BYDFi signing tests
# ---------------------------------------------------------------------------

class TestBydfiSigning:
    """Verify BYDFi HMAC-SHA256(API_KEY + TIMESTAMP + PARAMS_STR) format."""

    def test_sign_bydfi_adds_headers(self):
        """BYDFi signed params include api_key, timestamp, signature."""
        client = HttpClient(
            "https://api.bydfi.com/api",
            "test_key",
            "test_secret",
            sign_mode="bydfi",
        )
        signed = client._sign_bydfi(params={}, body="")

        assert "api_key" in signed
        assert "timestamp" in signed
        assert "signature" in signed
        assert signed["api_key"] == "test_key"

    def test_sign_bydfi_get_format(self):
        """For GET (no body), sign string = API_KEY + TIMESTAMP + sorted_query."""
        client = HttpClient(
            "https://api.bydfi.com/api",
            "test_key",
            "test_secret",
            sign_mode="bydfi",
        )
        params = {"symbol": "BTC-USDT"}
        signed = client._sign_bydfi(params, body="")

        ts = signed["timestamp"]
        expected_str = "test_key" + ts + "symbol=BTC-USDT"
        expected_sig = _hmac_sha256("test_secret", expected_str)
        assert signed["signature"] == expected_sig

    def test_sign_bydfi_post_format(self):
        """For POST (with body), sign string = API_KEY + TIMESTAMP + body."""
        client = HttpClient(
            "https://api.bydfi.com/api",
            "test_key",
            "test_secret",
            sign_mode="bydfi",
        )
        body = '{"symbol":"BTC-USDT","side":"BUY"}'
        signed = client._sign_bydfi(params={}, body=body)

        ts = signed["timestamp"]
        expected_str = "test_key" + ts + body
        expected_sig = _hmac_sha256("test_secret", expected_str)
        assert signed["signature"] == expected_sig

    def test_signed_get_bydfi_headers(self):
        """BYDFi GET should include X-API-* headers."""
        client = HttpClient(
            "https://api.bydfi.com/api",
            "test_key",
            "test_secret",
            sign_mode="bydfi",
        )
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"code": 200, "data": {}}

        with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
            client.signed_get("/swap/account/balance", {"orderId": "123"})

        headers = mock_get.call_args[1]["headers"]
        assert headers["X-API-KEY"] == "test_key"
        assert "X-API-TIMESTAMP" in headers
        assert "X-API-SIGNATURE" in headers


# ---------------------------------------------------------------------------
# MEXC signing tests
# ---------------------------------------------------------------------------

class TestMexcSigning:
    """Verify MEXC HMAC-SHA256(apikey={KEY}&timestamp={TS}, secret) format."""

    def test_sign_mexc_adds_fields(self):
        """MEXC signed params include api_key, timestamp, sign."""
        client = HttpClient(
            "https://api.mexc.com",
            "test_key",
            "test_secret",
            sign_mode="mexc",
        )
        params = {"symbol": "BTC_USDT"}
        signed = client._sign_mexc(params)

        assert "api_key" in signed
        assert "timestamp" in signed
        assert "sign" in signed
        assert signed["api_key"] == "test_key"

    def test_sign_mexc_format(self):
        """Sign string must be exactly 'apikey={KEY}&timestamp={TS}'."""
        client = HttpClient(
            "https://api.mexc.com",
            "test_key",
            "test_secret",
            sign_mode="mexc",
        )
        signed = client._sign_mexc({})

        ts = signed["timestamp"]
        expected_sig = _hmac_sha256("test_secret", f"apikey=test_key&timestamp={ts}")
        assert signed["sign"] == expected_sig

    def test_signed_get_mexc_url(self):
        """MEXC signed_get should pass signed params as query string."""
        client = HttpClient(
            "https://api.mexc.com",
            "test_key",
            "test_secret",
            sign_mode="mexc",
        )
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"code": "0", "data": {}}

        with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
            result = client.signed_get("/api/v1/account/balance", {"currency": "USDT"})

        mock_get.assert_called_once()
        url = mock_get.call_args[0][0]
        assert "account/balance" in url
        assert "api_key=test_key" in url
        assert "sign=" in url
        assert result["code"] == "0"


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Verify ExchangeApiError is raised correctly."""

    def test_raises_exchange_api_error_on_non_ok(self):
        """Non-ok HTTP response should raise ExchangeApiError."""
        client = HttpClient(
            "https://fapi.binance.com",
            "test_key",
            "test_secret",
            sign_mode="binance",
        )
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 403
        mock_resp.json.return_value = {"code": -2015, "msg": "Invalid API key"}
        mock_resp.text = '{"code":-2015,"msg":"Invalid API key"}'
        mock_resp.raise_for_status = MagicMock(
            side_effect=Exception("HTTP 403")
        )

        with pytest.raises(ExchangeApiError) as exc_info:
            client._parse_response(mock_resp)

        assert exc_info.value.exchange == "binance"
        assert exc_info.value.code == -2015
        assert "Invalid API key" in exc_info.value.message

    def test_raises_exchange_api_error_bybit_retcode(self):
        """Bybit retCode != 0 should raise ExchangeApiError."""
        client = HttpClient(
            "https://api.bybit.com",
            "test_key",
            "test_secret",
            sign_mode="bybit",
        )
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "retCode": 10001,
            "retMsg": "invalid request",
            "result": None,
        }

        with pytest.raises(ExchangeApiError) as exc_info:
            client._parse_response(mock_resp)

        assert exc_info.value.exchange == "bybit"
        assert exc_info.value.code == 10001

    def test_raises_exchange_api_error_bydfi_code(self):
        """BYDFi code != 200 should raise ExchangeApiError."""
        client = HttpClient(
            "https://api.bydfi.com/api",
            "test_key",
            "test_secret",
            sign_mode="bydfi",
        )
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "code": 401,
            "msg": "Unauthorized",
        }
        mock_resp.text = '{"code":401,"msg":"Unauthorized"}'

        with pytest.raises(ExchangeApiError) as exc_info:
            client._parse_response(mock_resp)

        assert exc_info.value.exchange == "bydfi"
        assert exc_info.value.code == 401

    def test_exchange_api_error_str(self):
        """Exception string should include exchange, code, and message."""
        err = ExchangeApiError("binance", -2015, "Invalid API key")
        assert "binance" in str(err)
        assert "-2015" in str(err)
        assert "Invalid API key" in str(err)


# ---------------------------------------------------------------------------
# signed_delete tests
# ---------------------------------------------------------------------------

class TestSignedDelete:
    """Verify signed_delete works for all modes."""

    def test_signed_delete_binance(self):
        """DELETE should include signature in URL query string."""
        client = HttpClient(
            "https://fapi.binance.com",
            "test_key",
            "test_secret",
            sign_mode="binance",
        )
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"orderId": "12345"}

        with patch.object(client._session, "delete", return_value=mock_resp) as mock_del:
            result = client.signed_delete("/fapi/v1/order", {"orderId": "12345"})

        mock_del.assert_called_once()
        url = mock_del.call_args[0][0]
        assert "signature=" in url
        assert result["orderId"] == "12345"


# ---------------------------------------------------------------------------
# Unknown sign_mode
# ---------------------------------------------------------------------------

class TestUnknownSignMode:
    def test_unknown_sign_mode_raises(self):
        """Unknown sign_mode should raise ValueError."""
        client = HttpClient(
            "https://api.example.com",
            "test_key",
            "test_secret",
            sign_mode="unknown",
        )
        with pytest.raises(ValueError, match="Unknown sign_mode"):
            client._sign_request("/test", {}, "")
