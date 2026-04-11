"""
Monitor Loop.
Periodically polls funding rates, checks time windows, and triggers arbitrage strategy.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger


logger = logging.getLogger(__name__)


class MonitorLoop:
    """
    Monitor Loop.
    Uses APScheduler to trigger a scan every N seconds.
    Settlement timing is derived from exchange API (next_settlement timestamp),
    not hardcoded — supports any funding interval (1h, 2h, 4h, 8h, etc.).
    """

    def __init__(
        self,
        config,
        adapters: Dict,
        strategy,
        executor,
        notifier,
        db=None,
    ):
        self._config = config
        self._adapters = adapters
        self._strategy = strategy
        self._executor = executor
        self._notifier = notifier
        self._db = db
        self._scheduler = BackgroundScheduler()
        self._running = False
        self._current_positions: Dict = {}
        self._load_open_positions()

    def _load_open_positions(self):
        """Load open positions from database on startup."""
        if not self._db:
            return
        positions = self._db.get_positions()
        for pos in positions:
            self._current_positions[pos["symbol"]] = {
                "high_exchange": pos["high_exchange"],
                "low_exchange": pos["low_exchange"],
                "side_a": pos["side_a"],
                "side_b": pos["side_b"],
                "quantity": pos.get("quantity", 0),
                "quantity_a": pos.get("quantity_a"),
                "quantity_b": pos.get("quantity_b"),
                "open_time": pos["open_time"],
            }
        if self._current_positions:
            logger.info(f"Loaded {len(self._current_positions)} open positions from database")

    def start(self):
        """Start monitoring."""
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
        """Stop monitoring."""
        self._scheduler.shutdown(wait=False)
        self._running = False
        logger.info("Monitor loop stopped")

    def _scan(self):
        """Execute one scan."""
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

        logger.info(f"Found {len(opportunities)} opportunities: {[o.symbol for o in opportunities]}")

        for opp in opportunities:
            self._execute_opportunity(opp, all_rates)

    def _collect_rates(self) -> Dict:
        """Collect funding rates from all exchanges."""
        from exchanges.base import FundingRate
        result = {}
        for name, adapter in self._adapters.items():
            try:
                rates = adapter.get_funding_rates()
                result[name] = rates
                logger.info(f"{name}: {len(rates)} symbols collected")
            except Exception as e:
                logger.error(f"Failed to fetch rates from {name}: {e}", exc_info=True)
        return result

    def _is_within_time_window(self) -> bool:
        """Check if current time is within running time windows."""
        windows = self._config.monitor.time_windows
        if not windows:
            return True  # Empty = 24h

        now_utc = datetime.now(timezone.utc)
        now_minutes = now_utc.hour * 60 + now_utc.minute

        for window in windows:
            start_str, end_str = window.split("-")
            sh, sm = map(int, start_str.split(":"))
            eh, em = map(int, end_str.split(":"))
            start_m = sh * 60 + sm
            end_m = eh * 60 + em

            # Cross-midnight window (e.g. 23:50-00:10)
            if start_m > end_m:
                if now_minutes >= start_m or now_minutes <= end_m:
                    return True
            else:
                if start_m <= now_minutes <= end_m:
                    return True
        return False

    def _is_near_settlement(self) -> bool:
        """
        Check if current time is within the pre-settlement window.
        Uses actual next_settlement timestamps from exchange APIs,
        supporting any funding interval (1h, 2h, 4h, 8h, etc.).
        Falls back to time_windows if no rates are available.
        """
        import time
        pre_seconds = self._config.strategy.pre_settlement_seconds
        now_ts = time.time()

        # Quick check: collect rates and compare next_settlement
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

        # Fallback: use time window if rate fetch fails
        return self._is_within_time_window()

    def _parse_time_window(self, window: str) -> tuple:
        """Parse time window string 'HH:MM-HH:MM' into (start_hour_float, end_hour_float)."""
        start_str, end_str = window.split("-")
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
        start_h = sh + sm / 60.0
        end_h = eh + em / 60.0
        return (start_h, end_h)

    def _execute_opportunity(self, opp, all_rates):
        """Execute a single arbitrage opportunity."""
        from strategy import ArbitrageOpportunity
        adapter_a = self._adapters[opp.high_exchange]
        adapter_b = self._adapters[opp.low_exchange]

        symbol = opp.symbol

        # Set leverage before placing orders
        leverage = self._strategy.leverage
        adapter_a.set_leverage(symbol, leverage)
        adapter_b.set_leverage(symbol, leverage)

        # Fetch real-time prices from both exchanges
        price_a = adapter_a.get_ticker_price(symbol)
        price_b = adapter_b.get_ticker_price(symbol)

        if price_a is None or price_b is None:
            logger.warning(
                f"Skipping {symbol}: failed to fetch prices "
                f"(high={opp.high_exchange}:{price_a}, low={opp.low_exchange}:{price_b})"
            )
            return

        logger.info(f"{symbol} prices: {opp.high_exchange}={price_a}, {opp.low_exchange}={price_b}")

        # Calculate position
        balances = {}
        for name in [opp.high_exchange, opp.low_exchange]:
            try:
                balances[name] = self._adapters[name].get_account_balance()
            except Exception:
                balances[name] = 0

        usdt_per_side = self._strategy.calculate_position_size(symbol, price_a, balances)

        # Calculate per-exchange quantities based on each adapter's contract size
        cs_a = adapter_a.get_contract_size(symbol)
        cs_b = adapter_b.get_contract_size(symbol)

        quantity_a = self._strategy.contracts_from_usdt(usdt_per_side, price_a, cs_a)
        quantity_b = self._strategy.contracts_from_usdt(usdt_per_side, price_b, cs_b)

        # Both sides must use the same quantity for a matched arbitrage position.
        # Use the smaller quantity to ensure neither side exceeds its USDT allocation.
        quantity = min(quantity_a, quantity_b)

        if quantity < 1:
            # Determine the skip reason
            if usdt_per_side <= 0:
                reason = "Insufficient balance"
                details = (
                    f"usdt_per_side={usdt_per_side}, "
                    f"balances={balances}, "
                    f"price_a={price_a}, price_b={price_b}"
                )
                logger.warning(
                    f"Skipping {symbol}: insufficient balance "
                    f"(usdt_per_side={usdt_per_side}, balances={balances})"
                )
            else:
                reason = "Position too small after calculation"
                details = (
                    f"usdt_per_side={usdt_per_side}, "
                    f"quantity={quantity} (from qa={quantity_a}, qb={quantity_b}), "
                    f"price_a={price_a}, price_b={price_b}"
                )
                logger.warning(
                    f"Position too small for {symbol}: "
                    f"quantity={quantity}, usdt_per_side={usdt_per_side}, "
                    f"price_a={price_a}, price_b={price_b}"
                )
            self._notifier.send_skip_reason(opp, reason, details)
            return

        # Clamp to the stricter of both exchange position limits
        clamped_a = self._strategy.clamp_quantity(symbol, quantity, adapter_a)
        clamped_b = self._strategy.clamp_quantity(symbol, quantity, adapter_b)
        quantity = min(clamped_a, clamped_b)

        if quantity < 1:
            logger.warning(
                f"Position too small after clamping for {symbol} "
                f"(quantity={quantity}, usdt_per_side={usdt_per_side})"
            )
            self._notifier.send_skip_reason(
                opp, "Position too small after exchange limit clamp",
                f"quantity={quantity}, usdt_per_side={usdt_per_side}"
            )
            return

        logger.info(
            f"{symbol} quantity: {quantity} "
            f"(qa={quantity_a}, qb={quantity_b}, cs_a={cs_a}, cs_b={cs_b})"
        )

        # Place orders — both sides use the same quantity
        result = self._executor.execute_arbitrage(
            symbol=symbol,
            adapter_a=adapter_a,
            adapter_b=adapter_b,
            side_a=opp.side_a,
            side_b=opp.side_b,
            quantity_a=quantity,
            quantity_b=quantity,
            price_a=price_a,
            price_b=price_b,
            order_type=self._config.strategy.order_type,
        )

        # Record position and trade
        if result.status == "filled":
            position = {
                "high_exchange": opp.high_exchange,
                "low_exchange": opp.low_exchange,
                "side_a": opp.side_a,
                "side_b": opp.side_b,
                "quantity": quantity_a,
                "quantity_a": quantity_a,
                "quantity_b": quantity_b,
                "open_time": result.timestamp,
            }
            self._current_positions[symbol] = position
            if self._db:
                self._db.save_position(symbol, **position)
                logger.info(f"Position saved to database: {symbol}")

        # Record trade result
        if self._db:
            self._db.save_trade(
                symbol=symbol,
                high_exchange=opp.high_exchange,
                low_exchange=opp.low_exchange,
                rate_diff=opp.rate_diff_percent,
                result=result.status,
                quantity=quantity_a,
                quantity_a=quantity_a,
                quantity_b=quantity_b,
                side_a=opp.side_a,
                side_b=opp.side_b,
                error_a=result.error_a,
                error_b=result.error_b,
            )
            logger.info(f"Trade recorded: {symbol} {result.status}")

        # Notify
        self._notifier.send_arbitrage_result(opp, result)

    def get_current_rates(self) -> Dict:
        """Get current rates (for Web UI)."""
        return self._collect_rates()

    def get_positions(self) -> Dict:
        """Get current positions."""
        return self._current_positions

    def close_position(self, symbol: str):
        """Close a position by placing reverse orders on both exchanges."""
        if symbol not in self._current_positions:
            logger.warning(f"No open position for {symbol}")
            return

        pos = self._current_positions[symbol]
        close_errors = []

        # Close on both exchanges
        for ex_name in [pos["high_exchange"], pos["low_exchange"]]:
            try:
                adapter = self._adapters[ex_name]
                adapter.close_position(symbol)
                logger.info(f"Closed position on {ex_name} for {symbol}")
            except Exception as e:
                logger.error(f"Failed to close on {ex_name} for {symbol}: {e}", exc_info=True)
                close_errors.append(f"{ex_name}: {e}")

        # Remove from tracking
        self._current_positions.pop(symbol, None)

        # Update database
        if self._db:
            self._db.close_position(symbol)
            close_result = "closed" if not close_errors else f"partial: {', '.join(close_errors)}"
            self._db.update_trade_close(symbol, close_result)
            logger.info(f"Position closed in database: {symbol} ({close_result})")

    def get_next_settlement(self) -> Optional[datetime]:
        """Get next settlement time from real API data."""
        all_rates = self._collect_rates()
        return self._get_next_settlement_from_rates(all_rates)

    def _get_next_settlement_from_rates(
        self, all_rates: Dict
    ) -> Optional[datetime]:
        """Find the nearest next_settlement timestamp across all rates."""
        import time
        now_ts = time.time()
        nearest_ts: Optional[int] = None

        for ex_rates in all_rates.values():
            for fr in ex_rates.values():
                if fr.next_settlement > now_ts:
                    if nearest_ts is None or fr.next_settlement < nearest_ts:
                        nearest_ts = fr.next_settlement

        if nearest_ts is None:
            return None
        return datetime.fromtimestamp(nearest_ts, tz=timezone.utc)
