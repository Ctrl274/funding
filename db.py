"""
SQLite Persistence.
Records arbitrage trades and positions.
"""
import sqlite3
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ_UTC8 = timezone(timedelta(hours=8))


class Database:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = Path(__file__).parent / "arbitrage.db"
        self._db_path = db_path
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA timezone = '+08:00'")
        return conn

    def _init_db(self):
        with self._connect() as conn:
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

    def save_trade(
        self,
        symbol: str,
        high_exchange: str,
        low_exchange: str,
        rate_diff: float,
        result: str,
        quantity: int = None,
        side_a: str = None,
        side_b: str = None,
        profit: float = None,
        error_a: str = None,
        error_b: str = None,
    ):
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO trades
                   (created_at, symbol, high_exchange, low_exchange, rate_diff,
                    quantity, side_a, side_b, result, profit, error_a, error_b)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now(TZ_UTC8).isoformat(),
                    symbol, high_exchange, low_exchange, rate_diff,
                    quantity, side_a, side_b, result, profit, error_a, error_b,
                )
            )
            conn.commit()

    def get_history(self, limit: int = 20, offset: int = 0) -> Dict:
        """Fetch paginated history records ordered by time descending.

        Returns dict with:
            - items: list of trade records
            - total: total count of all records
            - limit: page size
            - offset: current offset
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT COUNT(*) as cnt FROM trades")
            total = cur.fetchone()["cnt"]

            cur = conn.execute(
                "SELECT * FROM trades ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
            rows = cur.fetchall()
            return {
                "items": [dict(row) for row in rows],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    def save_position(self, symbol: str, **kwargs):
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO positions
                   (symbol, high_exchange, low_exchange, side_a, side_b, quantity, open_time, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (symbol, kwargs["high_exchange"], kwargs["low_exchange"],
                 kwargs["side_a"], kwargs["side_b"], kwargs["quantity"],
                 kwargs["open_time"], kwargs.get("status", "open"))
            )
            conn.commit()

    def get_positions(self) -> List[Dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM positions WHERE status='open'")
            rows = cur.fetchall()
            return [dict(row) for row in rows]

    def close_position(self, symbol: str):
        with self._connect() as conn:
            conn.execute(
                "UPDATE positions SET status='closed' WHERE symbol=?",
                (symbol,)
            )
            conn.commit()
