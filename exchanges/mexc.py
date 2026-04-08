"""MEXC exchange adapter using ccxt."""

import ccxt
import requests
from typing import Optional

from exchanges.base import ExchangeAdapter, FundingRate


class MexcAdapter(ExchangeAdapter):
    """MEXC perpetual futures adapter via ccxt.

    MEXC uses underscore-separated symbols (e.g., BTC_USDT) internally,
    while the system uses dash-separated format (e.g., BTC-USDT).
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False, **kwargs) -> None:
        super().__init__(api_key, api_secret, testnet=testnet, **kwargs)
        self._exchange = ccxt.mexc(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "options": {"defaultType": "swap"},
            }
        )

    def _normalize_symbol(self, symbol: str) -> str:
        """Convert internal symbol (BTC-USDT) to MEXC format (BTC_USDT)."""
        return symbol.replace("-", "_")

    def _format_symbol(self, symbol: str) -> str:
        """Convert MEXC symbol (BTC_USDT) to internal format (BTC-USDT)."""
        return symbol.replace("_", "-")

    def get_funding_rates(self) -> dict:
        """Fetch all funding rates via direct HTTP (MEXC ccxt doesn't support fetchFundingRates).

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
        except Exception:
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
        balance = self._exchange.fetch_balance({"type": "swap"})
        usdt_balance = balance.get("USDT", {})
        free = usdt_balance.get("free", "0")
        return float(free)

    def set_leverage(self, symbol: str, leverage: int) -> None:
        self._exchange.set_leverage(leverage, self._normalize_symbol(symbol))

    def place_fok_order(
        self, symbol: str, side: str, quantity: float, price: float
    ) -> str:
        result = self._exchange.create_order(
            symbol=self._normalize_symbol(symbol),
            type="limit",
            side=side.lower(),
            amount=quantity,
            price=price,
            params={"timeInForce": "IOC"},
        )
        return result["id"]

    def cancel_order(self, symbol: str, order_id: str) -> None:
        self._exchange.cancel_order(
            order_id, self._normalize_symbol(symbol)
        )

    def get_order_status(self, symbol: str, order_id: str) -> str:
        order = self._exchange.fetch_order(
            order_id, self._normalize_symbol(symbol)
        )
        if order["status"] == "closed":
            return "filled"
        return order["status"]

    def get_position(self, symbol: str) -> dict:
        positions = self._exchange.fetch_positions([self._normalize_symbol(symbol)])
        if not positions:
            return {}
        pos = positions[0]
        return {
            "symbol": symbol,
            "size": float(pos.get("contracts", 0) or 0),
            "side": pos.get("side", ""),
            "unrealized_pnl": float(pos.get("unrealizedPnl", 0) or 0),
        }

    def close_position(self, symbol: str) -> None:
        self._exchange.close_position(self._normalize_symbol(symbol))

    def get_fee_rate(self, symbol: str) -> float:
        markets = self._exchange.markets
        normalized = self._normalize_symbol(symbol)
        if normalized in markets:
            return float(markets[normalized].get("taker", 0.001))
        return 0.001

    def get_ticker_price(self, symbol: str) -> Optional[float]:
        """Fetch current last price via ccxt fetch_ticker."""
        try:
            ticker = self._exchange.fetch_ticker(self._normalize_symbol(symbol))
            return float(ticker["last"])
        except Exception:
            return None

    def get_max_position(self, symbol: str) -> Optional[float]:
        """Get maximum position size from MEXC position info."""
        try:
            pos = self._exchange.fetch_position(self._normalize_symbol(symbol))
            if pos:
                info = pos.get("info", {})
                max_qty = info.get("maxOpenOrderSize") or info.get("maxPositionSize")
                if max_qty is not None:
                    return float(max_qty)
            return None
        except Exception:
            return None

    def get_contract_size(self, symbol: str) -> float:
        """Get contract multiplier from MEXC contract detail API.

        Returns how many coins one contract represents.
        e.g. BTC_USDT contractSize=0.0001 means 1 contract = 0.0001 BTC.
        """
        try:
            mexc_sym = self._normalize_symbol(symbol)
            resp = requests.get(
                "https://contract.mexc.com/api/v1/contract/detail",
                params={"symbol": mexc_sym},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            cs = data.get("contractSize")
            if cs is not None:
                return float(cs)
        except Exception:
            pass
        return 1.0
