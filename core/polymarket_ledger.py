"""
core/polymarket_ledger.py — SQLite WAL ledger for Polymarket trades.

Tables:
    pm_markets          — cached market metadata
    pm_orders           — every order intent, keyed by client_order_id
    pm_positions        — open positions
    pm_trades           — closed trades with realized PnL
    pm_pnl_snapshots    — daily equity snapshots for drawdown tracking
    pm_calibration      — per-market forecast vs outcome records
    pm_weight_history   — history of weight tuning cycles

Public API:
    init_db(db_path) -> sqlite3.Connection
    insert_order_if_new(conn, client_order_id, condition_id, token_id,
                        direction, size_usd, limit_price, mode) -> bool
    reconcile_pending_orders(conn, client) -> int
    insert_calibration_record(conn, condition_id, entry_prob, ai_estimate,
                              resolved_yes, category, edge_at_entry) -> bool
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from core.logger import logger

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS pm_markets (
    condition_id        TEXT PRIMARY KEY,
    token_id            TEXT NOT NULL,
    question            TEXT NOT NULL,
    end_date_iso        TEXT NOT NULL DEFAULT '',
    volume_24h          REAL NOT NULL DEFAULT 0.0,
    spread_pct          REAL NOT NULL DEFAULT 0.0,
    days_to_resolution  REAL NOT NULL DEFAULT 0.0,
    yes_price           REAL NOT NULL DEFAULT 0.5,
    category            TEXT NOT NULL DEFAULT '',
    is_active           INTEGER NOT NULL DEFAULT 1,
    cached_at           REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pm_orders (
    client_order_id TEXT PRIMARY KEY,
    condition_id    TEXT NOT NULL,
    token_id        TEXT NOT NULL,
    direction       TEXT NOT NULL CHECK (direction IN ('yes', 'no')),
    size_usd        REAL NOT NULL,
    limit_price     REAL NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'filled', 'cancelled', 'rejected')),
    fill_price      REAL,
    mode            TEXT NOT NULL CHECK (mode IN ('paper', 'live')),
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pm_orders_status ON pm_orders(status);
CREATE INDEX IF NOT EXISTS idx_pm_orders_condition ON pm_orders(condition_id);

CREATE TABLE IF NOT EXISTS pm_positions (
    position_id     TEXT PRIMARY KEY,
    condition_id    TEXT NOT NULL,
    token_id        TEXT NOT NULL,
    direction       TEXT NOT NULL,
    size_usd        REAL NOT NULL,
    entry_price     REAL NOT NULL,
    current_price   REAL NOT NULL DEFAULT 0.5,
    unrealized_pnl  REAL NOT NULL DEFAULT 0.0,
    mode            TEXT NOT NULL,
    opened_at       REAL NOT NULL,
    updated_at      REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pm_positions_condition ON pm_positions(condition_id);

CREATE TABLE IF NOT EXISTS pm_trades (
    trade_id        TEXT PRIMARY KEY,
    condition_id    TEXT NOT NULL,
    direction       TEXT NOT NULL,
    size_usd        REAL NOT NULL,
    entry_price     REAL NOT NULL,
    exit_price      REAL NOT NULL,
    realized_pnl    REAL NOT NULL,
    mode            TEXT NOT NULL,
    opened_at       REAL NOT NULL,
    closed_at       REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pm_trades_condition ON pm_trades(condition_id);
CREATE INDEX IF NOT EXISTS idx_pm_trades_closed ON pm_trades(closed_at);

CREATE TABLE IF NOT EXISTS pm_pnl_snapshots (
    snapshot_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date   TEXT NOT NULL,
    equity_usd      REAL NOT NULL,
    open_positions  INTEGER NOT NULL DEFAULT 0,
    daily_pnl       REAL NOT NULL DEFAULT 0.0,
    mode            TEXT NOT NULL,
    created_at      REAL NOT NULL,
    UNIQUE (snapshot_date, mode)
);

CREATE TABLE IF NOT EXISTS pm_calibration (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_id    TEXT NOT NULL UNIQUE,
    entry_prob      REAL NOT NULL,
    ai_estimate     REAL,
    resolved_yes    INTEGER NOT NULL CHECK (resolved_yes IN (0, 1)),
    category        TEXT NOT NULL DEFAULT '',
    edge_at_entry   REAL NOT NULL DEFAULT 0.0,
    created_at      REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pm_calibration_category ON pm_calibration(category);
CREATE INDEX IF NOT EXISTS idx_pm_calibration_created ON pm_calibration(created_at);

CREATE TABLE IF NOT EXISTS pm_weight_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tuned_at        REAL NOT NULL,
    trigger_markets INTEGER NOT NULL DEFAULT 0,
    weights_before  TEXT NOT NULL,
    weights_after   TEXT NOT NULL,
    brier_score     REAL NOT NULL DEFAULT 0.0,
    win_rate        REAL NOT NULL DEFAULT 0.0
);
"""


def init_db(db_path: str = "data/polymarket_ledger.db") -> sqlite3.Connection:
    """Open (or create) the Polymarket ledger SQLite database.

    Applies WAL mode and creates all tables if they do not already exist.

    Args:
        db_path: Path to the SQLite file. Created (with parent dirs) if absent.

    Returns:
        An open sqlite3.Connection with WAL mode and row_factory set to
        sqlite3.Row for dict-style access.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    conn.commit()
    logger.info("polymarket_ledger: db ready at %s", path)
    return conn


def insert_order_if_new(
    conn: sqlite3.Connection,
    client_order_id: str,
    condition_id: str,
    token_id: str,
    direction: str,
    size_usd: float,
    limit_price: float,
    mode: str = "paper",
) -> bool:
    """Insert a new order record if the client_order_id has not been seen before.

    Idempotent: calling this twice with the same client_order_id is safe.

    Args:
        conn: Open ledger connection (from init_db).
        client_order_id: Unique order identifier (UUID or exchange-assigned).
        condition_id: Polymarket condition ID.
        token_id: YES token ID.
        direction: "yes" or "no".
        size_usd: Position size in USDC.
        limit_price: Limit price in [0, 1].
        mode: "paper" or "live".

    Returns:
        True if a new row was inserted, False if already present.
    """
    now = time.time()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO pm_orders
                (client_order_id, condition_id, token_id, direction,
                 size_usd, limit_price, status, mode, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (client_order_id, condition_id, token_id, direction,
             size_usd, limit_price, mode, now, now),
        )
        conn.commit()
        inserted = conn.execute(
            "SELECT changes() AS c"
        ).fetchone()["c"]
        return bool(inserted)
    except sqlite3.Error as exc:
        logger.error("insert_order_if_new failed: %s", exc)
        return False


def reconcile_pending_orders(conn: sqlite3.Connection, client: object) -> int:
    """Check all pending orders against the exchange and update their status.

    For each order with status='pending', queries the exchange (or paper engine)
    for the current fill status and updates the ledger accordingly.

    Args:
        conn: Open ledger connection.
        client: A py-clob-client ClobClient instance (or None in paper mode).
                In paper mode, all pending orders are auto-filled at limit_price.

    Returns:
        Number of orders whose status was updated.
    """
    rows = conn.execute(
        "SELECT * FROM pm_orders WHERE status = 'pending'"
    ).fetchall()

    if not rows:
        return 0

    updated = 0
    now = time.time()

    for row in rows:
        oid = row["client_order_id"]
        mode = row["mode"]
        new_status: str | None = None
        fill_price: float | None = None

        if mode == "paper":
            new_status = "filled"
            fill_price = float(row["limit_price"])

        elif client is not None:
            try:
                order_info = client.get_order(oid)  # type: ignore[union-attr]
                status_raw = (order_info.get("status") or "").lower()
                if status_raw in ("filled", "matched"):
                    new_status = "filled"
                    fill_price = float(order_info.get("avgPrice") or row["limit_price"])
                elif status_raw in ("cancelled", "canceled"):
                    new_status = "cancelled"
                elif status_raw == "rejected":
                    new_status = "rejected"
            except Exception as exc:
                logger.warning("reconcile: get_order(%s) failed: %s", oid, exc)
                continue

        if new_status is not None:
            conn.execute(
                """
                UPDATE pm_orders
                SET status = ?, fill_price = ?, updated_at = ?
                WHERE client_order_id = ?
                """,
                (new_status, fill_price, now, oid),
            )
            updated += 1

    if updated:
        conn.commit()
        logger.info("reconcile_pending_orders: updated %d orders", updated)

    return updated


def insert_calibration_record(
    conn: sqlite3.Connection,
    condition_id: str,
    entry_prob: float,
    ai_estimate: float | None,
    resolved_yes: bool,
    category: str = "",
    edge_at_entry: float = 0.0,
) -> bool:
    """Insert a calibration record for a resolved market.

    Idempotent: a second call with the same condition_id is silently ignored
    (INSERT OR IGNORE semantics).

    Args:
        conn: Open ledger connection.
        condition_id: Polymarket condition ID.
        entry_prob: Market YES price at trade entry.
        ai_estimate: AI-estimated fair probability, or None if unavailable.
        resolved_yes: True if the market resolved YES.
        category: Market category label.
        edge_at_entry: Absolute edge (|ai_estimate - entry_prob|) at entry.

    Returns:
        True if a new row was inserted, False if already present.
    """
    now = time.time()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO pm_calibration
                (condition_id, entry_prob, ai_estimate, resolved_yes,
                 category, edge_at_entry, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (condition_id, entry_prob, ai_estimate,
             1 if resolved_yes else 0, category, edge_at_entry, now),
        )
        conn.commit()
        inserted = conn.execute("SELECT changes() AS c").fetchone()["c"]
        return bool(inserted)
    except sqlite3.Error as exc:
        logger.error("insert_calibration_record failed: %s", exc)
        return False
