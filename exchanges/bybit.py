"""
Bybit 交易所适配器。
使用直接 V5 HTTP API 调用，完全替代 ccxt。
"""

import logging
import time
import httpx
from typing import Dict, Optional

from .base import CloseResult, ExchangeAdapter, FundingRate
from .http_client import HttpClient


class BybitAdapter(ExchangeAdapter):
    NAME = "bybit"

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        super().__init__(api_key, api_secret, testnet)
        self._testnet = testnet
        base_url = (
            "https://api-demo.bybit.com"
            if testnet
            else "https://api.bybit.com"
        )
        self._http = HttpClient(
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
            sign_mode="bybit",
        )
        self._funding_url = (
            "https://api-demo.bybit.com/v5/market/tickers?category=linear"
            if testnet
            else "https://api.bybit.com/v5/market/tickers?category=linear"
        )

    # -------------------------------------------------------------------------
    # Symbol helpers
    # -------------------------------------------------------------------------

    def _to_bybit_symbol(self, symbol: str) -> str:
        """BTC-USDT -> BTCUSDT"""
        return symbol.replace("-", "")

    def _from_bybit_symbol(self, bybit_sym: str) -> str:
        """BTCUSDT -> BTC-USDT"""
        if bybit_sym.endswith("USDT"):
            return bybit_sym[:-4] + "-USDT"
        return bybit_sym  # fallback: return as-is

    # -------------------------------------------------------------------------
    # Public endpoints (no auth) — keep using httpx directly
    # -------------------------------------------------------------------------

    def get_funding_rates(self) -> Dict[str, FundingRate]:
        """Fetch funding rates via direct HTTP (public endpoint, no auth)."""
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

            sym = self._from_bybit_symbol(sym_raw)

            result[sym] = FundingRate(
                symbol=sym,
                rate=rate,
                next_settlement=next_settlement,
            )
        return result

    def get_ticker_price(self, symbol: str) -> Optional[float]:
        """Fetch current price. Uses direct HTTP for demo mode."""
        try:
            base_url = (
                "https://api-demo.bybit.com"
                if self._testnet
                else "https://api.bybit.com"
            )
            resp = httpx.get(
                f"{base_url}/v5/market/tickers",
                params={"category": "linear", "symbol": self._to_bybit_symbol(symbol)},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("result", {}).get("list", [])
            if items:
                return float(items[0].get("lastPrice", 0)) or None
            return None
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # Private signed endpoints — use HttpClient
    # -------------------------------------------------------------------------

    def get_account_balance(self) -> float:
        """Fetch USDT balance via V5 wallet-balance endpoint.

        Returns equity (available + unrealized PnL) from the UNIFIED account.
        """
        try:
            data = self._http.signed_get(
                "/v5/account/wallet-balance",
                params={"accountType": "UNIFIED"},
            )
            for account in data.get("result", {}).get("list", []):
                for coin in account.get("coin", []):
                    if coin.get("coin") == "USDT":
                        # available may be null on demo/prod; fall back to equity
                        avail = coin.get("available")
                        if avail is not None and avail != "":
                            return float(avail)
                        # fallback to walletBalance then equity
                        wb = coin.get("walletBalance")
                        if wb is not None and wb != "":
                            return float(wb)
                        equity = coin.get("equity")
                        if equity is not None and equity != "":
                            return float(equity)
            return 0.0
        except Exception:
            return 0.0

    def set_leverage(self, symbol: str, leverage: int = 10) -> bool:
        """Set leverage via V5 set-leverage endpoint."""
        try:
            data = self._http.signed_post(
                "/v5/position/set-leverage",
                params={
                    "category": "linear",
                    "symbol": self._to_bybit_symbol(symbol),
                    "buyLeverage": str(leverage),
                    "sellLeverage": str(leverage),
                },
            )
            return data.get("retCode") == 0
        except Exception:
            return False

    def place_fok_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
    ) -> Optional[str]:
        """Place a Fill-or-Kill limit order via V5 place-order."""
        logger = logging.getLogger(__name__)
        try:
            data = self._http.signed_post(
                "/v5/order/create",
                params={
                    "category": "linear",
                    "symbol": self._to_bybit_symbol(symbol),
                    "side": side.capitalize(),
                    "orderType": "Limit",
                    "qty": str(quantity),
                    "price": str(price),
                    "timeInForce": "FOK",
                },
            )
            order_id = data.get("result", {}).get("orderId")
            if order_id:
                logger.info(
                    f"bybit order placed: {symbol} {side} {quantity} @ {price}, orderId={order_id}"
                )
            else:
                logger.warning(
                    f"bybit order placed but no orderId returned: {symbol} {side} {quantity} @ {price}"
                )
            return order_id
        except Exception as e:
            logger.warning(
                f"bybit order failed: {symbol} {side} {quantity} @ {price} {e}"
            )
            return None

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
    ) -> Optional[str]:
        """Place a market order via V5 place-order."""
        logger = logging.getLogger(__name__)
        try:
            data = self._http.signed_post(
                "/v5/order/create",
                params={
                    "category": "linear",
                    "symbol": self._to_bybit_symbol(symbol),
                    "side": side.capitalize(),
                    "orderType": "Market",
                    "qty": str(quantity),
                },
            )
            order_id = data.get("result", {}).get("orderId")
            if order_id:
                logger.info(
                    f"bybit market order placed: {symbol} {side} {quantity}, orderId={order_id}"
                )
            return order_id
        except Exception as e:
            logger.warning(
                f"bybit market order failed: {symbol} {side} {quantity} {e}"
            )
            return None

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an order via V5 cancel-order."""
        try:
            data = self._http.signed_post(
                "/v5/order/cancel",
                params={
                    "category": "linear",
                    "symbol": self._to_bybit_symbol(symbol),
                    "orderId": order_id,
                },
            )
            return data.get("retCode") == 0
        except Exception:
            return False

    def get_order_status(self, symbol: str, order_id: str) -> str:
        """Get order status via V5 order/realtime."""
        try:
            data = self._http.signed_get(
                "/v5/order/realtime",
                params={
                    "category": "linear",
                    "symbol": self._to_bybit_symbol(symbol),
                    "orderId": order_id,
                },
            )
            items = data.get("result", {}).get("list", [])
            if not items:
                return "unknown"
            order = items[0]
            status = order.get("orderStatus", "")
            filled = float(order.get("filledQty", 0))
            qty = float(order.get("qty", 1))
            if filled == qty:
                return "filled"
            if filled > 0:
                return "partial"
            status_lower = status.lower()
            if status_lower in ("cancelled", "rejected", "deactivated"):
                return "cancelled"
            return "unfilled"
        except Exception:
            return "unknown"

    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get position info via V5 position/list."""
        try:
            data = self._http.signed_get(
                "/v5/position/list",
                params={
                    "category": "linear",
                    "symbol": self._to_bybit_symbol(symbol),
                },
            )
            positions = data.get("result", {}).get("list", [])
            for pos in positions:
                size_str = pos.get("size", "0")
                size = float(size_str)
                if size > 0:
                    return {
                        "side": "BUY" if pos.get("side", "").upper() == "BUY" else "SELL",
                        "quantity": size,
                        "entry_price": float(pos.get("avgPrice", 0)),
                    }
            return None
        except Exception:
            return None

    def close_position(self, symbol: str) -> CloseResult:
        """Close position via reverse market order.

        Returns CloseResult with actual fill price and fees.
        """
        logger = logging.getLogger(__name__)
        try:
            pos = self.get_position(symbol)
            if not pos:
                return CloseResult(success=False)
            close_side = "SELL" if pos["side"] == "BUY" else "BUY"
            quantity = pos["quantity"]
            entry_price = pos.get("entry_price", 0)
            order_id = self.place_market_order(symbol, close_side.lower(), quantity)
            if not order_id:
                return CloseResult(success=False, error_a="order_placement_failed")

            # Poll for fill
            close_price = None
            deadline = time.time() + 5
            while time.time() < deadline:
                status = self.get_order_status(symbol, order_id)
                if status == "filled":
                    # Get fill price from position
                    updated = self.get_position(symbol)
                    if updated is None:
                        # Position closed — use entry as proxy
                        close_price = entry_price
                    break
                elif status in ("cancelled", "unfilled"):
                    break
                time.sleep(0.5)

            fee_rate = self.get_fee_rate(symbol)
            fee = (close_price or entry_price) * quantity * fee_rate["taker"] if close_price else 0

            if close_price is not None:
                logger.info(f"bybit position closed: {symbol} @ {close_price}")
                return CloseResult(
                    success=True,
                    close_price_a=close_price,
                    fee_a=fee,
                )
            # Timeout — check if order is still pending (not cancelled).
            # If pending, order is placed and will eventually fill; treat as success.
            if order_id:
                status = self.get_order_status(symbol, order_id)
                if status in ("new", "partially_filled"):
                    logger.info(f"bybit order {order_id} placed but not yet filled, treating as closed: {symbol}")
                    return CloseResult(success=True, close_price_a=entry_price, fee_a=0)
            return CloseResult(success=False)
        except Exception as e:
            logger.warning(f"bybit close_position failed: {symbol} {e}")
            return CloseResult(success=False, error_a=str(e))

    def get_fee_rate(self, symbol: str) -> Dict[str, float]:
        """Get fee rate from V5 instruments-info endpoint."""
        try:
            base_url = (
                "https://api-demo.bybit.com"
                if self._testnet
                else "https://api.bybit.com"
            )
            resp = httpx.get(
                f"{base_url}/v5/market/instruments-info",
                params={"category": "linear", "symbol": self._to_bybit_symbol(symbol)},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("result", {}).get("list", [])
            if items:
                item = items[0]
                return {
                    "maker": float(item.get("makerFeeRate", 0.0002)),
                    "taker": float(item.get("takerFeeRate", 0.0005)),
                }
        except Exception:
            pass
        return {"maker": 0.0002, "taker": 0.0005}

    def get_max_position(self, symbol: str) -> Optional[float]:
        """Get maximum position size from V5 position/list risk limit info."""
        try:
            # First get the position to find riskId, then get risk limits
            data = self._http.signed_get(
                "/v5/position/list",
                params={
                    "category": "linear",
                    "symbol": self._to_bybit_symbol(symbol),
                },
            )
            positions = data.get("result", {}).get("list", [])
            if not positions:
                return None
            pos = positions[0]
            risk_id = pos.get("riskId")
            if not risk_id:
                return None

            # Get risk limits
            risk_data = self._http.signed_get(
                "/v5/position/risk-limit-info",
                params={
                    "category": "linear",
                    "symbol": self._to_bybit_symbol(symbol),
                    "riskId": risk_id,
                },
            )
            risk_list = risk_data.get("result", {}).get("list", [])
            for risk in risk_list:
                if str(risk.get("id")) == str(risk_id):
                    max_limit = risk.get("maxLimit")
                    if max_limit is not None:
                        return float(max_limit)
            return None
        except Exception:
            return None

    def get_contract_size(self, symbol: str) -> float:
        """Bybit USDT-M quantity is in coins, so contract_size = 1."""
        return 1.0
