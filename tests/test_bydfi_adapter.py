import pytest
from unittest.mock import patch, MagicMock
from exchanges.bydfi import BydfiAdapter


def test_get_funding_rates():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {
                "symbol": "BTC-USDT",
                "fundingRate": "0.00010000",
                "nextFundingTime": 1700000000000,
            }
        ]
    }

    with patch("requests.get", return_value=mock_resp):
        adapter = BydfiAdapter("key", "secret")
        result = adapter.get_funding_rates()

    assert "BTC-USDT" in result
    assert result["BTC-USDT"].rate == pytest.approx(0.0001)
