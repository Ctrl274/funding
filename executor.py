"""
Execution Engine.
Handles FOK limit orders, market orders, fill listening, and partial fill handling.
"""
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OrderResult:
    """Order placement result."""
    status: str                   # "filled" | "partial_fill" | "failed" | "timeout"
    order_a_id: Optional[str] = None
    order_b_id: Optional[str] = None
    fill_price_a: Optional[float] = None
    fill_price_b: Optional[float] = None
    error_a: Optional[str] = None
    error_b: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class ExecutionEngine:
    """
    Execution Engine.

    Core flow:
    1. Send orders to both exchanges simultaneously
    2. Market orders: assume filled immediately, verify via get_order_status
    3. Limit orders (IOC/FOK): poll for fill status (N second timeout)
    4. Both filled -> success
       One side not filled -> cancel other side + stop loss
       Both failed -> failure
    """

    def __init__(self, timeout: int = 30, poll_interval: float = 1.0):
        self.timeout = timeout
        self.poll_interval = poll_interval

    def execute_arbitrage(
        self,
        symbol: str,
        adapter_a,
        adapter_b,
        side_a: str,
        side_b: str,
        quantity: int,
        price_a: float,
        price_b: float,
        order_type: str = "limit",
    ) -> OrderResult:
        """
        Execute arbitrage.
        order_type: "limit" (IOC/FOK) or "market"
        Returns OrderResult.
        """
        if order_type == "market":
            return self._execute_market(symbol, adapter_a, adapter_b,
                                        side_a, side_b, quantity, price_a, price_b)
        return self._execute_limit(symbol, adapter_a, adapter_b,
                                   side_a, side_b, quantity, price_a, price_b)

    def _execute_market(
        self,
        symbol: str,
        adapter_a,
        adapter_b,
        side_a: str,
        side_b: str,
        quantity: int,
        price_a: float,
        price_b: float,
    ) -> OrderResult:
        """
        Execute arbitrage using market orders.

        Market orders are verified via POSITION, not order status.
        Reason: market orders fill instantly and disappear from open-order lists,
        making get_order_status unreliable for filled market orders on exchanges
        like Bybit (which requires special params for closed orders and has a
        500-order history limit).
        """
        order_a_id = adapter_a.place_market_order(symbol, side_a, quantity)
        order_b_id = adapter_b.place_market_order(symbol, side_b, quantity)

        if order_a_id is None:
            if order_b_id:
                adapter_b.cancel_order(symbol, order_b_id)
            return OrderResult(status="failed", error_a="order_a_submit_failed")

        if order_b_id is None:
            adapter_a.cancel_order(symbol, order_a_id)
            return OrderResult(
                status="failed",
                order_a_id=order_a_id,
                error_b="order_b_submit_failed",
            )

        # Poll via position: market order that fills = position created
        # Wait a moment for exchange to settle and update position data
        time.sleep(1.0)

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            pos_a = adapter_a.get_position(symbol)
            pos_b = adapter_b.get_position(symbol)

            has_pos_a = pos_a is not None and pos_a.get("quantity", 0) > 0
            has_pos_b = pos_b is not None and pos_b.get("quantity", 0) > 0

            if has_pos_a and has_pos_b:
                return OrderResult(
                    status="filled",
                    order_a_id=order_a_id,
                    order_b_id=order_b_id,
                    fill_price_a=price_a,
                    fill_price_b=price_b,
                )

            if has_pos_a and not has_pos_b:
                adapter_a.cancel_order(symbol, order_a_id)
                return OrderResult(
                    status="partial_fill",
                    order_a_id=order_a_id,
                    order_b_id=order_b_id,
                    error_b="no_position",
                )
            if has_pos_b and not has_pos_a:
                adapter_b.cancel_order(symbol, order_b_id)
                return OrderResult(
                    status="partial_fill",
                    order_a_id=order_a_id,
                    order_b_id=order_b_id,
                    error_a="no_position",
                )

            # Neither has position yet — wait and retry
            time.sleep(self.poll_interval)

        # Timeout — cancel any open orders
        adapter_a.cancel_order(symbol, order_a_id)
        adapter_b.cancel_order(symbol, order_b_id)
        return OrderResult(
            status="timeout",
            order_a_id=order_a_id,
            order_b_id=order_b_id,
        )

    def _execute_limit(
        self,
        symbol: str,
        adapter_a,
        adapter_b,
        side_a: str,
        side_b: str,
        quantity: int,
        price_a: float,
        price_b: float,
    ) -> OrderResult:
        """Execute arbitrage using FOK limit orders."""
        order_a_id = adapter_a.place_fok_order(symbol, side_a, quantity, price_a)
        order_b_id = adapter_b.place_fok_order(symbol, side_b, quantity, price_b)

        if order_a_id is None:
            if order_b_id:
                adapter_b.cancel_order(symbol, order_b_id)
            return OrderResult(status="failed", error_a="order_a_submit_failed")

        if order_b_id is None:
            adapter_a.cancel_order(symbol, order_a_id)
            return OrderResult(
                status="failed",
                order_a_id=order_a_id,
                error_b="order_b_submit_failed",
            )

        # Poll for fills
        deadline = time.time() + self.timeout
        order_a_filled = False
        order_b_filled = False

        while time.time() < deadline:
            if not order_a_filled:
                status_a = adapter_a.get_order_status(symbol, order_a_id)
                if status_a == "filled":
                    order_a_filled = True
                elif status_a in ("cancelled", "partial"):
                    # A not fully filled, cancel B
                    adapter_b.cancel_order(symbol, order_b_id)
                    return OrderResult(
                        status="partial_fill",
                        order_a_id=order_a_id,
                        order_b_id=order_b_id,
                        error_a=f"status={status_a}",
                    )

            if not order_b_filled:
                status_b = adapter_b.get_order_status(symbol, order_b_id)
                if status_b == "filled":
                    order_b_filled = True
                elif status_b in ("cancelled", "partial"):
                    adapter_a.cancel_order(symbol, order_a_id)
                    return OrderResult(
                        status="partial_fill",
                        order_a_id=order_a_id,
                        order_b_id=order_b_id,
                        error_b=f"status={status_b}",
                    )

            # Check if one side is filled and the other has failed/been cancelled
            if order_a_filled and not order_b_filled:
                status_b = adapter_b.get_order_status(symbol, order_b_id)
                if status_b in ("cancelled", "partial", "unfilled"):
                    adapter_a.cancel_order(symbol, order_a_id)
                    return OrderResult(
                        status="partial_fill",
                        order_a_id=order_a_id,
                        order_b_id=order_b_id,
                        error_b=f"status={status_b}",
                    )
            if order_b_filled and not order_a_filled:
                status_a = adapter_a.get_order_status(symbol, order_a_id)
                if status_a in ("cancelled", "partial", "unfilled"):
                    adapter_b.cancel_order(symbol, order_b_id)
                    return OrderResult(
                        status="partial_fill",
                        order_a_id=order_a_id,
                        order_b_id=order_b_id,
                        error_a=f"status={status_a}",
                    )

            if order_a_filled and order_b_filled:
                return OrderResult(
                    status="filled",
                    order_a_id=order_a_id,
                    order_b_id=order_b_id,
                    fill_price_a=price_a,
                    fill_price_b=price_b,
                )

            time.sleep(self.poll_interval)

        # Timeout: cancel unfilled orders
        if not order_a_filled:
            adapter_a.cancel_order(symbol, order_a_id)
        if not order_b_filled:
            adapter_b.cancel_order(symbol, order_b_id)

        return OrderResult(
            status="timeout",
            order_a_id=order_a_id,
            order_b_id=order_b_id,
        )
