"""
Execution engine.
Handles FOK order placement, fill monitoring, and partial fill handling.
"""
import time
from dataclasses import dataclass, field
from typing import Optional
from exchanges.base import ExchangeAdapter


@dataclass
class OrderResult:
    status: str  # "filled" | "partial_fill" | "failed" | "timeout"
    order_a_id: Optional[str] = None
    order_b_id: Optional[str] = None
    fill_price_a: Optional[float] = None
    fill_price_b: Optional[float] = None
    error_a: Optional[str] = None
    error_b: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class ExecutionEngine:
    def __init__(self, timeout: int = 30, poll_interval: float = 1.0):
        self.timeout = timeout
        self.poll_interval = poll_interval

    def execute_arbitrage(
        self,
        symbol: str,
        adapter_a: ExchangeAdapter,
        adapter_b: ExchangeAdapter,
        side_a: str,
        side_b: str,
        quantity: int,
        price_a: float,
        price_b: float,
    ) -> OrderResult:
        order_a_id = adapter_a.place_fok_order(symbol, side_a, quantity, price_a)
        order_b_id = adapter_b.place_fok_order(symbol, side_b, quantity, price_b)

        if order_a_id is None:
            if order_b_id:
                adapter_b.cancel_order(symbol, order_b_id)
            return OrderResult(status="failed", error_a="order_a_submit_failed")

        if order_b_id is None:
            adapter_a.cancel_order(symbol, order_a_id)
            return OrderResult(status="failed", order_a_id=order_a_id, error_b="order_b_submit_failed")

        deadline = time.time() + self.timeout
        order_a_filled = False
        order_b_filled = False

        while time.time() < deadline:
            if not order_a_filled:
                status_a = adapter_a.get_order_status(symbol, order_a_id)
                if status_a == "filled":
                    order_a_filled = True
                elif status_a in ("cancelled", "unfilled"):
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
                elif status_b in ("cancelled", "unfilled"):
                    adapter_a.cancel_order(symbol, order_a_id)
                    return OrderResult(
                        status="partial_fill",
                        order_a_id=order_a_id,
                        order_b_id=order_b_id,
                        error_b=f"status={status_b}",
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

        if not order_a_filled:
            adapter_a.cancel_order(symbol, order_a_id)
        if not order_b_filled:
            adapter_b.cancel_order(symbol, order_b_id)

        return OrderResult(
            status="timeout",
            order_a_id=order_a_id,
            order_b_id=order_b_id,
        )
