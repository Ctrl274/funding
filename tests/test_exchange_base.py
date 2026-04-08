import pytest
from exchanges.base import FundingRate, SymbolFunding, ExchangeAdapter


def test_funding_rate_basic():
    fr = FundingRate(symbol="BTC-USDT", rate=0.0001, next_settlement=1700000000)
    assert fr.symbol == "BTC-USDT"
    assert fr.rate == 0.0001
    assert fr.rate_percent == 0.01


def test_funding_rate_negative():
    fr = FundingRate(symbol="ETH-USDT", rate=-0.00005, next_settlement=1700000000)
    assert fr.rate_percent == -0.005


def test_symbol_funding_dataclass():
    sf = SymbolFunding(
        symbol="BTC-USDT",
        exchange_a="binance",
        exchange_b="bybit",
        rate_a=0.0001,
        rate_b=0.0003,
    )
    assert abs(sf.rate_diff - 0.0002) < 1e-10
    assert abs(sf.rate_diff_percent - 0.02) < 1e-10
    assert sf.high_exchange == "bybit"
    assert sf.low_exchange == "binance"
    assert sf.direction["long"] == "bybit"
    assert sf.direction["short"] == "binance"


def test_exchange_adapter_is_abstract():
    """Cannot instantiate ExchangeAdapter directly"""
    with pytest.raises(TypeError):
        ExchangeAdapter("key", "secret")
