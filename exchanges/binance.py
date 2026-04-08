"""Binance exchange adapter using ccxt + direct HTTP for public endpoints."""

import time
import hmac
import hashlib
import requests
from typing import Any, Dict, List, Optional

import ccxt

from exchanges.base import ExchangeAdapter, FundingRate


def _binance_sign(api_secret: str, params: str) -> str:
    """HMAC-SHA256 sign for Binance signed endpoints."""
    return hmac.new(
        api_secret.encode(), params.encode(), hashlib.sha256
    ).hexdigest()


class BinanceAdapter(ExchangeAdapter):
    """Exchange adapter for Binance USDT-margined futures.

    Testnet mode uses direct HTTP for all requests to avoid
    https://t.me/ccxt_announcements/92 (Binance testnet deprecation).
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(api_key, api_secret, **kwargs)
        self._testnet = testnet
        # Use Binance Demo environment for testnet (not the deprecated testnet)
        # https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info
        demo_base = "https://demo-fapi.binance.com"
        prod_base = "https://fapi.binance.com"
        self._funding_url = f"{demo_base if testnet else prod_base}/fapi/v1/premiumIndex"
        self._ticker_url = f"{demo_base if testnet else prod_base}/fapi/v1/ticker/price"
        self._api_base = f"{demo_base if testnet else prod_base}/fapi/v1"
        self._exchange: ccxt.binance = ccxt.binance(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "options": {"defaultType": "future"},
            }
        )

    # -------------------------------------------------------------------------
    # Helper methods
    # -------------------------------------------------------------------------

    def _sign_params(self, params: Dict[str, Any]) -> Dict[str, str]:
        """Add timestamp, recvWindow, and signature to params dict.

        Preserves parameter order: original params -> timestamp -> recvWindow -> signature
        """
        from collections import OrderedDict
        result = OrderedDict()
        # Original params first
        for k, v in params.items():
            result[k] = str(v)
        # Required auth params
        result["timestamp"] = str(int(time.time() * 1000))
        result["recvWindow"] = "10000"
        # Build query string preserving order
        joined = "&".join(f"{k}={v}" for k, v in result.items())
        result["signature"] = _binance_sign(self._api_secret, joined)
        return result

    def _signed_get(self, endpoint: str, params: Optional[Dict] = None, version: str = "v1") -> dict:
        """Make a signed GET request."""
        params = params or {}
        params = self._sign_params(params)
        headers = {"X-MBX-APIKEY": self._api_key}
        base = self._api_base.replace("/fapi/v1", f"/fapi/{version}")
        # Build URL with params to preserve signature order
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{base}{endpoint}?{query}"
        resp = requests.get(url, headers=headers, timeout=10)
        if not resp.ok:
            try:
                err_body = resp.json()
                code = err_body.get("code", "")
                msg = err_body.get("msg", resp.text[:200])
                raise requests.exceptions.HTTPError(
                    f"{resp.status_code} Error (code={code}): {msg}"
                )
            except ValueError:
                resp.raise_for_status()
        return resp.json()

    def _signed_post(self, endpoint: str, params: Optional[Dict] = None, version: str = "v1") -> dict:
        """Make a signed POST request."""
        params = params or {}
        params = self._sign_params(params)
        headers = {"X-MBX-APIKEY": self._api_key}
        base = self._api_base.replace("/fapi/v1", f"/fapi/{version}")
        # Build URL with params to preserve signature order
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{base}{endpoint}?{query}"
        resp = requests.post(url, headers=headers, timeout=10)
        if not resp.ok:
            try:
                err_body = resp.json()
                code = err_body.get("code", "")
                msg = err_body.get("msg", resp.text[:200])
                raise requests.exceptions.HTTPError(
                    f"{resp.status_code} Error (code={code}): {msg}"
                )
            except ValueError:
                resp.raise_for_status()
        return resp.json()

    # -------------------------------------------------------------------------
    # Symbol normalization helpers
    # -------------------------------------------------------------------------

    def _binance_symbol(self, symbol: str) -> str:
        """Convert our symbol (BTC-USDT) to Binance format (BTCUSDT)."""
        return symbol.replace("-", "")

    def _our_symbol(self, binance_sym: str) -> str:
        """Convert Binance symbol (BTCUSDT) to our format (BTC-USDT)."""
        for quote in ["USDT", "USDC", "BUSD", "TUSD", "USD"]:
            if binance_sym.endswith(quote):
                return f"{binance_sym[:-len(quote)]}-{quote}"
        return binance_sym

    # -------------------------------------------------------------------------
    # ExchangeAdapter implementation
    # -------------------------------------------------------------------------

    def get_funding_rates(self) -> Dict[str, FundingRate]:
        """Fetch current funding rates from public premiumIndex endpoint."""
        result: Dict[str, FundingRate] = {}
        try:
            resp = requests.get(self._funding_url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return result

        for item in data:
            rate_str = item.get("lastFundingRate")
            next_time_ms = item.get("nextFundingTime") or 0
            if rate_str is None:
                continue
            our_sym = self._our_symbol(item.get("symbol", ""))
            result[our_sym] = FundingRate(
                symbol=our_sym,
                rate=float(rate_str),
                next_settlement=int(next_time_ms / 1000),
            )
        return result

    def get_account_balance(self) -> float:
        """Fetch USDT free balance via signed account endpoint.

        Returns 0.0 if the API call fails (e.g. Binance testnet deprecated).
        """
        try:
            data = self._signed_get("/account", version="v3")
            for bal in data.get("assets", []):
                if bal.get("asset") == "USDT":
                    return float(bal.get("availableBalance", 0))
        except Exception:
            pass
        return 0.0

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for a symbol."""
        try:
            self._signed_post(
                "/leverage",
                params={"symbol": self._binance_symbol(symbol), "leverage": leverage},
            )
            return True
        except Exception:
            return False

    def _get_symbol_precision(self, symbol: str) -> tuple:
        """Get quantity precision and tick size for a symbol from exchangeInfo."""
        try:
            resp = requests.get(
                f"{self._api_base}/exchangeInfo",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            binance_sym = self._binance_symbol(symbol)
            for s in data.get("symbols", []):
                if s["symbol"] == binance_sym:
                    qty_precision = int(s.get("quantityPrecision", 0))
                    tick_size = 0.01  # default
                    for f in s.get("filters", []):
                        if f["filterType"] == "PRICE_FILTER":
                            tick_size = float(f["tickSize"])
                            break
                    return qty_precision, tick_size
        except Exception:
            pass
        return (0, 0.01)  # defaults

    def place_fok_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
    ) -> Optional[str]:
        """Place an IOC limit order (FOK not natively supported)."""
        import logging
        logger = logging.getLogger(__name__)

        try:
            # Get precision and format values
            qty_precision, tick_size = self._get_symbol_precision(symbol)
            qty_str = f"{int(quantity)}" if qty_precision == 0 else f"{quantity:.{qty_precision}f}"
            # Round price to tick size
            price_rounded = round(price / tick_size) * tick_size
            price_str = f"{price_rounded:.8f}".rstrip("0").rstrip(".")

            data = self._signed_post(
                "/order",
                params={
                    "symbol": self._binance_symbol(symbol),
                    "side": side.upper(),
                    "type": "LIMIT",
                    "quantity": qty_str,
                    "price": price_str,
                    "timeInForce": "IOC",
                },
            )
            order_id = str(data.get("orderId"))
            logger.info(
                f"binance order placed: {symbol} {side} {quantity} @ {price}, orderId={order_id}"
            )
            return order_id
        except Exception as e:
            logger.warning(
                f"binance order failed: {symbol} {side} {quantity} @ {price} {e}"
            )
            return None

    def _signed_delete(self, endpoint: str, params: Optional[Dict] = None, version: str = "v1") -> dict:
        """Make a signed DELETE request."""
        params = params or {}
        params = self._sign_params(params)
        headers = {"X-MBX-APIKEY": self._api_key}
        base = self._api_base.replace("/fapi/v1", f"/fapi/{version}")
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{base}{endpoint}?{query}"
        resp = requests.delete(url, headers=headers, timeout=10)
        if not resp.ok:
            try:
                err_body = resp.json()
                code = err_body.get("code", "")
                msg = err_body.get("msg", resp.text[:200])
                raise requests.exceptions.HTTPError(
                    f"{resp.status_code} Error (code={code}): {msg}"
                )
            except ValueError:
                resp.raise_for_status()
        return resp.json()

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an order."""
        try:
            self._signed_delete(
                "/order",
                params={
                    "symbol": self._binance_symbol(symbol),
                    "orderId": order_id,
                },
            )
            return True
        except Exception:
            return False

    def get_order_status(self, symbol: str, order_id: str) -> str:
        """Get order status."""
        try:
            data = self._signed_get(
                "/order",
                params={"symbol": self._binance_symbol(symbol), "orderId": order_id},
            )
            status = data.get("status", "").lower()
            if status == "filled":
                return "filled"
            if status == "partially_filled":
                return "partial"
            if status in ("canceled", "rejected"):
                return "cancelled"
            return "unfilled"
        except Exception:
            return "unfilled"

    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get position info via v2 endpoint."""
        try:
            data = self._signed_get("/positionRisk", params={"symbol": self._binance_symbol(symbol)}, version="v2")
            for pos in data:
                if float(pos.get("positionAmt", 0)) != 0:
                    return {
                        "quantity": abs(float(pos["positionAmt"])),
                        "side": "BUY" if float(pos["positionAmt"]) > 0 else "SELL",
                        "entry_price": float(pos.get("entryPrice", 0)),
                    }
            return None
        except Exception:
            return None

    def close_position(self, symbol: str) -> bool:
        """Close position via Market order with proper quantity precision."""
        import logging
        logger = logging.getLogger(__name__)
        try:
            pos = self.get_position(symbol)
            if not pos:
                return False
            side = "SELL" if pos["side"] == "BUY" else "BUY"
            qty_precision, _ = self._get_symbol_precision(symbol)
            qty_str = f"{pos['quantity']:.{qty_precision}f}".rstrip('0').rstrip('.')
            self._signed_post(
                "/order",
                params={
                    "symbol": self._binance_symbol(symbol),
                    "side": side.upper(),
                    "type": "MARKET",
                    "quantity": qty_str,
                },
            )
            return True
        except Exception as e:
            logger.warning(f"binance close_position failed: {e}")
            return False

    def get_fee_rate(self, symbol: str) -> Dict[str, float]:
        """Get fee rate from exchange info."""
        try:
            data = self._signed_get("/commissionRate", params={"symbol": self._binance_symbol(symbol)})
            return {
                "maker": float(data.get("makerCommissionRate", 0.0002)),
                "taker": float(data.get("takerCommissionRate", 0.0004)),
            }
        except Exception:
            return {"maker": 0.0002, "taker": 0.0004}

    def get_ticker_price(self, symbol: str) -> Optional[float]:
        """Fetch current last price from public ticker endpoint."""
        try:
            resp = requests.get(
                self._ticker_url,
                params={"symbol": self._binance_symbol(symbol)},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return float(data.get("price", 0))
        except Exception:
            return None

    def get_max_position(self, symbol: str) -> Optional[float]:
        """Get maximum position size from position risk endpoint."""
        try:
            data = self._signed_get(
                "/positionRisk",
                params={"symbol": self._binance_symbol(symbol)},
                version="v2",
            )
            for pos in data:
                if pos.get("symbol") == self._binance_symbol(symbol):
                    max_qty = pos.get("maxQty")
                    if max_qty is not None:
                        return float(max_qty)
            return None
        except Exception:
            return None

    def get_contract_size(self, symbol: str) -> float:
        """Binance USDT-M quantity is in coins, so contract_size = 1."""
        return 1.0
