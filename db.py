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
                    quantity_a INTEGER,
                    quantity_b INTEGER,
                    side_a TEXT,
                    side_b TEXT,
                    result TEXT NOT NULL,
                    profit REAL,
                    fill_price_a REAL,
                    fill_price_b REAL,
                    error_a TEXT,
                    error_b TEXT,
                    close_time TEXT,
                    close_result TEXT,
                    close_price_a REAL,
                    close_price_b REAL,
                    fee_a REAL,
                    fee_b REAL,
                    realized_pnl REAL,
                    target_settlement TEXT
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
                    quantity_a INTEGER,
                    quantity_b INTEGER,
                    open_time TEXT NOT NULL,
                    status TEXT NOT NULL,
                    target_settlement TEXT
                )
            """)
            # Migrate existing tables: add new columns if missing
            self._migrate(conn)
            conn.commit()

    def _migrate(self, conn):
        """Add new columns to existing tables if they don't exist."""
        trade_columns = [row[1] for row in conn.execute("PRAGMA table_info(trades)").fetchall()]
        for col in ("quantity_a", "quantity_b", "close_time", "close_result",
                    "fill_price_a", "fill_price_b",
                    "close_price_a", "close_price_b", "fee_a", "fee_b", "realized_pnl",
                    "target_settlement"):
            if col not in trade_columns:
                col_type = "INTEGER" if "quantity" in col else "REAL" if "pnl" in col or "fee" in col or "price" in col else "TEXT"
                conn.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_type}")

        pos_columns = [row[1] for row in conn.execute("PRAGMA table_info(positions)").fetchall()]
        for col in ("quantity_a", "quantity_b", "target_settlement"):
            if col not in pos_columns:
                conn.execute(f"ALTER TABLE positions ADD COLUMN {col} {'INTEGER' if 'quantity' in col else 'TEXT'}")

    def save_trade(
        self,
        symbol: str,
        high_exchange: str,
        low_exchange: str,
        rate_diff: float,
        result: str,
        quantity: int = None,
        quantity_a: int = None,
        quantity_b: int = None,
        side_a: str = None,
        side_b: str = None,
        profit: float = None,
        fill_price_a: float = None,
        fill_price_b: float = None,
        error_a: str = None,
        error_b: str = None,
        target_settlement: str = None,
    ):
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO trades
                   (created_at, symbol, high_exchange, low_exchange, rate_diff,
                    quantity, quantity_a, quantity_b, side_a, side_b, result,
                    profit, fill_price_a, fill_price_b, error_a, error_b, target_settlement)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now(TZ_UTC8).strftime("%Y-%m-%d %H:%M:%S"),
                    symbol, high_exchange, low_exchange, rate_diff,
                    quantity, quantity_a, quantity_b, side_a, side_b, result,
                    profit, fill_price_a, fill_price_b, error_a, error_b,
                    target_settlement,
                )
            )
            conn.commit()

    def get_open_trade(self, symbol: str) -> Optional[Dict]:
        """Fetch the most recent open trade for a specific symbol."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM trades WHERE symbol=? AND close_time IS NULL ORDER BY created_at DESC LIMIT 1",
                (symbol,)
            )
            row = cur.fetchone()
            return dict(row) if row else None

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
                   (symbol, high_exchange, low_exchange, side_a, side_b,
                    quantity, quantity_a, quantity_b, open_time, status, target_settlement)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (symbol, kwargs["high_exchange"], kwargs["low_exchange"],
                 kwargs["side_a"], kwargs["side_b"], kwargs.get("quantity", 0),
                 kwargs.get("quantity_a"), kwargs.get("quantity_b"),
                 kwargs["open_time"], kwargs.get("status", "open"),
                 kwargs.get("target_settlement"))
            )
            conn.commit()

    def get_positions(self) -> List[Dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM positions WHERE status='open'")
            rows = cur.fetchall()
            return [dict(row) for row in rows]

    def update_trade_close(
        self,
        symbol: str,
        close_result: str,
        close_price_a: float = None,
        close_price_b: float = None,
        fee_a: float = None,
        fee_b: float = None,
        realized_pnl: float = None,
    ):
        """Update the most recent open trade for symbol with close data."""
        with self._connect() as conn:
            conn.execute(
                """UPDATE trades SET
                       close_time = ?,
                       close_result = ?,
                       close_price_a = ?,
                       close_price_b = ?,
                       fee_a = ?,
                       fee_b = ?,
                       realized_pnl = ?
                   WHERE id = (
                       SELECT id FROM trades
                       WHERE symbol = ? AND close_time IS NULL
                       ORDER BY created_at DESC LIMIT 1
                   )""",
                (
                    datetime.now(TZ_UTC8).strftime("%Y-%m-%d %H:%M:%S"),
                    close_result,
                    close_price_a,
                    close_price_b,
                    fee_a,
                    fee_b,
                    realized_pnl,
                    symbol,
                )
            )
            conn.commit()

    def close_position(self, symbol: str):
        with self._connect() as conn:
            conn.execute(
                "UPDATE positions SET status='closed' WHERE symbol=?",
                (symbol,)
            )
            conn.commit()
