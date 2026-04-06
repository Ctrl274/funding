import pytest
from unittest.mock import MagicMock, patch
from exchanges.mexc import MexcAdapter


def test_get_funding_rates():
    mock_exchange = MagicMock()
    mock_exchange.fetch_funding_rates.return_value = {
        "BTC/USDT:USDT": {"lastFundingRate": "0.00011000", "nextFundingTime": 1700000000000},
    }

    with patch("ccxt.mexc", return_value=mock_exchange):
        adapter = MexcAdapter("key", "secret")
        result = adapter.get_funding_rates()

    assert "BTC-USDT" in result
    assert result["BTC-USDT"].rate == pytest.approx(0.00011)
