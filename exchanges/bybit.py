"""
Bybit 交易所适配器。
使用直接 HTTP 调用获取资金费率（绕过 ccxt 的 bug），
其他操作使用 ccxt。
"""
import ccxt
import httpx
from typing import Dict, Optional
from .base import ExchangeAdapter, FundingRate


class BybitAdapter(ExchangeAdapter):
    NAME = "bybit"

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        super().__init__(api_key, api_secret, testnet)
        self._testnet = testnet
        self._client = ccxt.bybit({
            "apiKey": api_key,
            "secret": api_secret,
        })
        if testnet:
            self._client.set_sandbox_mode(True)
        self._funding_url = (
            "https://api-testnet.bybit.com/v5/market/tickers?category=linear"
            if testnet
            else "https://api.bybit.com/v5/market/tickers?category=linear"
        )

    def _normalize_symbol(self, symbol: str) -> str:
        """BTC-USDT -> BTC/USDT:USDT (ccxt linear perpetual format)."""
        base, quote = symbol.split("-", 1)
        return f"{base}/{quote}:{quote}"

    def _denormalize_symbol(self, ccxt_sym: str) -> str:
        """BTCUSDT -> BTC-USDT"""
        return ccxt_sym.replace("USDT", "-USDT")

    def get_funding_rates(self) -> Dict[str, FundingRate]:
        """Fetch funding rates via direct HTTP (bypasses ccxt bug).

        The public /v5/market/tickers endpoint requires no authentication.
        """
        result: Dict[str, FundingRate] = {}
        try:
            resp = httpx.get(self._funding_url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("result", {}).get("list", [])
        except Exception:
            return result

        for item in items:
            sym_raw = item.get("symbol", "")
            if not sym_raw.endswith("USDT"):
                continue
            rate_str = item.get("fundingRate", "0")
            next_time_ms_str = item.get("nextFundingTime") or "0"

            try:
                rate = float(rate_str)
            except (ValueError, TypeError):
                rate = 0.0

            try:
                next_settlement = int(int(next_time_ms_str) / 1000)
            except (ValueError, TypeError):
                next_settlement = 0
            sym = sym_raw.replace("USDT", "-USDT")

            result[sym] = FundingRate(
                symbol=sym,
                rate=rate,
                next_settlement=next_settlement,
            )
        return result

    def get_account_balance(self) -> float:
        balance = self._client.fetch_balance({"type": "swap", "coin": "USDT"})
        return float(balance.get("USDT", {}).get("free", 0))

    def set_leverage(self, symbol: str, leverage: int = 10) -> bool:
        try:
            self._client.set_leverage(leverage, self._normalize_symbol(symbol))
            return True
        except Exception:
            return False

    def place_fok_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
    ) -> Optional[str]:
        import logging
        logger = logging.getLogger(__name__)
        try:
            order = self._client.create_order(
                symbol=self._normalize_symbol(symbol),
                type="limit",
                side=side.lower(),
                amount=quantity,
                price=price,
                params={"timeInForce": "IOC"},
            )
            order_id = order.get("id")
            logger.info(f"{self.NAME} order placed: {symbol} {side} {quantity} @ {price}, orderId={order_id}")
            return order_id
        except Exception as e:
            logger.warning(f"{self.NAME} order failed: {symbol} {side} {quantity} @ {price} {e}")
            return None

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
    ) -> Optional[str]:
        import logging
        logger = logging.getLogger(__name__)
        try:
            order = self._client.create_order(
                symbol=self._normalize_symbol(symbol),
                type="market",
                side=side.lower(),
                amount=quantity,
            )
            order_id = order.get("id")
            logger.info(f"{self.NAME} market order placed: {symbol} {side} {quantity}, orderId={order_id}")
            return order_id
        except Exception as e:
            logger.warning(f"{self.NAME} market order failed: {symbol} {side} {quantity} {e}")
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
            filled = float(order.get("filled", 0))
            amount = float(order.get("amount", 1))
            if filled == amount:
                return "filled"
            elif filled > 0:
                return "partial"
            # IOC 订单撮合后 ccxt 可能返回 "open" 或 "new" 而非 "closed"
            status = order.get("status", "")
            if status in ("cancelled", "rejected", "canceled"):
                return "cancelled"
            if status == "closed":
                return "cancelled"
            return "unfilled"
        except Exception:
            return "unknown"

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
        """Close position via reverse market order (ccxt closePosition not supported for bybit)."""
        import logging
        logger = logging.getLogger(__name__)
        try:
            pos = self.get_position(symbol)
            if not pos:
                return False
            close_side = "sell" if pos["side"] == "BUY" else "buy"
            self._client.create_order(
                symbol=self._normalize_symbol(symbol),
                type="market",
                side=close_side,
                amount=pos["quantity"],
                params={"reduceOnly": True},
            )
            logger.info(f"bybit position closed: {symbol}")
            return True
        except Exception as e:
            logger.warning(f"bybit close_position failed: {symbol} {e}")
            return False

    def get_fee_rate(self, symbol: str) -> Dict[str, float]:
        try:
            markets = self._client.fetch_markets()
            for m in markets:
                if m.get("symbol", "").upper() == self._normalize_symbol(symbol).upper():
                    return {
                        "maker": float(m.get("maker", 0.0002)),
                        "taker": float(m.get("taker", 0.0005)),
                    }
        except Exception:
            pass
        return {"maker": 0.0002, "taker": 0.0005}

    def get_ticker_price(self, symbol: str) -> Optional[float]:
        """Fetch current last price via ccxt fetch_ticker."""
        try:
            ticker = self._client.fetch_ticker(self._normalize_symbol(symbol))
            return float(ticker["last"])
        except Exception:
            return None

    def get_max_position(self, symbol: str) -> Optional[float]:
        """Get maximum position size from Bybit position info."""
        try:
            pos = self._client.fetch_position(self._normalize_symbol(symbol))
            if pos:
                return float(pos.get("info", {}).get("maxPositionSize", 0)) or None
            return None
        except Exception:
            return None

    def get_contract_size(self, symbol: str) -> float:
        """Bybit USDT-M quantity is in coins, so contract_size = 1."""
        return 1.0
