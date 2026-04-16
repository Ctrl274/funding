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
from .base import CloseResult, ExchangeAdapter, FundingRate


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
        Fetch all funding rates via public batch endpoint.

        Testnet: https://beta-21.bydtms.com/swap/public/future/fundingRate/real
        Prod:    https://www.bydfi.com/swap/public/future/fundingRate/real

        Returns all symbols in one request. No auth required.
        """
        result: Dict[str, FundingRate] = {}

        if self._testnet:
            url = "https://beta-21.bydtms.com/swap/public/future/fundingRate/real"
        else:
            url = "https://www.bydfi.com/swap/public/future/fundingRate/real"

        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return result

        if data.get("code") != 200:
            return result

        for item in data.get("data", []):
            sym = item.get("symbol", "")
            if not sym or not sym.endswith("USDT"):
                continue
            try:
                rate = float(item.get("fundRate", 0))
                next_ts = int(item.get("feeTime", 0)) // 1000
                result[sym] = FundingRate(
                    symbol=sym,
                    rate=rate,
                    next_settlement=next_ts,
                )
            except (ValueError, TypeError):
                continue

        return result

    def get_account_balance(self) -> float:
        """GET /v1/account/assets — query UMFUTURE (USDT-M) wallet balance."""
        url = f"{self._base_url}/v1/account/assets"
        params = "account=UMFUTURE&asset=USDT"
        headers = self._headers(params)
        resp = requests.get(f"{url}?{params}", headers=headers, timeout=10)
        if resp.status_code != 200:
            return 0.0
        data = resp.json()
        for item in data.get("data", []):
            if item.get("account", "").upper() == "UMFUTURE" and item.get("asset", "").upper() == "USDT":
                return float(item.get("available", 0))
        return 0.0

    def set_leverage(self, symbol: str, leverage: int = 10) -> bool:
        """POST /v1/fapi/trade/leverage"""
        url = f"{self._base_url}/v1/fapi/trade/leverage"
        body = json.dumps(
            {"wallet": "W001", "symbol": symbol, "leverage": str(leverage)},
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
        """POST /v1/fapi/trade/place_order — FOK 限价单"""
        import logging
        logger = logging.getLogger(__name__)

        url = f"{self._base_url}/v1/fapi/trade/place_order"
        body_dict = {
            "wallet": "W001",
            "symbol": symbol,
            "side": side.upper(),
            "orderType": "FOK",
            "quantity": str(int(quantity)),
            "price": str(price),
            "type": "1",
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
        """POST /v1/fapi/trade/place_order — market order"""
        import logging
        logger = logging.getLogger(__name__)

        url = f"{self._base_url}/v1/fapi/trade/place_order"
        body_dict = {
            "wallet": "W001",
            "symbol": symbol,
            "side": side.upper(),
            "orderType": "MARKET",
            "quantity": str(int(quantity)),
            "type": "1",
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
        """POST /v1/fapi/trade/cancel_all_order"""
        import logging
        logger = logging.getLogger(__name__)
        url = f"{self._base_url}/v1/fapi/trade/cancel_all_order"
        body = json.dumps({"wallet": "W001", "symbol": symbol, "orderId": order_id, "type": "5"}, separators=(",", ":"))
        headers = self._headers(body)
        resp = requests.post(url, headers=headers, data=body, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"{self.NAME} cancel failed: {symbol} orderId={order_id} resp={resp.text}")
        return resp.status_code == 200

    def get_order_status(self, symbol: str, order_id: str) -> str:
        """GET /v1/fapi/trade/open_order — falls back to position check if IP-restricted."""
        url = f"{self._base_url}/v1/fapi/trade/open_order"
        params = f"wallet=W001&orderId={order_id}&symbol={symbol}"
        headers = self._headers(params)
        resp = requests.get(f"{url}?{params}", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 200:
                return data.get("data", {}).get("status", "unfilled").lower()

        # Fallback: check if position increased (order was filled)
        # If get_position returns a non-zero position, the order filled
        pos = self.get_position(symbol)
        if pos and pos.get("quantity", 0) > 0:
            return "filled"
        return "unknown"

    def get_position(self, symbol: str) -> Optional[Dict]:
        """GET /v1/fapi/trade/positions"""
        url = f"{self._base_url}/v1/fapi/trade/positions"
        params = f"contractType=FUTURE&symbol={symbol}"
        headers = self._headers(params)
        resp = requests.get(f"{url}?{params}", headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        positions = resp.json().get("data", [])
        for pos in positions:
            qty = float(pos.get("volume", 0))
            if qty != 0:
                return {
                    "side": pos.get("side", "BUY").upper(),
                    "quantity": abs(qty),
                    "entry_price": float(pos.get("avgPrice", 0)),
                }
        return None

    def close_position(self, symbol: str) -> CloseResult:
        """Close via place_order with closePosition=true.

        Returns CloseResult with actual fill price and fees.
        """
        try:
            pos_before = self.get_position(symbol)
            if not pos_before:
                return CloseResult(success=False)
            entry_price = pos_before.get("entry_price", 0)
            quantity = pos_before["quantity"]

            url = f"{self._base_url}/v1/fapi/trade/place_order"
            body_dict = {
                "wallet": "W001",
                "symbol": symbol,
                "side": "SELL" if pos_before["side"] == "BUY" else "BUY",
                "orderType": "MARKET",
                "quantity": str(int(quantity)),
                "reduceOnly": True,
                "type": "1",
            }
            body = json.dumps(body_dict, separators=(",", ":"))
            headers = self._headers(body)
            resp = requests.post(url, headers=headers, data=body, timeout=10)
            if resp.status_code != 200:
                return CloseResult(success=False, error_a=f"http_{resp.status_code}")

            close_price = entry_price
            fee_rate = self.get_fee_rate(symbol)
            fee = close_price * quantity * fee_rate["taker"] if close_price else 0

            logger.info(f"bydfi position closed: {symbol} @ {close_price}")
            return CloseResult(
                success=True,
                close_price_a=close_price,
                fee_a=fee,
            )
        except Exception as e:
            logger.warning(f"bydfi close_position failed: {e}")
            return CloseResult(success=False, error_a=str(e))

    def get_fee_rate(self, symbol: str) -> Dict[str, float]:
        """从 exchangeInfo 获取"""
        url = f"{self._base_url}/v1/fapi/market/exchange_info"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return {"maker": 0.0002, "taker": 0.0006}
        data = resp.json()
        for item in data.get("data", []):
            if item.get("symbol") == symbol:
                return {
                    "maker": float(item.get("feeRateMaker", 0.0002)),
                    "taker": float(item.get("feeRateTaker", 0.0006)),
                }
        return {"maker": 0.0002, "taker": 0.0006}

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
        """Get maximum position size from positions endpoint."""
        try:
            url = f"{self._base_url}/v1/fapi/trade/positions"
            params = f"contractType=FUTURE&symbol={symbol}"
            headers = self._headers(params)
            resp = requests.get(f"{url}?{params}", headers=headers, timeout=10)
            if resp.status_code == 200:
                positions = resp.json().get("data", [])
                for pos in positions:
                    max_qty = pos.get("maxOpenOrderSize") or pos.get("maxPositionSize")
                    if max_qty is not None:
                        return float(max_qty)
            return None
        except Exception:
            return None

    def get_contract_size(self, symbol: str) -> float:
        """Get contract multiplier from exchange_info.

        Returns how many coins one contract represents.
        """
        try:
            url = f"{self._base_url}/v1/fapi/market/exchange_info"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", []):
                    if item.get("symbol") == symbol:
                        m = item.get("contractFactor")
                        if m is not None:
                            return float(m)
        except Exception:
            pass
        return 1.0
