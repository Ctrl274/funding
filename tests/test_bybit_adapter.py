import pytest
from unittest.mock import MagicMock, patch
from exchanges.bybit import BybitAdapter


def test_get_funding_rates():
    mock_exchange = MagicMock()
    mock_exchange.fetch_funding_rates.return_value = {
        "BTC/USDT:USDT": {"lastFundingRate": "0.00012000", "nextFundingTime": 1700000000000},
    }

    with patch("ccxt.bybit", return_value=mock_exchange):
        adapter = BybitAdapter("key", "secret")
        result = adapter.get_funding_rates()

    assert "BTC-USDT" in result
    assert result["BTC-USDT"].rate == pytest.approx(0.00012)
    assert result["BTC-USDT"].rate_percent == pytest.approx(0.012)
