import tempfile
import os
from db import Database


def test_save_and_load_trade():
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
            quantity=1,
            side_a="BUY",
            side_b="SELL"
        )
        trades = db.get_history(limit=10)
        assert len(trades) == 1
        assert trades[0]["symbol"] == "BTC-USDT"
        assert trades[0]["result"] == "filled"
        assert trades[0]["profit"] == 1.5
        assert trades[0]["quantity"] == 1


def test_save_and_load_position():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)
        db.save_position(
            symbol="BTC-USDT",
            high_exchange="bybit",
            low_exchange="binance",
            side_a="BUY",
            side_b="SELL",
            quantity=1,
            open_time="2026-04-07T00:00:00"
        )
        positions = db.get_positions()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "BTC-USDT"
        assert positions[0]["status"] == "open"
        assert positions[0]["quantity"] == 1


def test_close_position():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)
        db.save_position(
            symbol="BTC-USDT",
            high_exchange="bybit",
            low_exchange="binance",
            side_a="BUY",
            side_b="SELL",
            quantity=1,
            open_time="2026-04-07T00:00:00"
        )
        db.close_position("BTC-USDT")
        positions = db.get_positions()
        assert len(positions) == 0


def test_multiple_trades_history():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)
        for i in range(5):
            db.save_trade(
                symbol=f"BTC-{i}",
                high_exchange="bybit",
                low_exchange="binance",
                rate_diff=0.01 * i,
                result="filled"
            )
        trades = db.get_history(limit=3)
        assert len(trades) == 3


def test_position_update_replaces():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)
        db.save_position(
            symbol="BTC-USDT",
            high_exchange="bybit",
            low_exchange="binance",
            side_a="BUY",
            side_b="SELL",
            quantity=1,
            open_time="2026-04-07T00:00:00"
        )
        db.save_position(
            symbol="BTC-USDT",
            high_exchange="mexc",
            low_exchange="binance",
            side_a="SELL",
            side_b="BUY",
            quantity=2,
            open_time="2026-04-07T01:00:00"
        )
        positions = db.get_positions()
        assert len(positions) == 1
        assert positions[0]["high_exchange"] == "mexc"
        assert positions[0]["quantity"] == 2
