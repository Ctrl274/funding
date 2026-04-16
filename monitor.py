"""
Monitor Loop.
Periodically polls funding rates, checks time windows, and triggers arbitrage strategy.
"""
import logging
from datetime import datetime, timezone, timedelta

TZ_UTC8 = timezone(timedelta(hours=8))
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
        self._attempted_this_cycle: Dict[str, str] = {}  # {symbol: result_summary} per cycle
        self._next_settlement_ts: Optional[int] = None        # tracks upcoming settlement
        self._most_recent_settled_ts: Optional[int] = None  # tracks most recent past settlement
        self._in_close: bool = False                      # prevents re-entrant close during auto-close
        self._closing: Dict[str, bool] = {}              # {symbol: True} while close is in progress
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
                "target_settlement": pos.get("target_settlement"),
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

        import time
        post_close_seconds = self._config.strategy.post_settlement_close_seconds
        now_ts = time.time()

        # Check if we are in the auto-close window (post-settlement)
        is_close_window = False
        if self._most_recent_settled_ts:
            time_since = now_ts - self._most_recent_settled_ts
            if time_since >= post_close_seconds:
                is_close_window = True

        if not self._is_near_settlement():
            # Outside both windows — cycle reset already handled in _is_near_settlement
            logger.debug("Not within open/close window, skipping")
            return

        if is_close_window:
            # Auto-close window: close all open positions
            if self._in_close:
                logger.debug("Auto-close already in progress, skipping")
                return
            self._in_close = True
            try:
                self._auto_close_positions()
            finally:
                self._in_close = False
            return

        # === Open window: scan for opportunities ===
        logger.info("Scanning funding rates...")
        all_rates = self._collect_rates()
        if not all_rates:
            logger.warning("No funding rates collected")
            return

        opportunities = self._strategy.find_opportunities(all_rates)
        if not opportunities:
            logger.info("No arbitrage opportunities found")
            return

        # Filter out symbols already attempted in this settlement cycle
        new_opps = [o for o in opportunities if o.symbol not in self._attempted_this_cycle]
        # Also filter out symbols that already have an open position
        new_opps = [o for o in new_opps if o.symbol not in self._current_positions]
        if not new_opps:
            logger.info(f"All {len(opportunities)} opportunities already attempted this cycle")
            return

        logger.info(f"Found {len(new_opps)} new opportunities (cycle total: {len(self._attempted_this_cycle)} already tried): {[o.symbol for o in new_opps]}")

        for opp in new_opps:
            self._execute_opportunity(opp, all_rates)

    def _auto_close_positions(self):
        """Close all open positions during the post-settlement close window."""
        if not self._current_positions:
            return
        symbols = list(self._current_positions.keys())
        logger.info(f"Auto-close window: closing {len(symbols)} positions: {symbols}")
        for symbol in symbols:
            self.close_position(symbol)

    def _send_cycle_summary(self):
        """Send a single batch notification for all failed attempts in this cycle."""
        failures = {sym: reason for sym, reason in self._attempted_this_cycle.items()
                    if reason != "filled"}
        if not failures:
            return

        lines = ["[Settlement Cycle Summary]"]
        for sym, reason in failures.items():
            lines.append(f"  {sym}: {reason}")
        self._notifier.send("\n".join(lines))

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
        Also tracks the current settlement cycle and resets _attempted_this_cycle
        when a new settlement cycle begins.
        """
        import time
        pre_seconds = self._config.strategy.pre_settlement_seconds
        pre_open_seconds = self._config.strategy.pre_open_seconds
        post_close_seconds = self._config.strategy.post_settlement_close_seconds
        now_ts = time.time()

        # Find nearest upcoming settlement across all exchanges
        nearest_settlement_ts = None
        for name, adapter in self._adapters.items():
            try:
                rates = adapter.get_funding_rates()
                for fr in rates.values():
                    if fr.next_settlement > now_ts:
                        if nearest_settlement_ts is None or fr.next_settlement < nearest_settlement_ts:
                            nearest_settlement_ts = fr.next_settlement
            except Exception:
                pass

        # If no upcoming settlement from API, fall back to time window
        if nearest_settlement_ts is None:
            return self._is_within_time_window()

        # Detect cycle change: if nearest upcoming settlement is NEWER than tracked,
        # it means settlement passed and a new cycle began
        if self._next_settlement_ts is not None and nearest_settlement_ts > self._next_settlement_ts:
            # Settlement cycle changed — send summary for old cycle, reset
            if self._attempted_this_cycle:
                self._send_cycle_summary()
                self._attempted_this_cycle.clear()
            self._most_recent_settled_ts = self._next_settlement_ts
            logger.info(
                f"Settlement cycle change: {self._next_settlement_ts} -> {nearest_settlement_ts}"
            )
        self._next_settlement_ts = nearest_settlement_ts

        # Open window: pre_settlement_seconds to pre_open_seconds before settlement
        time_to_settlement = nearest_settlement_ts - now_ts
        if pre_seconds <= time_to_settlement <= pre_open_seconds:
            return True

        # Auto-close window: time_since >= post_close_seconds after most recent settlement
        if self._most_recent_settled_ts is not None:
            time_since_settlement = now_ts - self._most_recent_settled_ts
            if time_since_settlement >= post_close_seconds:
                return True

        return False

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
                logger.warning(
                    f"Skipping {symbol}: insufficient balance "
                    f"(usdt_per_side={usdt_per_side}, balances={balances})"
                )
                self._attempted_this_cycle[symbol] = (
                    f"Insufficient balance (balances={balances})"
                )
            else:
                logger.warning(
                    f"Position too small for {symbol}: "
                    f"quantity={quantity}, usdt_per_side={usdt_per_side}, "
                    f"price_a={price_a}, price_b={price_b}"
                )
                self._attempted_this_cycle[symbol] = (
                    f"Position too small (qty={quantity})"
                )
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
            self._attempted_this_cycle[symbol] = "Position too small after clamping"
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
            rate_diff=opp.rate_diff_percent,
        )

        # Record position and trade
        if result.status == "filled":
            position = {
                "high_exchange": opp.high_exchange,
                "low_exchange": opp.low_exchange,
                "side_a": opp.side_a,
                "side_b": opp.side_b,
                "quantity": quantity,
                "quantity_a": quantity,
                "quantity_b": quantity,
                "fill_price_a": result.fill_price_a,
                "fill_price_b": result.fill_price_b,
                "open_time": result.timestamp,
                "target_settlement": datetime.fromtimestamp(opp.next_settlement, tz=TZ_UTC8).strftime("%Y-%m-%d %H:%M:%S"),
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
                quantity=quantity,
                quantity_a=quantity,
                quantity_b=quantity,
                side_a=opp.side_a,
                side_b=opp.side_b,
                profit=result.profit,
                fill_price_a=result.fill_price_a,
                fill_price_b=result.fill_price_b,
                error_a=result.error_a,
                error_b=result.error_b,
                target_settlement=datetime.fromtimestamp(opp.next_settlement, tz=TZ_UTC8).strftime("%Y-%m-%d %H:%M:%S"),
            )
            logger.info(f"Trade recorded: {symbol} {result.status}")

        # Record result in cycle tracker and notify
        if result.status == "filled":
            self._attempted_this_cycle[symbol] = "filled"
            self._notifier.send_arbitrage_result(opp, result)
        else:
            # Failed: record reason and notify immediately
            error_parts = []
            if result.error_a:
                error_parts.append(f"A: {result.error_a}")
            if result.error_b:
                error_parts.append(f"B: {result.error_b}")
            reason = f"{result.status} — {', '.join(error_parts)}" if error_parts else result.status
            self._attempted_this_cycle[symbol] = reason
            logger.warning(f"{symbol} arbitrage failed: {reason}")
            self._notifier.send(f"[FAIL] {symbol}: {reason}")

    def get_current_rates(self) -> Dict:
        """Get current rates (for Web UI)."""
        return self._collect_rates()

    def get_positions(self) -> Dict:
        """Get current positions."""
        return self._current_positions

    def close_position(self, symbol: str) -> Dict:
        """Close a position by placing reverse orders on both exchanges.

        Returns dict with:
            - status: 'closed' | 'partial' | 'failed'
            - close_results: {exchange_name: {success, close_price, fee, error}}
        """
        if symbol not in self._current_positions:
            # Position already closed (auto-close or manual), operation is effectively done
            return {"status": "closed", "close_results": {}, "error": None}

        if symbol in self._closing:
            logger.warning(f"{symbol} already being closed, skipping")
            return {"status": "failed", "close_results": {}, "error": "already_closing"}
        self._closing[symbol] = True

        pos = self._current_positions[symbol]
        trade_row = None
        if self._db:
            trade_row = self._db.get_open_trade(symbol)

        close_price_a_total = None
        close_price_b_total = None
        fee_a_total = 0.0
        fee_b_total = 0.0
        close_errors = []

        # Close on both exchanges
        for ex_name in [pos["high_exchange"], pos["low_exchange"]]:
            try:
                adapter = self._adapters[ex_name]
                result = adapter.close_position(symbol)
                logger.info(f"Closed position on {ex_name} for {symbol}: {result}")
                if ex_name == pos["high_exchange"]:
                    close_price_a_total = result.close_price_a
                    fee_a_total = result.fee_a or 0.0
                    if not result.success:
                        close_errors.append(f"{ex_name}: {result.error_a or 'failed'}")
                else:
                    close_price_b_total = result.close_price_b
                    fee_b_total = result.fee_b or 0.0
                    if not result.success:
                        close_errors.append(f"{ex_name}: {result.error_b or 'failed'}")
            except Exception as e:
                logger.error(f"Failed to close on {ex_name} for {symbol}: {e}", exc_info=True)
                close_errors.append(f"{ex_name}: {e}")

        # Remove from tracking
        self._current_positions.pop(symbol, None)

        # Update database — skip if trade not found (already closed) or no new data
        if self._db:
            if trade_row is None:
                logger.warning(f"No open trade found for {symbol} to update on close")
            else:
                self._db.close_position(symbol)
                close_result = "closed" if not close_errors else f"partial: {', '.join(close_errors)}"

                # Compute realized PnL: (close_price - fill_price) * qty - fee per side
                # For arbitrage: high exchange long (buy low, sell high), low exchange short
                realized_pnl = None
                qty = trade_row.get("quantity_a") or trade_row.get("quantity") or 0
                fill_a = trade_row.get("fill_price_a")
                fill_b = trade_row.get("fill_price_b")
                if fill_a and close_price_a_total and qty:
                    pnl_a = (close_price_a_total - fill_a) * qty - fee_a_total
                else:
                    pnl_a = 0.0
                if fill_b and close_price_b_total and qty:
                    pnl_b = (fill_b - close_price_b_total) * qty - fee_b_total
                else:
                    pnl_b = 0.0
                realized_pnl = pnl_a + pnl_b

                self._db.update_trade_close(
                    symbol,
                    close_result,
                    close_price_a=close_price_a_total,
                    close_price_b=close_price_b_total,
                    fee_a=fee_a_total or None,
                    fee_b=fee_b_total or None,
                    realized_pnl=realized_pnl,
                )
                logger.info(f"Position closed in database: {symbol} ({close_result}), pnl={realized_pnl}")

        # Determine status from close_errors
        if not close_errors:
            status = "closed"
        elif len(close_errors) == 2:
            status = "failed"
        else:
            status = "partial"

        # Build per-exchange results
        close_results = {}
        for ex_name in [pos["high_exchange"], pos["low_exchange"]]:
            if ex_name == pos["high_exchange"]:
                close_results[ex_name] = {
                    "success": pos["high_exchange"] not in close_errors,
                    "close_price": close_price_a_total,
                    "fee": fee_a_total or None,
                }
            else:
                close_results[ex_name] = {
                    "success": pos["low_exchange"] not in close_errors,
                    "close_price": close_price_b_total,
                    "fee": fee_b_total or None,
                }

        self._closing.pop(symbol, None)
        return {"status": status, "close_results": close_results}

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
