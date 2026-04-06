"""
Strategy engine.
Collects exchange rates, finds arbitrage opportunities by pairwise comparison.
"""
import math
from dataclasses import dataclass
from typing import Dict, List, Optional
from exchanges.base import FundingRate


@dataclass(frozen=True)
class ArbitrageOpportunity:
    symbol: str
    high_exchange: str
    low_exchange: str
    high_rate: float
    low_rate: float
    rate_diff_percent: float
    estimated_profit: float
    side_a: str  # "BUY" = long on high-rate exchange
    side_b: str  # "SELL" = short on low-rate exchange
    next_settlement: int


class StrategyEngine:
    def __init__(
        self,
        min_rate_diff: float = 0.01,
        max_concurrent: int = 3,
        position_mode: str = "fixed",
        position_value: float = 1000,
        position_percent: float = 5,
    ):
        self.min_rate_diff = min_rate_diff
        self.max_concurrent = max_concurrent
        self.position_mode = position_mode
        self.position_value = position_value
        self.position_percent = position_percent

    def find_opportunities(self, all_rates: Dict[str, Dict[str, FundingRate]]) -> List[ArbitrageOpportunity]:
        opportunities = []
        exchanges = list(all_rates.keys())

        for i in range(len(exchanges)):
            for j in range(i + 1, len(exchanges)):
                ex_a, ex_b = exchanges[i], exchanges[j]
                rates_a, rates_b = all_rates[ex_a], all_rates[ex_b]
                common = set(rates_a.keys()) & set(rates_b.keys())

                for sym in common:
                    fr_a, fr_b = rates_a[sym], rates_b[sym]
                    rate_diff_pct = abs(fr_a.rate - fr_b.rate) * 100

                    if rate_diff_pct < self.min_rate_diff:
                        continue

                    if fr_a.rate > fr_b.rate:
                        high_ex, low_ex = ex_a, ex_b
                        high_rate, low_rate = fr_a.rate, fr_b.rate
                        settlement = fr_a.next_settlement
                    else:
                        high_ex, low_ex = ex_b, ex_a
                        high_rate, low_rate = fr_b.rate, fr_a.rate
                        settlement = fr_b.next_settlement

                    opportunities.append(ArbitrageOpportunity(
                        symbol=sym,
                        high_exchange=high_ex,
                        low_exchange=low_ex,
                        high_rate=high_rate,
                        low_rate=low_rate,
                        rate_diff_percent=rate_diff_pct,
                        estimated_profit=0,
                        side_a="BUY",
                        side_b="SELL",
                        next_settlement=int(settlement),
                    ))

        opportunities.sort(key=lambda x: x.rate_diff_percent, reverse=True)
        return opportunities[:self.max_concurrent]

    def calculate_position_size(self, symbol: str, current_price: float, balances: Dict[str, float]) -> float:
        if self.position_mode == "fixed":
            return self.position_value
        if self.position_mode == "percent":
            return sum(balances.values()) * (self.position_percent / 100)
        return self.position_value

    def contracts_from_usdt(self, usdt_amount: float, price: float, contract_size: float = 1.0) -> int:
        return math.floor(usdt_amount / price / contract_size)
