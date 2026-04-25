"""
core/crypto_ledger.py — SQLite schema and helpers for the crypto trading system.

Schema (all tables prefixed `crypto_`):
    crypto_orders         — every order request (paper or live).
    crypto_positions      — currently open positions.
    crypto_trades         — closed round-trip trades with realised PnL.
    crypto_pnl_snapshots  — daily PnL roll-ups (one row per mode per day).

Public API:
    init_crypto_db(conn) -> None
    get_daily_pnl(conn, mode) -> float
    get_open_positions(conn, mode) -> list[CryptoPosition]
    get_balance_estimate(conn, initial_balance, mode) -> float
    get_recent_trades(conn, mode, days, min_count) -> list[dict]
    write_pnl_snapshot(conn, mode) -> None
"""

from __future__ import annotations

import os
import sqlite3
import time
from datetime import date
from pathlib import Path

from core.crypto_types import CryptoPosition
from core.logger import logger

_DDL = """
CREATE TABLE IF NOT EXISTS crypto_orders (
    id               TEXT PRIMARY KEY,
    symbol           TEXT NOT NULL,
    side             TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    qty_usd          REAL NOT NULL,
    entry_price      REAL NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'filled', 'cancelled', 'rejected')),
    mode             TEXT NOT NULL CHECK (mode IN ('paper', 'live')),
    created_at       REAL NOT NULL,
    binance_order_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_crypto_orders_symbol ON crypto_orders(symbol);
CREATE INDEX IF NOT EXISTS idx_crypto_orders_status ON crypto_orders(status);
CREATE INDEX IF NOT EXISTS idx_crypto_orders_mode   ON crypto_orders(mode);

CREATE TABLE IF NOT EXISTS crypto_positions (
    id                 TEXT PRIMARY KEY,
    symbol             TEXT NOT NULL,
    side               TEXT NOT NULL CHECK (side IN ('long', 'short')),
    entry_price        REAL NOT NULL,
    qty_usd            REAL NOT NULL,
    stop_loss          REAL NOT NULL,
    take_profit        REAL NOT NULL,
    opened_at          REAL NOT NULL,
    mode               TEXT NOT NULL CHECK (mode IN ('paper', 'live')),
    signal_confidence  REAL NOT NULL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_crypto_positions_symbol ON crypto_positions(symbol);
CREATE INDEX IF NOT EXISTS idx_crypto_positions_mode   ON crypto_positions(mode);

CREATE TABLE IF NOT EXISTS crypto_trades (
    id             TEXT PRIMARY KEY,
    symbol         TEXT NOT NULL,
    side           TEXT NOT NULL CHECK (side IN ('long', 'short')),
    entry_price    REAL NOT NULL,
    exit_price     REAL NOT NULL,
    qty_usd        REAL NOT NULL,
    realized_pnl   REAL NOT NULL,
    pnl_pct        REAL NOT NULL,
    opened_at      REAL NOT NULL,
    closed_at      REAL NOT NULL,
    exit_reason    TEXT NOT NULL DEFAULT '',
    mode           TEXT NOT NULL CHECK (mode IN ('paper', 'live'))
);

CREATE INDEX IF NOT EXISTS idx_crypto_trades_symbol ON crypto_trades(symbol);
CREATE INDEX IF NOT EXISTS idx_crypto_trades_closed ON crypto_trades(closed_at);
CREATE INDEX IF NOT EXISTS idx_crypto_trades_mode   ON crypto_trades(mode);

CREATE TABLE IF NOT EXISTS crypto_pnl_snapshots (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    date             TEXT NOT NULL,
    mode             TEXT NOT NULL CHECK (mode IN ('paper', 'live')),
    open_positions   INTEGER NOT NULL DEFAULT 0,
    realized_pnl     REAL NOT NULL DEFAULT 0.0,
    created_at       REAL NOT NULL,
    UNIQUE (date, mode)
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply incremental migrations to existing databases."""
    try:
        conn.execute("ALTER TABLE crypto_orders ADD COLUMN binance_order_id TEXT")
        conn.commit()
        logger.info("crypto_ledger: migrated — added crypto_orders.binance_order_id")
    except sqlite3.OperationalError:
        pass  # column already exists — safe to ignore


_schema_logged = False


def init_crypto_db(conn: sqlite3.Connection) -> None:
    """Create all crypto_* tables in the given connection if absent.

    Sets row_factory to sqlite3.Row on the connection for dict-style access.

    Args:
        conn: An open sqlite3.Connection (paths typically come from
              env `DATABASE_PATH` or default "alphacota.db").
    """
    global _schema_logged
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    conn.commit()
    _migrate(conn)
    if not _schema_logged:
        logger.info("crypto_ledger: schema ready")
        _schema_logged = True


def connect_default() -> sqlite3.Connection:
    """Open a connection to the database path from env or project default.

    Resolves the path from DATABASE_PATH (env), falling back to the
    repository-local "alphacota.db". Parent directories are created on demand.

    Returns:
        An open sqlite3.Connection with the crypto_* schema applied.
    """
    db_path = os.getenv("DATABASE_PATH", "alphacota.db")
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    init_crypto_db(conn)
    return conn


def get_daily_pnl(conn: sqlite3.Connection, mode: str) -> float:
    """Sum realised PnL for today in the given mode.

    Args:
        conn: Open sqlite3 connection.
        mode: "paper" or "live".

    Returns:
        Sum of realized_pnl for today; 0.0 if none / on error.
    """
    today = date.today().isoformat()
    try:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(realized_pnl), 0.0) AS pnl
              FROM crypto_trades
             WHERE mode = ?
               AND date(closed_at, 'unixepoch') = ?
            """,
            (mode, today),
        ).fetchone()
        return float(row["pnl"]) if row is not None else 0.0
    except sqlite3.Error as exc:
        logger.warning("get_daily_pnl: %s", exc)
        return 0.0


def get_open_positions(
    conn: sqlite3.Connection,
    mode: str,
) -> list[CryptoPosition]:
    """Return all currently open positions for the given mode.

    Args:
        conn: Open sqlite3 connection.
        mode: "paper" or "live".

    Returns:
        List of CryptoPosition ordered by opened_at ascending.
    """
    try:
        rows = conn.execute(
            """
            SELECT *
              FROM crypto_positions
             WHERE mode = ?
             ORDER BY opened_at ASC
            """,
            (mode,),
        ).fetchall()
    except sqlite3.Error as exc:
        logger.warning("get_open_positions: %s", exc)
        return []

    out: list[CryptoPosition] = []
    for row in rows:
        try:
            out.append(
                CryptoPosition(
                    id=row["id"],
                    symbol=row["symbol"],
                    side=row["side"],
                    entry_price=float(row["entry_price"]),
                    qty=float(row["qty_usd"]),
                    stop_loss=float(row["stop_loss"]),
                    take_profit=float(row["take_profit"]),
                    opened_at=float(row["opened_at"]),
                    mode=row["mode"],
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("get_open_positions: bad row %s: %s", dict(row), exc)
            continue
    return out


def get_balance_estimate(
    conn: sqlite3.Connection,
    initial_balance: float,
    mode: str,
) -> float:
    """Estimate current free balance = initial + realised PnL - open notional.

    "Free" means: capital not currently locked inside open positions. This is
    the number the sizing engine should use to cap new trades.

    Args:
        conn: Open sqlite3 connection.
        initial_balance: Starting USD balance for the account / paper run.
        mode: "paper" or "live".

    Returns:
        Estimated free balance in USD (non-negative).
    """
    try:
        row_pnl = conn.execute(
            """
            SELECT COALESCE(SUM(realized_pnl), 0.0) AS pnl
              FROM crypto_trades
             WHERE mode = ?
            """,
            (mode,),
        ).fetchone()
        realised = float(row_pnl["pnl"]) if row_pnl is not None else 0.0

        row_locked = conn.execute(
            """
            SELECT COALESCE(SUM(qty_usd), 0.0) AS locked
              FROM crypto_positions
             WHERE mode = ?
            """,
            (mode,),
        ).fetchone()
        locked = float(row_locked["locked"]) if row_locked is not None else 0.0
    except sqlite3.Error as exc:
        logger.warning("get_balance_estimate: %s", exc)
        return max(0.0, float(initial_balance))

    free = float(initial_balance) + realised - locked
    return max(0.0, round(free, 2))


def write_pnl_snapshot(conn: sqlite3.Connection, mode: str) -> None:
    """Upsert a daily PnL snapshot row.

    One row per (date, mode); repeated calls on the same day overwrite the
    previous snapshot so the most recent numbers are always visible.

    Args:
        conn: Open sqlite3 connection.
        mode: "paper" or "live".
    """
    today = date.today().isoformat()
    now = time.time()
    try:
        open_row = conn.execute(
            "SELECT COUNT(*) AS c FROM crypto_positions WHERE mode = ?",
            (mode,),
        ).fetchone()
        open_count = int(open_row["c"]) if open_row is not None else 0
        realised = get_daily_pnl(conn, mode)

        conn.execute(
            """
            INSERT INTO crypto_pnl_snapshots
                (date, mode, open_positions, realized_pnl, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(date, mode) DO UPDATE SET
                open_positions = excluded.open_positions,
                realized_pnl   = excluded.realized_pnl,
                created_at     = excluded.created_at
            """,
            (today, mode, open_count, realised, now),
        )
        conn.commit()
    except sqlite3.Error as exc:
        logger.warning("write_pnl_snapshot: %s", exc)


def get_recent_trades(
    conn: sqlite3.Connection,
    mode: str,
    days: int = 90,
    min_count: int = 50,
) -> list[dict]:
    """Return closed trades from the last `days` days for feedback learning.

    Used by the feedback trainer to build a real-outcome dataset:
        exit_reason == "tp_hit"     → label  1  (long won / short won)
        exit_reason == "sl_hit"     → label -1  (trade failed)
        exit_reason == "signal_flip"→ label  0  (flat / neutral exit)

    Returns an empty list when fewer than `min_count` trades exist so the
    caller can skip retraining with insufficient data.

    Args:
        conn: Open sqlite3 connection.
        mode: "paper" or "live".
        days: Look-back window in calendar days (default 90).
        min_count: Minimum trades required; returns [] if below threshold.

    Returns:
        List of dicts with keys: id, symbol, side, entry_price, exit_price,
        qty_usd, realized_pnl, pnl_pct, opened_at, closed_at, exit_reason.
    """
    cutoff = time.time() - days * 86_400
    try:
        rows = conn.execute(
            """
            SELECT id, symbol, side, entry_price, exit_price,
                   qty_usd, realized_pnl, pnl_pct,
                   opened_at, closed_at, exit_reason
              FROM crypto_trades
             WHERE mode = ?
               AND closed_at >= ?
             ORDER BY closed_at ASC
            """,
            (mode, cutoff),
        ).fetchall()
    except sqlite3.Error as exc:
        logger.warning("get_recent_trades: %s", exc)
        return []

    if len(rows) < min_count:
        logger.info(
            "get_recent_trades: only %d trades in last %d days (need %d) — skipping",
            len(rows), days, min_count,
        )
        return []

    return [
        {
            "id":           row["id"],
            "symbol":       row["symbol"],
            "side":         row["side"],
            "entry_price":  float(row["entry_price"]),
            "exit_price":   float(row["exit_price"]),
            "qty_usd":      float(row["qty_usd"]),
            "realized_pnl": float(row["realized_pnl"]),
            "pnl_pct":      float(row["pnl_pct"]),
            "opened_at":    float(row["opened_at"]),
            "closed_at":    float(row["closed_at"]),
            "exit_reason":  row["exit_reason"],
        }
        for row in rows
    ]
