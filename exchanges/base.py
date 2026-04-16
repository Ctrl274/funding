"""Base classes for exchange adapters in the funding arbitrage system."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class FundingRate:
    """Represents a funding rate for a symbol on a single exchange."""

    symbol: str
    rate: float
    next_settlement: int

    @property
    def rate_percent(self) -> float:
        """Return the funding rate as a percentage."""
        return self.rate * 100


@dataclass
class CloseResult:
    """Position close result with actual PnL."""
    success: bool
    close_price_a: Optional[float] = None  # actual fill price on exchange A
    close_price_b: Optional[float] = None  # actual fill price on exchange B
    fee_a: Optional[float] = None          # trading fee on exchange A
    fee_b: Optional[float] = None          # trading fee on exchange B
    pnl: Optional[float] = None           # actual realized PnL (after fees)
    error_a: Optional[str] = None
    error_b: Optional[str] = None


@dataclass(frozen=True)
class SymbolFunding:
    """Represents the funding rate comparison between two exchanges for a symbol."""

    symbol: str
    exchange_a: str
    exchange_b: str
    rate_a: float
    rate_b: float

    @property
    def rate_diff(self) -> float:
        """Return the absolute difference between the two rates."""
        return abs(self.rate_a - self.rate_b)

    @property
    def rate_diff_percent(self) -> float:
        """Return the rate difference as a percentage."""
        return self.rate_diff * 100

    @property
    def high_exchange(self) -> str:
        """Return the exchange with the higher funding rate."""
        if self.rate_a >= self.rate_b:
            return self.exchange_a
        return self.exchange_b

    @property
    def low_exchange(self) -> str:
        """Return the exchange with the lower funding rate."""
        if self.rate_a < self.rate_b:
            return self.exchange_a
        return self.exchange_b

    @property
    def direction(self) -> Dict[str, str]:
        """Return the recommended trade direction.

        Go long on the exchange with the higher funding rate.
        Go short on the exchange with the lower funding rate.
        """
        return {
            "long": self.high_exchange,
            "short": self.low_exchange,
        }


class ExchangeAdapter(ABC):
    """Abstract base class for exchange adapters.

    Each exchange implementation must inherit from this class and
    implement all abstract methods.
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = False, **kwargs: Any) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._testnet = testnet

    @abstractmethod
    def get_funding_rates(self) -> Dict[str, FundingRate]:
        """Fetch current funding rates for all symbols. Returns {symbol: FundingRate}."""

    @abstractmethod
    def get_account_balance(self) -> float:
        """Fetch USDT balance."""

    @abstractmethod
    def set_leverage(self, symbol: str, leverage: int = 10) -> bool:
        """Set leverage for a symbol."""

    @abstractmethod
    def place_fok_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
    ) -> Optional[str]:
        """Place a Fill-or-Kill order. Returns order ID or None."""

    @abstractmethod
    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
    ) -> Optional[str]:
        """Place a market order. Returns order ID or None."""

    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an existing order."""

    @abstractmethod
    def get_order_status(self, symbol: str, order_id: str) -> str:
        """Get order status. Returns 'filled'|'cancelled'|'unfilled'|'partial'."""

    @abstractmethod
    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get current position. Returns dict or None."""

    @abstractmethod
    def close_position(self, symbol: str) -> CloseResult:
        """Close the current position for a symbol. Returns CloseResult with PnL data."""

    @abstractmethod
    def get_fee_rate(self, symbol: str) -> Dict[str, float]:
        """Get the trading fee rate. Returns {'maker': float, 'taker': float}."""

    @abstractmethod
    def get_ticker_price(self, symbol: str) -> Optional[float]:
        """Get current mark/last price for a symbol. Returns float or None."""

    @abstractmethod
    def get_max_position(self, symbol: str) -> Optional[float]:
        """Get maximum position size allowed for a symbol. Returns float or None."""

    @abstractmethod
    def get_contract_size(self, symbol: str) -> float:
        """Get contract size (multiplier) for a symbol.

        For exchanges where quantity = coins (Binance, Bybit), returns 1.0.
        For exchanges where quantity = contracts (MEXC, BYDFi), returns the
        multiplier (e.g. 0.0001 means 1 contract = 0.0001 coins).
        """
