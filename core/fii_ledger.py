"""
core/fii_ledger.py — SQLite persistence for FII daily snapshots.

Table: fii_daily_snapshot
    One row per (ticker, date). Captures raw fundamentals + computed scores
    at the time of each fii_loop iteration. Immutable historical record.

Public API:
    connect_fii_db() -> sqlite3.Connection
    save_fii_snapshot(conn, entry: dict) -> None
    get_fii_history(conn, ticker, days) -> list[dict]
    get_fii_latest_scores(conn) -> list[dict]
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core.logger import logger

_DB_PATH = Path("data/fii_snapshots.db")

_DDL = """
CREATE TABLE IF NOT EXISTS fii_daily_snapshot (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    date            TEXT NOT NULL,           -- YYYY-MM-DD

    -- Market data
    price           REAL NOT NULL DEFAULT 0.0,
    monthly_div     REAL NOT NULL DEFAULT 0.0,

    -- Fundamentals (raw — never loses value)
    dividend_yield  REAL NOT NULL DEFAULT 0.0,
    pvp             REAL NOT NULL DEFAULT 1.0,
    dividend_consistency REAL NOT NULL DEFAULT 50.0,
    debt_ratio      REAL,                    -- NULL = no data
    vacancy_rate    REAL,                    -- NULL = no data
    revenue_growth_12m  REAL NOT NULL DEFAULT 0.0,
    earnings_growth_12m REAL NOT NULL DEFAULT 0.0,
    daily_liquidity REAL NOT NULL DEFAULT 0.0,
    news_sentiment  REAL NOT NULL DEFAULT 0.0,

    -- Computed scores
    alpha_score         REAL NOT NULL DEFAULT 0.0,
    income_score        REAL NOT NULL DEFAULT 0.0,
    valuation_score     REAL NOT NULL DEFAULT 0.0,
    risk_score          REAL NOT NULL DEFAULT 50.0,
    growth_score        REAL NOT NULL DEFAULT 0.0,
    news_sentiment_score REAL NOT NULL DEFAULT 50.0,

    -- Metadata
    data_source     TEXT NOT NULL DEFAULT 'scraper',
    created_at      REAL NOT NULL,           -- unix timestamp

    UNIQUE(ticker, date)                     -- one snapshot per ticker per day
);

CREATE INDEX IF NOT EXISTS idx_fds_ticker_date ON fii_daily_snapshot(ticker, date);
CREATE INDEX IF NOT EXISTS idx_fds_date        ON fii_daily_snapshot(date);
CREATE INDEX IF NOT EXISTS idx_fds_score       ON fii_daily_snapshot(alpha_score, date);
"""


def connect_fii_db(db_path: str | Path = _DB_PATH) -> sqlite3.Connection:
    """Open (and initialise) the FII snapshot database."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    conn.commit()
    return conn


def save_fii_snapshot(conn: sqlite3.Connection, entry: dict) -> None:
    """Insert or replace one FII snapshot row.

    Uses INSERT OR REPLACE so re-running the loop on the same day
    updates the row with fresh data instead of failing.

    Args:
        conn: Open connection from connect_fii_db().
        entry: Dict with keys matching table columns. Missing keys default to 0/NULL.
    """
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO fii_daily_snapshot (
                ticker, date, price, monthly_div,
                dividend_yield, pvp, dividend_consistency,
                debt_ratio, vacancy_rate,
                revenue_growth_12m, earnings_growth_12m,
                daily_liquidity, news_sentiment,
                alpha_score, income_score, valuation_score,
                risk_score, growth_score, news_sentiment_score,
                data_source, created_at
            ) VALUES (
                :ticker, :date, :price, :monthly_div,
                :dividend_yield, :pvp, :dividend_consistency,
                :debt_ratio, :vacancy_rate,
                :revenue_growth_12m, :earnings_growth_12m,
                :daily_liquidity, :news_sentiment,
                :alpha_score, :income_score, :valuation_score,
                :risk_score, :growth_score, :news_sentiment_score,
                :data_source, :created_at
            )
            """,
            entry,
        )
        conn.commit()
    except sqlite3.Error as exc:
        logger.warning("save_fii_snapshot(%s): %s", entry.get("ticker"), exc)


def get_fii_history(
    conn: sqlite3.Connection,
    ticker: str,
    days: int = 90,
) -> list[dict]:
    """Return daily snapshots for one ticker, newest first."""
    try:
        rows = conn.execute(
            """
            SELECT * FROM fii_daily_snapshot
            WHERE ticker = ?
            ORDER BY date DESC
            LIMIT ?
            """,
            (ticker.upper(), days),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        logger.warning("get_fii_history(%s): %s", ticker, exc)
        return []


def get_fii_latest_scores(conn: sqlite3.Connection) -> list[dict]:
    """Return the most recent snapshot per ticker, ordered by alpha_score desc."""
    try:
        rows = conn.execute(
            """
            SELECT s.*
            FROM fii_daily_snapshot s
            INNER JOIN (
                SELECT ticker, MAX(date) AS max_date
                FROM fii_daily_snapshot
                GROUP BY ticker
            ) latest ON s.ticker = latest.ticker AND s.date = latest.max_date
            ORDER BY s.alpha_score DESC
            """,
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        logger.warning("get_fii_latest_scores: %s", exc)
        return []


def get_fii_score_delta(
    conn: sqlite3.Connection,
    ticker: str,
    days: int = 30,
) -> float | None:
    """Return score change over last `days` days (latest - oldest in window).

    Returns None when insufficient history.
    """
    history = get_fii_history(conn, ticker, days)
    if len(history) < 2:
        return None
    return round(history[0]["alpha_score"] - history[-1]["alpha_score"], 2)
