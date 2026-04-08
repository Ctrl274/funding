"""
Tests for SQLite Database.
"""
import pytest
import tempfile
import os
from db import Database


class TestDatabaseTrades:
    def test_save_and_get_history(self):
        """保存交易记录并查询"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)
            db.save_trade(
                symbol="BTC-USDT",
                high_exchange="bybit",
                low_exchange="binance",
                rate_diff=0.02,
                result="filled",
                profit=1.5,
            )
            trades = db.get_history(limit=10)
            assert len(trades) == 1
            assert trades[0]["symbol"] == "BTC-USDT"
            assert trades[0]["result"] == "filled"
            assert trades[0]["profit"] == 1.5

    def test_get_history_respects_limit(self):
        """get_history 限制条数"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)
            for i in range(10):
                db.save_trade(symbol=f"SYM{i}", high_exchange="a", low_exchange="b",
                              rate_diff=0.01, result="filled")
            trades = db.get_history(limit=3)
            assert len(trades) == 3

    def test_save_trade_with_all_fields(self):
        """保存包含所有字段的交易记录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)
            db.save_trade(
                symbol="ETH-USDT",
                high_exchange="mexc",
                low_exchange="binance",
                rate_diff=0.015,
                result="partial_fill",
                quantity=5,
                side_a="BUY",
                side_b="SELL",
                profit=-0.5,
                error_a="status=unfilled",
                error_b=None,
            )
            trades = db.get_history(limit=1)
            assert len(trades) == 1
            assert trades[0]["symbol"] == "ETH-USDT"
            assert trades[0]["result"] == "partial_fill"
            assert trades[0]["profit"] == -0.5
            assert trades[0]["error_a"] == "status=unfilled"


class TestDatabasePositions:
    def test_save_and_get_positions(self):
        """保存和查询持仓"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)
            db.save_position(
                symbol="BTC-USDT",
                high_exchange="bybit",
                low_exchange="binance",
                side_a="BUY",
                side_b="SELL",
                quantity=5,
                open_time="2024-01-01T00:00:00",
            )
            positions = db.get_positions()
            assert len(positions) == 1
            assert positions[0]["symbol"] == "BTC-USDT"
            assert positions[0]["high_exchange"] == "bybit"
            assert positions[0]["status"] == "open"

    def test_replace_existing_position(self):
        """同一 symbol 更新持仓（OR REPLACE）"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)
            db.save_position(symbol="BTC-USDT", high_exchange="a", low_exchange="b",
                           side_a="BUY", side_b="SELL", quantity=5,
                           open_time="2024-01-01T00:00:00")
            db.save_position(symbol="BTC-USDT", high_exchange="a", low_exchange="b",
                           side_a="BUY", side_b="SELL", quantity=10,
                           open_time="2024-01-01T01:00:00")
            positions = db.get_positions()
            assert len(positions) == 1
            assert positions[0]["quantity"] == 10

    def test_close_position(self):
        """平仓后从 open 列表移除"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)
            db.save_position(symbol="BTC-USDT", high_exchange="a", low_exchange="b",
                           side_a="BUY", side_b="SELL", quantity=5,
                           open_time="2024-01-01T00:00:00")
            db.close_position("BTC-USDT")
            positions = db.get_positions()
            assert len(positions) == 0
