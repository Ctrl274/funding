import pytest
from unittest.mock import MagicMock, patch
from exchanges.binance import BinanceAdapter
from exchanges.base import FundingRate


def test_get_funding_rates():
    mock_exchange = MagicMock()
    mock_exchange.fetch_funding_rates.return_value = {
        "BTC/USDT:USDT": {"lastFundingRate": "0.00010000", "nextFundingTime": 1700000000000},
        "ETH/USDT:USDT": {"lastFundingRate": "-0.00005000", "nextFundingTime": 1700000000000},
    }

    with patch("ccxt.binance", return_value=mock_exchange):
        adapter = BinanceAdapter("key", "secret")
        result = adapter.get_funding_rates()

    assert "BTC-USDT" in result
    assert result["BTC-USDT"].rate == pytest.approx(0.0001)
    assert result["BTC-USDT"].rate_percent == pytest.approx(0.01)
    assert "ETH-USDT" in result
    assert result["ETH-USDT"].rate == pytest.approx(-0.00005)
