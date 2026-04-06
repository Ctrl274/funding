"""
Monitor loop with APScheduler.
Periodically polls funding rates, checks settlement windows, triggers arbitrage strategy.
"""
import time
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from config import Config
from exchanges.base import ExchangeAdapter, FundingRate
from strategy import StrategyEngine, ArbitrageOpportunity
from executor import ExecutionEngine, OrderResult
from notifier import Notifier

logger = logging.getLogger(__name__)


class MonitorLoop:
    """
    Monitor loop with APScheduler.
    Checks settlement timing based on API-returned next_settlement.
    Supports any settlement frequency (1h / 2h / 4h / 8h etc).
    """

    def __init__(
        self,
        config: Config,
        adapters: Dict[str, ExchangeAdapter],
        strategy: StrategyEngine,
        executor: ExecutionEngine,
        notifier: Notifier,
    ):
        self._config = config
        self._adapters = adapters
        self._strategy = strategy
        self._executor = executor
        self._notifier = notifier
        self._scheduler = BackgroundScheduler()
        self._running = False
        self._current_positions: Dict[str, Dict] = {}

    def start(self):
        interval = self._config.monitor.polling_interval
        self._scheduler.add_job(
            self._scan,
            IntervalTrigger(seconds=interval),
            id="funding_scan",
            replace_existing=True,
        )
        self._scheduler.start()
        self._running = True
        logger.info("Monitor loop started")

    def stop(self):
        self._scheduler.shutdown(wait=False)
        self._running = False
        logger.info("Monitor loop stopped")

    def _scan(self):
        if not self._config.monitor.enabled:
            return

        if not self._is_near_settlement():
            logger.debug("Not within pre-settlement window, skipping")
            return

        logger.info("Scanning funding rates...")
        all_rates = self._collect_rates()
        if not all_rates:
            logger.warning("No funding rates collected")
            return

        opportunities = self._strategy.find_opportunities(all_rates)
        if not opportunities:
            logger.info("No arbitrage opportunities found")
            return

        logger.info(f"Found {len(opportunities)} opportunities")

        for opp in opportunities:
            self._execute_opportunity(opp, all_rates)

    def _collect_rates(self) -> Dict[str, Dict[str, FundingRate]]:
        result = {}
        for name, adapter in self._adapters.items():
            try:
                rates = adapter.get_funding_rates()
                result[name] = rates
                logger.debug(f"{name}: {len(rates)} symbols")
            except Exception as e:
                logger.error(f"Failed to fetch rates from {name}: {e}")
        return result

    def _is_within_time_window(self) -> bool:
        windows = self._config.monitor.time_windows
        if not windows:
            return True

        now_utc = datetime.now(timezone.utc)
        now_minutes = now_utc.hour * 60 + now_utc.minute

        for window in windows:
            start_str, end_str = window.split("-")
            sh, sm = map(int, start_str.split(":"))
            eh, em = map(int, end_str.split(":"))
            start_m = sh * 60 + sm
            end_m = eh * 60 + em

            if start_m > end_m:
                if now_minutes >= start_m or now_minutes <= end_m:
                    return True
            else:
                if start_m <= now_minutes <= end_m:
                    return True
        return False

    def _is_near_settlement(self) -> bool:
        pre_seconds = self._config.strategy.pre_settlement_seconds
        now_ts = time.time()

        for name, adapter in self._adapters.items():
            try:
                rates = adapter.get_funding_rates()
                for fr in rates.values():
                    if fr.next_settlement > 0:
                        time_to_settlement = fr.next_settlement - now_ts
                        if 0 < time_to_settlement <= pre_seconds:
                            return True
            except Exception:
                pass

        return self._is_within_time_window()

    def _execute_opportunity(self, opp: ArbitrageOpportunity, all_rates: Dict):
        adapter_a = self._adapters[opp.high_exchange]
        adapter_b = self._adapters[opp.low_exchange]
        symbol = opp.symbol

        price_a = 50000.0
        price_b = 50000.0

        balances = {}
        for name in [opp.high_exchange, opp.low_exchange]:
            try:
                balances[name] = self._adapters[name].get_account_balance()
            except Exception:
                balances[name] = 0

        usdt_per_side = self._strategy.calculate_position_size(symbol, price_a, balances)
        quantity = self._strategy.contracts_from_usdt(usdt_per_side, price_a)

        if quantity < 1:
            logger.info(f"Position too small for {symbol}")
            return

        result = self._executor.execute_arbitrage(
            symbol=symbol,
            adapter_a=adapter_a,
            adapter_b=adapter_b,
            side_a=opp.side_a,
            side_b=opp.side_b,
            quantity=quantity,
            price_a=price_a,
            price_b=price_b,
        )

        if result.status == "filled":
            self._current_positions[symbol] = {
                "high_exchange": opp.high_exchange,
                "low_exchange": opp.low_exchange,
                "side_a": opp.side_a,
                "side_b": opp.side_b,
                "quantity": quantity,
                "open_time": result.timestamp,
            }

        self._notifier.send_arbitrage_result(opp, result)

    def get_current_rates(self) -> Dict[str, Dict[str, FundingRate]]:
        return self._collect_rates()

    def get_positions(self) -> Dict[str, Dict]:
        return self._current_positions

    def get_next_settlement(self) -> Optional[datetime]:
        all_rates = self._collect_rates()
        return self._get_next_settlement_from_rates(all_rates)

    def _get_next_settlement_from_rates(self, all_rates: Dict) -> Optional[datetime]:
        now_ts = time.time()
        nearest_ts: Optional[float] = None

        for ex_rates in all_rates.values():
            for fr in ex_rates.values():
                if fr.next_settlement > now_ts:
                    if nearest_ts is None or fr.next_settlement < nearest_ts:
                        nearest_ts = fr.next_settlement

        if nearest_ts is None:
            return None
        return datetime.fromtimestamp(nearest_ts, tz=timezone.utc)
