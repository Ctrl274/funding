from unittest.mock import MagicMock, patch
from notifier import Notifier


def test_build_detailed_message_filled():
    notifier = Notifier(webhook="http://test", detail_level="detailed")
    result = MagicMock()
    result.status = "filled"
    result.order_a_id = "123"
    result.order_b_id = "456"
    result.error_a = None
    result.error_b = None
    msg = notifier._build_message(
        symbol="BTC-USDT",
        high_ex="bybit",
        low_ex="binance",
        rate_diff=0.02,
        result=result,
    )
    assert "BTC-USDT" in msg
    assert "bybit" in msg
    assert "binance" in msg
    assert "filled" in msg
    assert "0.0200%" in msg


def test_build_detailed_message_failed():
    notifier = Notifier(webhook="http://test", detail_level="detailed")
    result = MagicMock()
    result.status = "partial_fill"
    result.order_a_id = None
    result.order_b_id = None
    result.error_a = "unfilled"
    result.error_b = None
    msg = notifier._build_message(
        symbol="ETH-USDT",
        high_ex="mexc",
        low_ex="binance",
        rate_diff=0.015,
        result=result,
    )
    assert "ETH-USDT" in msg
    assert "partial_fill" in msg
    assert "Error A: unfilled" in msg


def test_build_simple_message():
    notifier = Notifier(webhook="http://test", detail_level="simple")
    result = MagicMock()
    result.status = "filled"
    msg = notifier._build_message(
        symbol="BTC-USDT",
        high_ex="bybit",
        low_ex="binance",
        rate_diff=0.02,
        result=result,
    )
    assert msg == "[Funding Arbitrage] BTC-USDT bybit-binance filled"


@patch("notifier.httpx.post")
def test_send_success(mock_post):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    notifier = Notifier(webhook="http://test")
    result = notifier.send("test message")

    assert result is True
    mock_post.assert_called_once()


@patch("notifier.httpx.post")
def test_send_failure(mock_post):
    mock_post.side_effect = Exception("Network error")

    notifier = Notifier(webhook="http://test")
    result = notifier.send("test message")

    assert result is False


def test_send_no_webhook():
    notifier = Notifier(webhook="")
    result = notifier.send("test message")
    assert result is False
