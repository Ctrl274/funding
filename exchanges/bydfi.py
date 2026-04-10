"""
BYDFi 交易所适配器。
使用原生 requests，参考 bydfi-openapi.md 的签名规范。
Production: https://api.bydfi.com/api
Test:       https://api.bydtms.com/api
"""
import time
import hmac
import hashlib
import json
import requests
from typing import Dict, Optional
from .base import ExchangeAdapter, FundingRate


class BydfiAdapter(ExchangeAdapter):
    NAME = "bydfi"

    BASE_URL = "https://api.bydfi.com/api"
    TEST_URL = "https://api.bydtms.com/api"

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        super().__init__(api_key, api_secret, testnet)
        self._base_url = self.TEST_URL if testnet else self.BASE_URL

    def _sign(self, timestamp: str, params_str: str) -> str:
        """HMAC-SHA256(apiKey + timestamp + paramsStr/body, secretKey)"""
        msg = self._api_key + timestamp + params_str
        return hmac.new(
            self._api_secret.encode(), msg.encode(), hashlib.sha256
        ).hexdigest()

    def _headers(self, body: str = "") -> Dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        signature = self._sign(timestamp, body)
        return {
            "X-API-KEY": self._api_key,
            "X-API-TIMESTAMP": timestamp,
            "X-API-SIGNATURE": signature,
            "Content-Type": "application/json",
        }

    def get_funding_rates(self) -> Dict[str, FundingRate]:
        """
        Fetch funding rates via public API endpoints.

        Step 1: GET /v1/fapi/market/ticker/price — get all USDT symbols (no auth)
        Step 2: Concurrent fetch funding rates for all symbols via ThreadPoolExecutor.
        """
        result: Dict[str, FundingRate] = {}

        # Step 1: get all USDT perpetual symbols
        try:
            ticker_resp = requests.get(
                f"{self._base_url}/v1/fapi/market/ticker/price",
                timeout=10,
            )
            ticker_resp.raise_for_status()
            ticker_data = ticker_resp.json()
        except Exception:
            return result

        all_usdt = [
            item["symbol"]
            for item in ticker_data.get("data", [])
            if item.get("symbol", "").endswith("USDT")
        ]
        if not all_usdt:
            return result

        # Step 2: concurrent fetch all symbols
        def _fetch_one(sym: str) -> tuple:
            try:
                resp = requests.get(
                    f"{self._base_url}/v1/fapi/market/funding_rate",
                    params={"symbol": sym},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") != 200:
                    return sym, None
                item = data.get("data", {})
                return sym, FundingRate(
                    symbol=sym,
                    rate=float(item.get("lastFundingRate", "0")),
                    next_settlement=int(item.get("nextFundingTime", 0)) // 1000
                    if item.get("nextFundingTime")
                    else 0,
                )
            except Exception:
                return sym, None

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=20) as pool:
            for sym, fr in pool.map(_fetch_one, all_usdt):
                if fr:
                    result[sym] = fr

        return result

    def get_account_balance(self) -> float:
        """GET /swap/account/balance"""
        url = f"{self._base_url}/swap/account/balance"
        headers = self._headers()
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("data", []):
            if item.get("coin") == "USDT":
                return float(item.get("available", 0))
        return 0.0

    def set_leverage(self, symbol: str, leverage: int = 10) -> bool:
        """POST /swap/account/leverage"""
        url = f"{self._base_url}/swap/account/leverage"
        body = json.dumps(
            {"symbol": symbol, "leverage": str(leverage)},
            separators=(",", ":"),
        )
        headers = self._headers(body)
        resp = requests.post(url, headers=headers, data=body, timeout=10)
        return resp.status_code == 200

    def place_fok_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
    ) -> Optional[str]:
        """POST /swap/order/place — FOK 限价单"""
        import logging
        logger = logging.getLogger(__name__)

        url = f"{self._base_url}/swap/order/place"
        body_dict = {
            "symbol": symbol,
            "side": side.upper(),
            "orderType": "FOK",
            "quantity": str(int(quantity)),
            "price": str(price),
        }
        body = json.dumps(body_dict, separators=(",", ":"))
        headers = self._headers(body)
        resp = requests.post(url, headers=headers, data=body, timeout=10)
        data = resp.json()
        if resp.status_code == 200 and data.get("code") == 200:
            order_id = data.get("data", {}).get("orderId")
            if order_id:
                logger.info(f"{self.NAME} order placed: {symbol} {side} {quantity} @ {price}, orderId={order_id}")
            else:
                logger.warning(f"{self.NAME} order placed but no orderId returned: {symbol} {side} {quantity}")
            return order_id

        # Log the actual error
        err_code = data.get("code")
        err_msg = data.get("msg") or data.get("message") or data.get("error") or resp.text
        logger.warning(
            f"{self.NAME} order failed: {symbol} {side} {quantity} @ {price} "
            f"[code={err_code}] {err_msg}"
        )
        return None

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
    ) -> Optional[str]:
        """POST /swap/order/place — market order"""
        import logging
        logger = logging.getLogger(__name__)

        url = f"{self._base_url}/swap/order/place"
        body_dict = {
            "symbol": symbol,
            "side": side.upper(),
            "orderType": "MARKET",
            "quantity": str(int(quantity)),
        }
        body = json.dumps(body_dict, separators=(",", ":"))
        headers = self._headers(body)
        resp = requests.post(url, headers=headers, data=body, timeout=10)
        data = resp.json()
        if resp.status_code == 200 and data.get("code") == 200:
            order_id = data.get("data", {}).get("orderId")
            if order_id:
                logger.info(f"{self.NAME} market order placed: {symbol} {side} {quantity}, orderId={order_id}")
            return order_id

        err_code = data.get("code")
        err_msg = data.get("msg") or data.get("message") or data.get("error") or resp.text
        logger.warning(
            f"{self.NAME} market order failed: {symbol} {side} {quantity} "
            f"[code={err_code}] {err_msg}"
        )
        return None

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """POST /swap/order/cancel"""
        import logging
        logger = logging.getLogger(__name__)
        url = f"{self._base_url}/swap/order/cancel"
        body = json.dumps({"symbol": symbol, "orderId": order_id}, separators=(",", ":"))
        headers = self._headers(body)
        resp = requests.post(url, headers=headers, data=body, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"{self.NAME} cancel failed: {symbol} orderId={order_id} resp={resp.text}")
        return resp.status_code == 200

    def get_order_status(self, symbol: str, order_id: str) -> str:
        """GET /swap/order/info"""
        url = f"{self._base_url}/swap/order/info"
        params = f"orderId={order_id}&symbol={symbol}"
        headers = self._headers(params)
        resp = requests.get(f"{url}?{params}", headers=headers, timeout=10)
        if resp.status_code != 200:
            return "unfilled"
        return resp.json().get("data", {}).get("status", "unfilled").lower()

    def get_position(self, symbol: str) -> Optional[Dict]:
        """GET /swap/position/info"""
        url = f"{self._base_url}/swap/position/info"
        params = f"symbol={symbol}"
        headers = self._headers(params)
        resp = requests.get(f"{url}?{params}", headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        pos = resp.json().get("data", {})
        qty = float(pos.get("openOrderQuantity", 0))
        if qty == 0:
            return None
        return {
            "side": pos.get("side", "BUY").upper(),
            "quantity": qty,
            "entry_price": float(pos.get("entryPrice", 0)),
        }

    def close_position(self, symbol: str) -> bool:
        """POST /swap/position/close"""
        url = f"{self._base_url}/swap/position/close"
        body = json.dumps({"symbol": symbol}, separators=(",", ":"))
        headers = self._headers(body)
        resp = requests.post(url, headers=headers, data=body, timeout=10)
        return resp.status_code == 200

    def get_fee_rate(self, symbol: str) -> Dict[str, float]:
        """从 exchangeInfo 获取"""
        url = f"{self._base_url}/swap/public/q/contracts"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return {"maker": 0.0003, "taker": 0.0005}
        data = resp.json()
        for item in data.get("data", []):
            if item.get("symbol") == symbol:
                return {
                    "maker": float(item.get("makerFee", 0.0003)),
                    "taker": float(item.get("takerFee", 0.0005)),
                }
        return {"maker": 0.0003, "taker": 0.0005}

    def get_ticker_price(self, symbol: str) -> Optional[float]:
        """Fetch current last price from ticker endpoint."""
        try:
            resp = requests.get(
                f"{self._base_url}/v1/fapi/market/ticker/price",
                params={"symbol": symbol},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == 200 and data.get("data"):
                items = data["data"]
                if isinstance(items, list) and items:
                    return float(items[0].get("price", 0))
                elif isinstance(items, dict):
                    return float(items.get("price", 0))
            return None
        except Exception:
            return None

    def get_max_position(self, symbol: str) -> Optional[float]:
        """Get maximum position size from BYDFi position info."""
        try:
            url = f"{self._base_url}/swap/position/info"
            params = f"symbol={symbol}"
            headers = self._headers(params)
            resp = requests.get(f"{url}?{params}", headers=headers, timeout=10)
            if resp.status_code == 200:
                pos = resp.json().get("data", {})
                max_qty = pos.get("maxOpenOrderSize") or pos.get("maxPositionSize")
                if max_qty is not None:
                    return float(max_qty)
            return None
        except Exception:
            return None

    def get_contract_size(self, symbol: str) -> float:
        """Get contract multiplier from BYDFi contracts endpoint.

        Returns how many coins one contract represents.
        Requires authentication via /swap/public/q/contracts.
        """
        try:
            url = f"{self._base_url}/swap/public/q/contracts"
            headers = self._headers()
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", []):
                    if item.get("symbol") == symbol:
                        m = item.get("multiplier")
                        if m is not None:
                            return float(m)
        except Exception:
            pass
        return 1.0
