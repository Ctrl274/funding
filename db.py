"""
SQLite persistence.
Stores trade history and open positions.
"""
import sqlite3
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path


class Database:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path(__file__).parent / "arbitrage.db")
        self._db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                high_exchange TEXT NOT NULL,
                low_exchange TEXT NOT NULL,
                rate_diff REAL NOT NULL,
                quantity INTEGER,
                side_a TEXT,
                side_b TEXT,
                result TEXT NOT NULL,
                profit REAL,
                error_a TEXT,
                error_b TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT UNIQUE NOT NULL,
                high_exchange TEXT NOT NULL,
                low_exchange TEXT NOT NULL,
                side_a TEXT NOT NULL,
                side_b TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                open_time TEXT NOT NULL,
                status TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def save_trade(self, symbol: str, high_exchange: str, low_exchange: str,
                   rate_diff: float, result: str, **kwargs):
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            """INSERT INTO trades
               (created_at, symbol, high_exchange, low_exchange, rate_diff,
                quantity, side_a, side_b, result, profit, error_a, error_b)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.utcnow().isoformat(),
                symbol, high_exchange, low_exchange, rate_diff,
                kwargs.get("quantity"),
                kwargs.get("side_a"),
                kwargs.get("side_b"),
                result,
                kwargs.get("profit"),
                kwargs.get("error_a"),
                kwargs.get("error_b"),
            )
        )
        conn.commit()
        conn.close()

    def get_history(self, limit: int = 100) -> List[Dict]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        rows = cur.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def save_position(self, symbol: str, **kwargs):
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            """INSERT OR REPLACE INTO positions
               (symbol, high_exchange, low_exchange, side_a, side_b, quantity, open_time, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol, kwargs["high_exchange"], kwargs["low_exchange"],
             kwargs["side_a"], kwargs["side_b"], kwargs["quantity"],
             kwargs["open_time"], kwargs.get("status", "open"))
        )
        conn.commit()
        conn.close()

    def get_positions(self) -> List[Dict]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM positions WHERE status='open'")
        rows = cur.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def close_position(self, symbol: str):
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            "UPDATE positions SET status='closed' WHERE symbol=?",
            (symbol,)
        )
        conn.commit()
        conn.close()
