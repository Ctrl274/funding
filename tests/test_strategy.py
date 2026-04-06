from strategy import StrategyEngine
from exchanges.base import FundingRate


def test_find_opportunities():
    engine = StrategyEngine(min_rate_diff=0.01, max_concurrent=3)
    rates = {
        "binance": {
            "BTC-USDT": FundingRate("BTC-USDT", 0.0001, 1700000000),
            "ETH-USDT": FundingRate("ETH-USDT", 0.0002, 1700000000),
        },
        "bybit": {
            "BTC-USDT": FundingRate("BTC-USDT", 0.0003, 1700000000),
            "ETH-USDT": FundingRate("ETH-USDT", 0.0001, 1700000000),
        },
        "mexc": {
            "BTC-USDT": FundingRate("BTC-USDT", 0.0002, 1700000000),
        },
    }
    opportunities = engine.find_opportunities(rates)
    assert len(opportunities) >= 1
    btc_opp = next((o for o in opportunities if o.symbol == "BTC-USDT"), None)
    assert btc_opp is not None
    assert btc_opp.high_exchange == "bybit"
    assert btc_opp.low_exchange == "binance"


def test_calculate_position_size_fixed():
    engine = StrategyEngine(position_mode="fixed", position_value=1000)
    size = engine.calculate_position_size("BTC-USDT", 50000, {"binance": 10000, "bybit": 10000})
    assert size == 1000


def test_calculate_position_size_percent():
    engine = StrategyEngine(position_mode="percent", position_percent=5)
    size = engine.calculate_position_size("BTC-USDT", 50000, {"binance": 10000, "bybit": 10000})
    assert size == 1000
