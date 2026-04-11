"""
Shared HttpClient for exchange API calls with HMAC signing.

Supports Binance, Bybit, BYDFi, and MEXC signature modes.
"""

import time
import hmac
import hashlib
import requests
from typing import Any, Dict, Optional
from urllib.parse import quote


class ExchangeApiError(Exception):
    """Raised when an exchange API call fails."""

    def __init__(self, exchange: str, code: Any, message: str) -> None:
        self.exchange = exchange
        self.code = code
        self.message = message
        super().__init__(f"[{exchange}] code={code}: {message}")


class HttpClient:
    """HTTP client with HMAC signing for multiple exchanges.

    Parameters
    ----------
    base_url : str
        Base URL for the exchange API (e.g. "https://fapi.binance.com").
    api_key : str
        API key for authentication.
    api_secret : str
        API secret for HMAC signing.
    sign_mode : str
        One of "binance", "bybit", "bydfi", "mexc".
    recv_window : str
        recvWindow value appended in signatures (default "5000").
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str,
        sign_mode: str = "binance",
        recv_window: str = "5000",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._api_secret = api_secret
        self._sign_mode = sign_mode
        self._recv_window = recv_window
        self._session = requests.Session()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def signed_get(self, path: str, params: Optional[Dict[str, Any]] = None) -> dict:
        """Send a signed GET request.

        Parameters
        ----------
        path : str
            API endpoint path (e.g. "/fapi/v1/account").
        params : dict, optional
            Query parameters to include in the request.

        Returns
        -------
        dict
            Parsed JSON response.

        Raises
        ------
        ExchangeApiError
            If the exchange returns a non-successful response.
        """
        params = params or {}
        signed = self._sign_request(path, params, body="")
        url = self._build_url(path, signed)
        resp = self._session.get(url, headers=self._headers_get(signed), timeout=10)
        return self._parse_response(resp)

    def signed_post(
        self, path: str, params: Optional[Dict[str, Any]] = None, body: str = ""
    ) -> dict:
        """Send a signed POST request.

        Parameters
        ----------
        path : str
            API endpoint path.
        params : dict, optional
            Query parameters to include in the URL.
        body : str
            JSON request body (empty string for no body).

        Returns
        -------
        dict
            Parsed JSON response.

        Raises
        ------
        ExchangeApiError
            If the exchange returns a non-successful response.
        """
        params = params or {}
        signed = self._sign_request(path, params, body)
        url = self._build_url(path, signed)
        resp = self._session.post(
            url, headers=self._headers_post(signed, body), data=body or None, timeout=10
        )
        return self._parse_response(resp)

    def signed_delete(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> dict:
        """Send a signed DELETE request.

        Parameters
        ----------
        path : str
            API endpoint path.
        params : dict, optional
            Query parameters.

        Returns
        -------
        dict
            Parsed JSON response.

        Raises
        ------
        ExchangeApiError
            If the exchange returns a non-successful response.
        """
        params = params or {}
        signed = self._sign_request(path, params, body="")
        url = self._build_url(path, signed)
        resp = self._session.delete(url, headers=self._headers_get(signed), timeout=10)
        return self._parse_response(resp)

    # -------------------------------------------------------------------------
    # Signing logic
    # -------------------------------------------------------------------------

    def _sign_request(
        self, path: str, params: Dict[str, Any], body: str
    ) -> Dict[str, str]:
        """Compute signature and return params dict with auth fields added.

        Dispatch based on sign_mode.
        """
        mode = self._sign_mode.lower()

        if mode == "binance":
            return self._sign_binance(params)
        elif mode == "bybit":
            return self._sign_bybit(params, body)
        elif mode == "bydfi":
            return self._sign_bydfi(params, body)
        elif mode == "mexc":
            return self._sign_mexc(params)
        else:
            raise ValueError(f"Unknown sign_mode: {mode}")

    def _sign_binance(self, params: Dict[str, Any]) -> Dict[str, str]:
        """Sign params for Binance.

        Sort keys alphabetically, append timestamp + recvWindow,
        HMAC-SHA256 the full query string.
        """
        import copy
        p = {k: str(v) for k, v in sorted(params.items())}
        ts = str(int(time.time() * 1000))
        p["timestamp"] = ts
        p["recvWindow"] = self._recv_window
        query = "&".join(f"{quote(str(k), safe='')}={quote(str(v), safe='')}"
                         for k, v in sorted(p.items()))
        sig = hmac.new(
            self._api_secret.encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        p["signature"] = sig
        return p

    def _sign_bybit(self, params: Dict[str, Any], body: str) -> Dict[str, str]:
        """Sign for Bybit.

        Signature = HMAC-SHA256(
            TIMESTAMP + API_KEY + RECV_WINDOW + sorted_query_string + body
        )

        Auth fields (timestamp, sign, etc.) are sent via headers only,
        NOT in query params. The sign string only includes business params.
        """
        ts = str(int(time.time() * 1000))

        # Sort params alphabetically for the signing string
        sorted_items = sorted((k, str(v)) for k, v in params.items())
        query = "&".join(f"{k}={v}" for k, v in sorted_items)

        # Build the signing string: TIMESTAMP + API_KEY + RECV_WINDOW + query + body
        sign_str = ts + self._api_key + self._recv_window + query + body

        sig = hmac.new(
            self._api_secret.encode(), sign_str.encode(), hashlib.sha256
        ).hexdigest()

        # Return business params only; auth goes in headers via _headers_get
        # Store auth fields under _bybit_ prefix so headers can read them
        # but _build_url won't include them in the query string
        p = {k: str(v) for k, v in params.items()}
        p["_bybit_timestamp"] = ts
        p["_bybit_sign"] = sig
        return p

    def _sign_bydfi(self, params: Dict[str, Any], body: str) -> Dict[str, str]:
        """Sign for BYDFi.

        Signature = HMAC-SHA256(API_KEY + TIMESTAMP + PARAMS_STR)
        where PARAMS_STR is query string for GET or body for POST.
        """
        ts = str(int(time.time() * 1000))

        if body:
            params_str = body
        else:
            sorted_items = sorted((k, str(v)) for k, v in params.items())
            params_str = "&".join(f"{k}={v}" for k, v in sorted_items)

        sign_str = self._api_key + ts + params_str

        sig = hmac.new(
            self._api_secret.encode(), sign_str.encode(), hashlib.sha256
        ).hexdigest()

        return {
            "api_key": self._api_key,
            "timestamp": ts,
            "signature": sig,
        }

    def _sign_mexc(self, params: Dict[str, Any]) -> Dict[str, str]:
        """Sign for MEXC.

        Signature = HMAC-SHA256(apikey={KEY}&timestamp={TS}, secret)
        """
        ts = str(int(time.time() * 1000))

        sign_input = f"apikey={self._api_key}&timestamp={ts}"
        sig = hmac.new(
            self._api_secret.encode(), sign_input.encode(), hashlib.sha256
        ).hexdigest()

        p = {k: str(v) for k, v in params.items()}
        p["api_key"] = self._api_key
        p["timestamp"] = ts
        p["sign"] = sig
        return p

    # -------------------------------------------------------------------------
    # Headers
    # -------------------------------------------------------------------------

    def _headers_get(self, signed: Dict[str, str]) -> Dict[str, str]:
        """Return headers for GET request based on sign mode."""
        mode = self._sign_mode.lower()

        if mode == "binance":
            return {"X-MBX-APIKEY": self._api_key}
        elif mode == "bybit":
            return {
                "X-BAPI-API-KEY": self._api_key,
                "X-BAPI-SIGN": signed["_bybit_sign"],
                "X-BAPI-SIGN-TYPE": "2",
                "X-BAPI-TIMESTAMP": signed["_bybit_timestamp"],
                "X-BAPI-RECV-WINDOW": self._recv_window,
            }
        elif mode == "bydfi":
            return {
                "X-API-KEY": self._api_key,
                "X-API-TIMESTAMP": signed["timestamp"],
                "X-API-SIGNATURE": signed["signature"],
                "Content-Type": "application/json",
            }
        elif mode == "mexc":
            return {
                "Content-Type": "application/json",
            }
        else:
            return {}

    def _headers_post(self, signed: Dict[str, str], body: str) -> Dict[str, str]:
        """Return headers for POST request based on sign mode."""
        mode = self._sign_mode.lower()

        if mode == "binance":
            return {"X-MBX-APIKEY": self._api_key}
        elif mode == "bybit":
            return {
                "X-BAPI-API-KEY": self._api_key,
                "X-BAPI-SIGN": signed["_bybit_sign"],
                "X-BAPI-SIGN-TYPE": "2",
                "X-BAPI-TIMESTAMP": signed["_bybit_timestamp"],
                "X-BAPI-RECV-WINDOW": self._recv_window,
                "Content-Type": "application/json",
            }
        elif mode == "bydfi":
            return {
                "X-API-KEY": self._api_key,
                "X-API-TIMESTAMP": signed["timestamp"],
                "X-API-SIGNATURE": signed["signature"],
                "Content-Type": "application/json",
            }
        elif mode == "mexc":
            return {
                "Content-Type": "application/json",
            }
        else:
            return {}

    # -------------------------------------------------------------------------
    # URL helpers
    # -------------------------------------------------------------------------

    def _build_url(self, path: str, params: Dict[str, str]) -> str:
        """Build full URL with query string.

        Keys prefixed with _bybit_ are internal auth fields and
        are excluded from the URL query string.
        """
        url = self._base_url + path
        # Filter out internal auth fields (prefixed with underscore)
        filtered = {k: v for k, v in params.items() if not k.startswith("_")}
        if filtered:
            qs = "&".join(
                f"{quote(str(k), safe='')}={quote(str(v), safe='')}"
                for k, v in filtered.items()
            )
            return f"{url}?{qs}"
        return url

    # -------------------------------------------------------------------------
    # Response handling
    # -------------------------------------------------------------------------

    def _parse_response(self, resp: requests.Response) -> dict:
        """Parse JSON response, raising ExchangeApiError on failure."""
        try:
            data = resp.json()
        except ValueError:
            resp.raise_for_status()
            raise ExchangeApiError(
                self._sign_mode,
                resp.status_code,
                f"Non-JSON response: {resp.text[:200]}",
            )

        # Check for exchange-specific error codes
        if not resp.ok:
            code = data.get("code") or data.get("retCode") or resp.status_code
            msg = (
                data.get("msg")
                or data.get("retMsg")
                or data.get("message")
                or resp.text[:200]
            )
            raise ExchangeApiError(self._sign_mode, code, msg)

        # Additional error checks per exchange
        mode = self._sign_mode.lower()
        if mode == "bybit":
            if data.get("retCode") != 0:
                raise ExchangeApiError(
                    self._sign_mode,
                    data.get("retCode"),
                    data.get("retMsg") or resp.text[:200],
                )
        elif mode == "bydfi":
            if data.get("code") != 200:
                raise ExchangeApiError(
                    self._sign_mode,
                    data.get("code"),
                    data.get("msg") or resp.text[:200],
                )

        return data
