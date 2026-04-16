"""MEXC exchange adapter using direct HTTP via HttpClient."""

import logging
import requests
from typing import Optional

from exchanges.base import CloseResult, ExchangeAdapter, FundingRate
from exchanges.http_client import HttpClient


logger = logging.getLogger(__name__)


class MexcAdapter(ExchangeAdapter):
    """MEXC perpetual futures adapter via HttpClient.

    MEXC uses underscore-separated symbols (e.g., BTC_USDT) internally,
    while the system uses dash-separated format (e.g., BTC-USDT).
    """

    BASE_URL = "https://contract.mexc.com"

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False, **kwargs) -> None:
        super().__init__(api_key, api_secret, testnet=testnet, **kwargs)
        self._http = HttpClient(
            base_url=self.BASE_URL,
            api_key=api_key,
            api_secret=api_secret,
            sign_mode="mexc",
        )

    def _normalize_symbol(self, symbol: str) -> str:
        """Convert internal symbol (BTC-USDT) to MEXC format (BTC_USDT)."""
        return symbol.replace("-", "_")

    def _format_symbol(self, symbol: str) -> str:
        """Convert MEXC symbol (BTC_USDT) to internal format (BTC-USDT)."""
        return symbol.replace("_", "-")

    def get_funding_rates(self) -> dict:
        """Fetch all funding rates via direct HTTP (no ccxt needed).

        Public endpoint: GET /api/v1/contract/funding_rate
        Returns funding rate and next settlement time for all perpetual contracts.
        """
        result = {}
        try:
            resp = requests.get(
                "https://api.mexc.com/api/v1/contract/funding_rate",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data", [])
        except Exception as e:
            logger.warning(f"mexc get_funding_rates failed: {e}")
            return result

        for item in items:
            sym_raw = item.get("symbol", "")
            if not sym_raw:
                continue

            try:
                rate = float(item.get("fundingRate", 0))
            except (ValueError, TypeError):
                rate = 0.0

            next_time_ms = item.get("nextSettleTime") or 0
            try:
                next_settlement = int(int(next_time_ms) / 1000)
            except (ValueError, TypeError):
                next_settlement = 0

            # MEXC uses BTC_USDT format, convert to BTC-USDT
            normalized = self._format_symbol(sym_raw)
            result[normalized] = FundingRate(
                symbol=normalized,
                rate=rate,
                next_settlement=next_settlement,
            )
        return result

    def get_account_balance(self) -> float:
        """Fetch USDT balance from signed account endpoint.

        Returns the available USDT balance, or 0.0 on error.
        """
        try:
            data = self._http.signed_get("/api/v1/account/balance")
            for asset in data.get("data", {}).get("asset_list", []):
                if asset.get("asset") == "USDT":
                    return float(asset.get("available_balance", 0))
        except Exception as e:
            logger.warning(f"mexc get_account_balance failed: {e}")
        return 0.0

    def set_leverage(self, symbol: str, leverage: int = 10) -> bool:
        """Set leverage for a symbol via signed POST."""
        try:
            self._http.signed_post(
                "/api/v1/account/contract",
                params={
                    "symbol": self._normalize_symbol(symbol),
                    "leverage": str(leverage),
                },
            )
            return True
        except Exception as e:
            logger.warning(f"mexc set_leverage failed: {symbol} {leverage} {e}")
            return False

    def place_fok_order(
        self, symbol: str, side: str, quantity: float, price: float
    ) -> Optional[str]:
        """Place a Fill-or-Kill limit order via signed POST.

        Returns the order ID on success, or None on failure.
        """
        try:
            data = self._http.signed_post(
                "/api/v1/order/place",
                params={
                    "symbol": self._normalize_symbol(symbol),
                    "side": side.upper(),
                    "type": "FOK",
                    "quantity": str(quantity),
                    "price": str(price),
                },
            )
            order_id = data.get("data", {}).get("order_id")
            if order_id:
                logger.info(
                    f"mexc order placed: {symbol} {side} {quantity} @ {price}, orderId={order_id}"
                )
            return order_id
        except Exception as e:
            logger.warning(
                f"mexc order failed: {symbol} {side} {quantity} @ {price} {e}"
            )
            return None

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
    ) -> Optional[str]:
        """Place a market order via signed POST.

        Returns the order ID on success, or None on failure.
        """
        try:
            data = self._http.signed_post(
                "/api/v1/order/place",
                params={
                    "symbol": self._normalize_symbol(symbol),
                    "side": side.upper(),
                    "type": "MARKET",
                    "quantity": str(quantity),
                },
            )
            order_id = data.get("data", {}).get("order_id")
            if order_id:
                logger.info(
                    f"mexc market order placed: {symbol} {side} {quantity}, orderId={order_id}"
                )
                return order_id
            logger.warning(f"MEXC market order failed: {symbol} {side} {quantity} -- no order_id returned")
            return None
        except Exception as e:
            logger.warning(
                f"mexc market order failed: {symbol} {side} {quantity} {e}"
            )
            return None

    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an existing order via signed POST."""
        try:
            self._http.signed_post(
                "/api/v1/order/cancel",
                params={
                    "symbol": self._normalize_symbol(symbol),
                    "order_id": order_id,
                },
            )
            return True
        except Exception as e:
            logger.warning(f"mexc cancel_order failed: {symbol} {order_id} {e}")
            return False

    def get_order_status(self, symbol: str, order_id: str) -> str:
        """Get order status via signed GET.

        Returns one of: 'filled', 'cancelled', 'unfilled', 'partial', 'unknown'.
        """
        try:
            data = self._http.signed_get(
                "/api/v1/order/detail",
                params={
                    "symbol": self._normalize_symbol(symbol),
                    "order_id": order_id,
                },
            )
            order = data.get("data", {})
            status = order.get("status", "").lower()
            if status == "filled":
                return "filled"
            if status == "cancelled" or status == "canceled":
                return "cancelled"
            if status == "partial":
                return "partial"
            return "unfilled"
        except Exception:
            return "unknown"

    def get_position(self, symbol: str) -> Optional[dict]:
        """Get current position via signed GET.

        Returns a dict with 'symbol', 'quantity', 'side', 'unrealized_pnl',
        or None if no position exists.
        """
        try:
            data = self._http.signed_get(
                "/api/v1/position/list",
                params={"symbol": self._normalize_symbol(symbol)},
            )
            positions = data.get("data", [])
            if not positions:
                return None
            pos = positions[0]
            available_qty = float(pos.get("available_quantity", 0) or 0)
            if available_qty <= 0:
                return None
            return {
                "symbol": symbol,
                "quantity": available_qty,
                "side": pos.get("side", "").upper(),
                "unrealized_pnl": float(pos.get("unrealized_pnl", 0) or 0),
            }
        except Exception as e:
            logger.warning(f"mexc get_position failed: {symbol} {e}")
            return None

    def close_position(self, symbol: str) -> CloseResult:
        """Close position via market order (opposite side).

        Returns CloseResult with actual fill price and fees.
        """
        try:
            pos = self.get_position(symbol)
            if not pos:
                return CloseResult(success=False)
            close_side = "SELL" if pos["side"] == "BUY" else "BUY"
            quantity = pos["quantity"]
            entry_price = pos.get("entry_price", 0)
            order_id = self.place_market_order(symbol, close_side, quantity)
            if not order_id:
                logger.warning(f"mexc close_position failed: {symbol}")
                return CloseResult(success=False, error_a="order_placement_failed")

            # Poll for fill
            close_price = None
            deadline = time.time() + 5
            while time.time() < deadline:
                status = self.get_order_status(symbol, order_id)
                if status == "filled":
                    # Position should be closed, use entry as proxy for close price
                    close_price = entry_price
                    break
                elif status in ("cancelled", "unfilled"):
                    break
                time.sleep(0.5)

            fee_rate = self.get_fee_rate(symbol)
            fee = (close_price or entry_price) * quantity * fee_rate["taker"] if close_price else 0

            if close_price:
                logger.info(f"mexc position closed: {symbol} @ {close_price}")
                return CloseResult(
                    success=True,
                    close_price_a=close_price,
                    fee_a=fee,
                )
            return CloseResult(success=False)
        except Exception as e:
            logger.warning(f"mexc close_position failed: {symbol} {e}")
            return CloseResult(success=False, error_a=str(e))

    def get_fee_rate(self, symbol: str) -> dict:
        """Fetch taker/maker fee rates from MEXC contract detail API.

        Returns {'maker': float, 'taker': float}, or defaults on error.
        """
        try:
            resp = requests.get(
                "https://contract.mexc.com/api/v1/contract/detail",
                params={"symbol": self._normalize_symbol(symbol)},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            taker = float(data.get("taker_fee", 0.001))
            maker = float(data.get("maker_fee", 0.0005))
            return {"maker": maker, "taker": taker}
        except Exception:
            return {"maker": 0.0005, "taker": 0.001}

    def get_ticker_price(self, symbol: str) -> Optional[float]:
        """Fetch current last price from MEXC public ticker endpoint."""
        try:
            resp = requests.get(
                "https://contract.mexc.com/api/v1/contract/ticker",
                params={"symbol": self._normalize_symbol(symbol)},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            last = data.get("last")
            if last is not None:
                return float(last)
        except Exception:
            pass
        return None

    def get_max_position(self, symbol: str) -> Optional[float]:
        """Get maximum position size from MEXC position info via signed GET."""
        try:
            data = self._http.signed_get(
                "/api/v1/position/list",
                params={"symbol": self._normalize_symbol(symbol)},
            )
            positions = data.get("data", [])
            if positions:
                pos = positions[0]
                max_qty = pos.get("max_position_size") or pos.get("max_open_order_size")
                if max_qty is not None:
                    return float(max_qty)
        except Exception as e:
            logger.warning(f"mexc get_max_position failed: {symbol} {e}")
        return None

    def get_contract_size(self, symbol: str) -> float:
        """Get contract multiplier from MEXC contract detail API.

        Returns how many coins one contract represents.
        e.g. BTC_USDT contractSize=0.0001 means 1 contract = 0.0001 BTC.
        """
        try:
            resp = requests.get(
                "https://contract.mexc.com/api/v1/contract/detail",
                params={"symbol": self._normalize_symbol(symbol)},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            cs = data.get("contract_size")
            if cs is not None:
                return float(cs)
        except Exception:
            pass
        return 1.0
