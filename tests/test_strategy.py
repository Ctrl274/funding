"""
Tests for Strategy Engine.
"""
import pytest
from strategy import StrategyEngine, ArbitrageOpportunity
from exchanges.base import FundingRate


class TestFindOpportunities:
    def test_no_opportunities_below_threshold(self):
        """费率差小于阈值时应返回空列表"""
        engine = StrategyEngine(min_rate_diff=0.01, max_concurrent=3)
        rates = {
            "binance": {
                "BTC-USDT": FundingRate("BTC-USDT", 0.0001, 1700000000),
            },
            "bybit": {
                "BTC-USDT": FundingRate("BTC-USDT", 0.00015, 1700000000),
            },
        }
        # 费率差 = 0.005% < 0.01%，不应有机会
        opportunities = engine.find_opportunities(rates)
        assert opportunities == []

    def test_finds_single_opportunity(self):
        """找到单一套利机会"""
        engine = StrategyEngine(min_rate_diff=0.01, max_concurrent=3)
        rates = {
            "binance": {
                "BTC-USDT": FundingRate("BTC-USDT", 0.0001, 1700000000),
            },
            "bybit": {
                "BTC-USDT": FundingRate("BTC-USDT", 0.0003, 1700000000),
            },
        }
        opportunities = engine.find_opportunities(rates)
        assert len(opportunities) == 1
        assert opportunities[0].symbol == "BTC-USDT"
        assert opportunities[0].high_exchange == "bybit"
        assert opportunities[0].low_exchange == "binance"
        # 费率差 = 0.02%
        assert opportunities[0].rate_diff_percent == pytest.approx(0.02, rel=1e-9)

    def test_finds_multiple_opportunities_sorted_by_rate_diff(self):
        """多个机会时按费率差降序排列"""
        engine = StrategyEngine(min_rate_diff=0.005, max_concurrent=3)
        rates = {
            "binance": {
                "BTC-USDT": FundingRate("BTC-USDT", 0.0001, 1700000000),
                "ETH-USDT": FundingRate("ETH-USDT", 0.0001, 1700000000),
            },
            "bybit": {
                "BTC-USDT": FundingRate("BTC-USDT", 0.0005, 1700000000),
                "ETH-USDT": FundingRate("ETH-USDT", 0.0003, 1700000000),
            },
        }
        opportunities = engine.find_opportunities(rates)
        assert len(opportunities) == 2
        # BTC 费率差更大，排前面
        assert opportunities[0].symbol == "BTC-USDT"
        assert opportunities[1].symbol == "ETH-USDT"

    def test_respects_max_concurrent_limit(self):
        """最多返回 max_concurrent 个机会"""
        engine = StrategyEngine(min_rate_diff=0.001, max_concurrent=2)
        rates = {
            "binance": {
                "BTC-USDT": FundingRate("BTC-USDT", 0.0001, 1700000000),
                "ETH-USDT": FundingRate("ETH-USDT", 0.0002, 1700000000),
                "SOL-USDT": FundingRate("SOL-USDT", 0.0003, 1700000000),
            },
            "bybit": {
                "BTC-USDT": FundingRate("BTC-USDT", 0.0005, 1700000000),
                "ETH-USDT": FundingRate("ETH-USDT", 0.0008, 1700000000),
                "SOL-USDT": FundingRate("SOL-USDT", 0.0011, 1700000000),
            },
        }
        opportunities = engine.find_opportunities(rates)
        assert len(opportunities) == 2  # 限制为 2

    def test_paired_exchanges_all_combinations(self):
        """两两配对检查所有交易所组合"""
        engine = StrategyEngine(min_rate_diff=0.001, max_concurrent=10)
        rates = {
            "binance": {"BTC-USDT": FundingRate("BTC-USDT", 0.0001, 1700000000)},
            "bybit":   {"BTC-USDT": FundingRate("BTC-USDT", 0.0003, 1700000000)},
            "mexc":    {"BTC-USDT": FundingRate("BTC-USDT", 0.0005, 1700000000)},
        }
        opportunities = engine.find_opportunities(rates)
        # binance-bybit, binance-mexc, bybit-mexc => 3 pairs
        assert len(opportunities) == 3
        symbols = {o.symbol for o in opportunities}
        assert symbols == {"BTC-USDT"}

    def test_common_symbols_only(self):
        """只匹配共同币对"""
        engine = StrategyEngine(min_rate_diff=0.001, max_concurrent=10)
        rates = {
            "binance": {
                "BTC-USDT": FundingRate("BTC-USDT", 0.0001, 1700000000),
                "ETH-USDT": FundingRate("ETH-USDT", 0.0001, 1700000000),
            },
            "bybit": {
                "BTC-USDT": FundingRate("BTC-USDT", 0.0003, 1700000000),
                # bybit 没有 ETH
            },
        }
        opportunities = engine.find_opportunities(rates)
        assert len(opportunities) == 1
        assert opportunities[0].symbol == "BTC-USDT"


class TestCalculatePositionSize:
    def test_fixed_mode_returns_config_value(self):
        """fixed 模式返回配置值"""
        engine = StrategyEngine(position_mode="fixed", position_value=1000)
        size = engine.calculate_position_size("BTC-USDT", 50000, {"binance": 10000, "bybit": 10000})
        assert size == 1000

    def test_percent_mode_uses_total_balance(self):
        """percent 模式按账户总余额百分比计算"""
        engine = StrategyEngine(position_mode="percent", position_percent=5)
        size = engine.calculate_position_size("BTC-USDT", 50000, {"binance": 10000, "bybit": 10000})
        # 总余额 20000 * 5% = 1000
        assert size == 1000

    def test_percent_mode_with_single_balance(self):
        """percent 模式只用单边余额"""
        engine = StrategyEngine(position_mode="percent", position_percent=10)
        size = engine.calculate_position_size("BTC-USDT", 50000, {"binance": 5000})
        assert size == 500  # 5000 * 10% = 500


class TestContractsFromUsdt:
    def test_default_contract_size_is_coins(self):
        """默认 contract_size=1，quantity = 币数"""
        engine = StrategyEngine()
        # 1000 USDT / 0.01 price = 100000 coins
        contracts = engine.contracts_from_usdt(1000, 0.01)
        assert contracts == 100000

    def test_btc_position(self):
        """BTC 仓位：1000 USDT / 50000 * 1 = 0.02 -> 0"""
        engine = StrategyEngine()
        contracts = engine.contracts_from_usdt(1000, 50000)
        assert contracts == 0

    def test_mexc_with_contract_size(self):
        """MEXC: contract_size=0.0001, BTC 价格 50000
        quantity = 1000 / (0.0001 * 50000) = 200 contracts"""
        engine = StrategyEngine()
        contracts = engine.contracts_from_usdt(1000, 50000, contract_size=0.0001)
        assert contracts == 200

    def test_rounds_down(self):
        """向下取整"""
        engine = StrategyEngine()
        # 999 / (1 * 100) = 9.99 -> 9
        contracts = engine.contracts_from_usdt(999, 100)
        assert contracts == 9

    def test_small_amount_returns_zero(self):
        """金额过小返回 0"""
        engine = StrategyEngine()
        contracts = engine.contracts_from_usdt(10, 50000)
        assert contracts == 0


class TestClampQuantity:
    def test_clamps_to_max_position(self):
        """数量超过最大持仓时截断"""
        engine = StrategyEngine()
        mock_adapter = type("Mock", (), {
            "get_max_position": lambda self, s: 5.0
        })()
        qty = engine.clamp_quantity("BTC-USDT", 100, mock_adapter)
        assert qty == 5

    def test_unchanged_if_under_limit(self):
        """数量在限制内不变"""
        engine = StrategyEngine()
        mock_adapter = type("Mock", (), {
            "get_max_position": lambda self, s: 100.0
        })()
        qty = engine.clamp_quantity("BTC-USDT", 10, mock_adapter)
        assert qty == 10

    def test_returns_none_when_no_limit(self):
        """没有最大持仓限制时不变"""
        engine = StrategyEngine()
        mock_adapter = type("Mock", (), {
            "get_max_position": lambda self, s: None
        })()
        qty = engine.clamp_quantity("BTC-USDT", 10, mock_adapter)
        assert qty == 10


class TestArbitrageOpportunityDataclass:
    def test_direction_long_high_short_low(self):
        """费率高的做多，费率低的做空"""
        opp = ArbitrageOpportunity(
            symbol="BTC-USDT",
            high_exchange="bybit",
            low_exchange="binance",
            high_rate=0.0003,
            low_rate=0.0001,
            rate_diff_percent=0.02,
            estimated_profit=0,
            side_a="BUY",
            side_b="SELL",
            next_settlement=1700000000,
        )
        assert opp.high_exchange == "bybit"
        assert opp.low_exchange == "binance"
