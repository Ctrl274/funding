"""
Lark Notifier.
Sends detailed notifications for every arbitrage trade (success or failure).
"""
import logging
import httpx


logger = logging.getLogger(__name__)


class Notifier:
    """
    Lark Webhook Notifier.
    """

    def __init__(self, webhook: str, detail_level: str = "detailed"):
        self.webhook = webhook
        self.detail_level = detail_level

    def send(self, message: str) -> bool:
        """Send Lark message."""
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

    def send_arbitrage_result(self, opportunity, result) -> bool:
        """Send arbitrage result notification."""
        msg = self._build_message(
            symbol=opportunity.symbol,
            high_ex=opportunity.high_exchange,
            low_ex=opportunity.low_exchange,
            rate_diff=opportunity.rate_diff_percent,
            result=result,
        )
        return self.send(msg)

    def send_skip_reason(self, opportunity, reason: str, details: str = "") -> bool:
        """Send notification when opportunity is skipped (e.g. no balance, position too small)."""
        msg = (
            f"[Skip] {opportunity.symbol}\n"
            f"Pair: {opportunity.high_exchange} <-> {opportunity.low_exchange}\n"
            f"Rate Diff: {opportunity.rate_diff_percent:.4f}%\n"
            f"Reason: {reason}"
            + (f"\nDetails: {details}" if details else "")
        )
        return self.send(msg)

    def _build_message(self, symbol, high_ex, low_ex, rate_diff, result) -> str:
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
