"""
BYDFi exchange adapter.
Uses native requests, following bydfi-openapi.md signature spec.
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
        msg = self.api_key + timestamp + params_str
        return hmac.new(
            self.api_secret.encode(),
            msg.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _headers(self, body: str = "") -> Dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        signature = self._sign(timestamp, body)
        return {
            "X-API-KEY": self.api_key,
            "X-API-TIMESTAMP": timestamp,
            "X-API-SIGNATURE": signature,
            "Content-Type": "application/json",
        }

    def get_funding_rates(self) -> Dict[str, FundingRate]:
        url = f"{self._base_url}/swap/public/q/contracts"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        result = {}
        for item in data.get("data", []):
            sym = item.get("symbol", "")
            if not sym or "-USDT" not in sym:
                continue
            rate = float(item.get("fundingRate", "0"))
            next_time = item.get("nextFundingTime", 0)
            result[sym] = FundingRate(
                symbol=sym,
                rate=rate,
                next_settlement=next_time / 1000 if next_time else 0,
            )
        return result

    def get_account_balance(self) -> float:
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
        url = f"{self._base_url}/swap/account/leverage"
        body = json.dumps({"symbol": symbol, "leverage": str(leverage)}, separators=(",", ":"))
        headers = self._headers(body)
        resp = requests.post(url, headers=headers, data=body, timeout=10)
        return resp.status_code == 200

    def place_fok_order(self, symbol: str, side: str, quantity: float, price: float) -> Optional[str]:
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
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", {}).get("orderId")
        return None

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        url = f"{self._base_url}/swap/order/cancel"
        body = json.dumps({"symbol": symbol, "orderId": order_id}, separators=(",", ":"))
        headers = self._headers(body)
        resp = requests.post(url, headers=headers, data=body, timeout=10)
        return resp.status_code == 200

    def get_order_status(self, symbol: str, order_id: str) -> str:
        url = f"{self._base_url}/swap/order/info"
        params = f"orderId={order_id}&symbol={symbol}"
        headers = self._headers(params)
        resp = requests.get(f"{url}?{params}", headers=headers, timeout=10)
        if resp.status_code != 200:
            return "unfilled"
        data = resp.json()
        status = data.get("data", {}).get("status", "")
        return status.lower()

    def get_position(self, symbol: str) -> Optional[Dict]:
        url = f"{self._base_url}/swap/position/info"
        params = f"symbol={symbol}"
        headers = self._headers(params)
        resp = requests.get(f"{url}?{params}", headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        pos = data.get("data", {})
        qty = float(pos.get("openOrderQuantity", 0))
        if qty == 0:
            return None
        return {
            "side": pos.get("side", "BUY").upper(),
            "quantity": qty,
            "entry_price": float(pos.get("entryPrice", 0)),
        }

    def close_position(self, symbol: str) -> bool:
        url = f"{self._base_url}/swap/position/close"
        body = json.dumps({"symbol": symbol}, separators=(",", ":"))
        headers = self._headers(body)
        resp = requests.post(url, headers=headers, data=body, timeout=10)
        return resp.status_code == 200

    def get_fee_rate(self, symbol: str) -> Dict[str, float]:
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
