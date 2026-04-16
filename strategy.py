"""
Strategy Engine.
Receives funding rates from all exchanges, filters arbitrage opportunities,
and calculates position sizes.
"""
import math
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ArbitrageOpportunity:
    """Arbitrage opportunity."""
    symbol: str
    high_exchange: str        # Exchange with higher rate (long side)
    low_exchange: str         # Exchange with lower rate (short side)
    high_rate: float          # Higher funding rate (decimal)
    low_rate: float           # Lower funding rate (decimal)
    rate_diff_percent: float  # Rate difference (percentage)
    estimated_profit: float  # Estimated profit (before fees)
    side_a: str               # High side direction ("BUY"=long)
    side_b: str               # Low side direction ("SELL"=short)
    next_settlement: int      # Unix timestamp of next funding settlement


class StrategyEngine:
    """
    Strategy Engine.

    Args:
        min_rate_diff: Minimum trigger threshold (percentage, e.g. 0.01)
        max_concurrent: Maximum concurrent positions
        position_mode: "fixed" | "percent" | "dynamic"
        position_value: Position size for fixed mode (USDT)
        position_percent: Account balance percentage for percent mode
    """

    def __init__(
        self,
        min_rate_diff: float = 0.01,
        max_concurrent: int = 3,
        position_mode: str = "fixed",
        position_value: float = 1000,
        position_percent: float = 5,
        leverage: int = 5,
    ):
        self.min_rate_diff = min_rate_diff
        self.max_concurrent = max_concurrent
        self.position_mode = position_mode
        self.position_value = position_value
        self.position_percent = position_percent
        self.leverage = leverage

    def find_opportunities(
        self,
        all_rates: Dict[str, Dict[str, "FundingRate"]],
    ) -> List[ArbitrageOpportunity]:
        """
        Scan all exchange rates and find qualifying arbitrage opportunities.
        all_rates: {exchange_name: {symbol: FundingRate}}
        Returns: List of opportunities sorted by rate_diff descending
        """
        from exchanges.base import FundingRate

        opportunities = []
        exchanges = list(all_rates.keys())

        # Pair all exchanges
        for i in range(len(exchanges)):
            for j in range(i + 1, len(exchanges)):
                ex_a = exchanges[i]
                ex_b = exchanges[j]
                rates_a = all_rates[ex_a]
                rates_b = all_rates[ex_b]

                # Find common symbols
                common = set(rates_a.keys()) & set(rates_b.keys())
                for sym in common:
                    fr_a = rates_a[sym]
                    fr_b = rates_b[sym]

                    # Skip if next_settlement differs between exchanges
                    if fr_a.next_settlement != fr_b.next_settlement:
                        continue

                    rate_diff = abs(fr_a.rate - fr_b.rate)
                    rate_diff_pct = rate_diff * 100

                    if rate_diff_pct < self.min_rate_diff:
                        continue

                    # Determine direction
                    if fr_a.rate > fr_b.rate:
                        high_ex, low_ex = ex_a, ex_b
                        high_rate, low_rate = fr_a.rate, fr_b.rate
                    else:
                        high_ex, low_ex = ex_b, ex_a
                        high_rate, low_rate = fr_b.rate, fr_a.rate

                    opportunities.append(ArbitrageOpportunity(
                        symbol=sym,
                        high_exchange=high_ex,
                        low_exchange=low_ex,
                        high_rate=high_rate,
                        low_rate=low_rate,
                        rate_diff_percent=rate_diff_pct,
                        estimated_profit=0,  # Filled by executor
                        side_a="BUY",
                        side_b="SELL",
                        next_settlement=rates_a[sym].next_settlement
                        if high_ex == ex_a
                        else rates_b[sym].next_settlement,
                    ))

        # Sort by rate_diff descending, take top max_concurrent
        opportunities.sort(key=lambda x: x.rate_diff_percent, reverse=True)
        return opportunities[:self.max_concurrent]

    def calculate_position_size(
        self,
        symbol: str,
        current_price: float,
        balances: Dict[str, float],
    ) -> float:
        """
        Calculate position size (USDT value per side) based on position mode.

        BOTH exchanges must have sufficient available balance for the arbitrage
        to work. Position size is limited by the smaller of the two balances.
        """
        if self.position_mode == "fixed":
            # Use the minimum balance across exchanges, so neither side is underfunded
            min_balance = min(balances.values()) if balances else 0.0
            return min(self.position_value, min_balance)

        if self.position_mode == "percent":
            total_balance = sum(balances.values())
            return total_balance * (self.position_percent / 100)

        # dynamic: use fixed as base
        return self.position_value

    def contracts_from_usdt(
        self,
        usdt_amount: float,
        price: float,
        contract_size: float = 1.0,
    ) -> int:
        """
        Convert USDT amount to order quantity.

        Formula: quantity = notional_value / (contract_size * price)

        - Binance/Bybit: contract_size=1, so quantity = usdt / price (coins)
        - MEXC: contract_size from API (e.g. 0.0001), quantity = usdt / (cs * price) (contracts)
        - BYDFi: contract_size=multiplier from API, same formula (contracts)
        """
        if contract_size <= 0 or price <= 0 or usdt_amount <= 0:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"contracts_from_usdt returned 0: usdt={usdt_amount}, "
                f"price={price}, contract_size={contract_size}"
            )
            return 0
        return math.floor(usdt_amount / (contract_size * price))

    def clamp_quantity(
        self,
        symbol: str,
        quantity: int,
        adapter,
    ) -> int:
        """
        Clamp quantity to exchange position limits.
        Queries max position from exchange and returns the lesser of quantity
        or that limit. If clamped quantity is below min order size, returns 0.
        """
        max_pos = adapter.get_max_position(symbol)
        if max_pos is not None and quantity > max_pos:
            quantity = int(max_pos)
        return quantity
