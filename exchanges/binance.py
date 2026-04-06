"""
Binance exchange adapter.
Uses ccxt, supports USDT-M perpetual futures.
"""
import ccxt
from typing import Dict, Optional
from .base import ExchangeAdapter, FundingRate


class BinanceAdapter(ExchangeAdapter):
    NAME = "binance"

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        super().__init__(api_key, api_secret, testnet)

        config = {"defaultType": "future"}
        if testnet:
            config["testnet"] = True

        self._client = ccxt.binance(config)
        if api_key and api_secret:
            self._client.apiKey = api_key
            self._client.secret = api_secret

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.replace("-", "")

    def _denormalize_symbol(self, ccxt_sym: str) -> Optional[str]:
        # Convert "BTC/USDT:USDT" to "BTC-USDT"
        if "/" not in ccxt_sym:
            return None
        base = ccxt_sym.split("/")[0]
        return f"{base}-USDT"

    def get_funding_rates(self) -> Dict[str, FundingRate]:
        raw = self._client.fetch_funding_rates()
        result = {}
        for ccxt_sym, data in raw.items():
            sym = self._denormalize_symbol(ccxt_sym)
            if sym is None:
                continue
            rate = float(data.get("lastFundingRate", 0))
            next_time = data.get("nextFundingTime", 0)
            result[sym] = FundingRate(
                symbol=sym,
                rate=rate,
                next_settlement=next_time / 1000 if next_time else 0,
            )
        return result

    def get_account_balance(self) -> float:
        balance = self._client.fetch_balance({"type": "future"})
        return float(balance.get("USDT", {}).get("free", 0))

    def set_leverage(self, symbol: str, leverage: int = 10) -> bool:
        try:
            self._client.set_leverage(leverage, self._normalize_symbol(symbol))
            return True
        except Exception:
            return False

    def place_fok_order(self, symbol: str, side: str, quantity: float, price: float) -> Optional[str]:
        try:
            order = self._client.create_order(
                symbol=self._normalize_symbol(symbol),
                type="limit",
                side=side.lower(),
                amount=quantity,
                price=price,
                params={"timeInForce": "IOC"},
            )
            return order.get("id")
        except Exception:
            return None

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        try:
            self._client.cancel_order(order_id, self._normalize_symbol(symbol))
            return True
        except Exception:
            return False

    def get_order_status(self, symbol: str, order_id: str) -> str:
        try:
            order = self._client.fetch_order(order_id, self._normalize_symbol(symbol))
            status = order.get("status", "")
            if status == "closed":
                filled = float(order.get("filled", 0))
                amount = float(order.get("amount", 1))
                if filled == amount:
                    return "filled"
                elif filled > 0:
                    return "partial"
                else:
                    return "cancelled"
            return "unfilled"
        except Exception:
            return "unfilled"

    def get_position(self, symbol: str) -> Optional[Dict]:
        try:
            pos = self._client.fetch_position(self._normalize_symbol(symbol))
            if pos and float(pos.get("contracts", 0)) > 0:
                return {
                    "side": "BUY" if pos.get("unrealizedPnl", 0) >= 0 else "SELL",
                    "quantity": float(pos["contracts"]),
                    "entry_price": float(pos.get("entryPrice", 0)),
                }
            return None
        except Exception:
            return None

    def close_position(self, symbol: str) -> bool:
        try:
            self._client.close_position(self._normalize_symbol(symbol))
            return True
        except Exception:
            return False

    def get_fee_rate(self, symbol: str) -> Dict[str, float]:
        return {"maker": 0.0002, "taker": 0.0004}
