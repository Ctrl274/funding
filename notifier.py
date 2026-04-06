"""
Lark notification.
Sends detailed notifications for every arbitrage attempt.
"""
import logging
import httpx
from typing import Optional
from strategy import ArbitrageOpportunity
from executor import OrderResult

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, webhook: str = "", detail_level: str = "detailed"):
        self.webhook = webhook
        self.detail_level = detail_level

    def send(self, message: str) -> bool:
        if not self.webhook:
            logger.warning("Lark webhook not configured")
            return False

        payload = {
            "msg_type": "text",
            "content": {"text": message},
        }
        try:
            resp = httpx.post(self.webhook, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info("Lark notification sent")
            return True
        except Exception as e:
            logger.error(f"Failed to send Lark notification: {e}")
            return False

    def send_arbitrage_result(self, opportunity: ArbitrageOpportunity, result: OrderResult) -> bool:
        msg = self._build_message(
            symbol=opportunity.symbol,
            high_ex=opportunity.high_exchange,
            low_ex=opportunity.low_exchange,
            rate_diff=opportunity.rate_diff_percent,
            result=result,
        )
        return self.send(msg)

    def _build_message(self, symbol: str, high_ex: str, low_ex: str, rate_diff: float, result: OrderResult) -> str:
        if self.detail_level == "detailed":
            lines = [
                f"[Funding Arbitrage] {symbol}",
                f"",
                f"Exchange Pair: {high_ex} <-> {low_ex}",
                f"Funding Rate Diff: {rate_diff:.4f}%",
                f"Result: {result.status}",
            ]
            if result.order_a_id:
                lines.append(f"Order A ({high_ex}): {result.order_a_id}")
            if result.order_b_id:
                lines.append(f"Order B ({low_ex}): {result.order_b_id}")
            if result.error_a:
                lines.append(f"Error A: {result.error_a}")
            if result.error_b:
                lines.append(f"Error B: {result.error_b}")
            return "\n".join(lines)
        else:
            return f"[Funding Arbitrage] {symbol} {high_ex}-{low_ex} {result.status}"
