from exchanges.base import FundingRate, SymbolFunding

def test_funding_rate_dataclass():
    fr = FundingRate(symbol="BTC-USDT", rate=0.0001, next_settlement=1700000000)
    assert fr.symbol == "BTC-USDT"
    assert fr.rate == 0.0001
    assert fr.rate_percent == 0.01

def test_symbol_funding_dataclass():
    sf = SymbolFunding(symbol="BTC-USDT", exchange_a="binance", exchange_b="bybit", rate_a=0.0001, rate_b=0.0002)
    assert sf.rate_diff == 0.0001
    assert sf.rate_diff_percent == 0.01
    assert sf.high_exchange == "bybit"
    assert sf.low_exchange == "binance"
