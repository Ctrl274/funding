"""
Execution Engine.
Handles FOK limit orders, fill listening, and partial fill handling.
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
    1. Send FOK limit orders to both exchanges simultaneously
    2. Poll for fill status (N second timeout)
    3. Both filled -> success
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
    ) -> OrderResult:
        """
        Execute arbitrage.
        Returns OrderResult.
        """
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
