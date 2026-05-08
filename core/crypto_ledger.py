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

CREATE TABLE IF NOT EXISTS crypto_signal_log (
    -- Identity
    event_id              TEXT PRIMARY KEY,
    timestamp             REAL NOT NULL,
    symbol                TEXT NOT NULL,
    mode                  TEXT NOT NULL DEFAULT 'paper',

    -- Regime
    regime_raw            TEXT NOT NULL DEFAULT 'unknown',
    regime_confirmed      TEXT NOT NULL DEFAULT 'unknown',
    regime_persistence    INTEGER NOT NULL DEFAULT 0,

    -- Technical component scores (signed, -1..1)
    tech_signed           REAL NOT NULL DEFAULT 0.0,
    rsi_score             REAL NOT NULL DEFAULT 0.0,
    macd_score            REAL NOT NULL DEFAULT 0.0,
    vwap_score            REAL NOT NULL DEFAULT 0.0,
    volume_score          REAL NOT NULL DEFAULT 0.0,
    news_score            REAL NOT NULL DEFAULT 0.0,
    onchain_score         REAL NOT NULL DEFAULT 0.0,

    -- BTC context
    btc_strength          REAL NOT NULL DEFAULT 0.0,
    btc_modifier          REAL NOT NULL DEFAULT 1.0,

    -- Composite
    combined_before_btc   REAL NOT NULL DEFAULT 0.0,
    combined_after_btc    REAL NOT NULL DEFAULT 0.0,
    threshold             REAL NOT NULL DEFAULT 0.63,
    threshold_reason      TEXT NOT NULL DEFAULT 'normal',

    -- HTF
    htf_trend             TEXT NOT NULL DEFAULT 'neutral',
    htf_alignment         INTEGER NOT NULL DEFAULT 0,  -- 1=aligned, 0=neutral, -1=filtered

    -- Decision
    direction             TEXT NOT NULL DEFAULT 'flat',
    confidence            REAL NOT NULL DEFAULT 0.0,
    would_enter           INTEGER NOT NULL DEFAULT 0,
    skip_reason           TEXT,

    -- Risk
    regime_size_mult      REAL NOT NULL DEFAULT 1.0,
    kelly_fraction        REAL NOT NULL DEFAULT 0.0,
    position_size_usd     REAL NOT NULL DEFAULT 0.0,
    entry_price           REAL NOT NULL DEFAULT 0.0,
    stop_loss             REAL NOT NULL DEFAULT 0.0,
    take_profit           REAL NOT NULL DEFAULT 0.0,

    -- Ranging mean-reversion flag
    ranging_mean_reversion INTEGER NOT NULL DEFAULT 0,

    -- Taker buy/sell upgrade fields
    taker_score            REAL NOT NULL DEFAULT 0.0,
    oi_breakout_confirmed  INTEGER NOT NULL DEFAULT 0,
    breakout_bonus         REAL NOT NULL DEFAULT 0.0,

    -- Raw market-structure values (immutable — scores/weights may change, raws never do)
    raw_funding_rate       REAL NOT NULL DEFAULT 0.0,
    raw_oi_delta_pct       REAL NOT NULL DEFAULT 0.0,
    raw_taker_ratio        REAL NOT NULL DEFAULT 0.5,
    raw_ls_ratio           REAL NOT NULL DEFAULT 1.0
);

CREATE INDEX IF NOT EXISTS idx_csl_timestamp        ON crypto_signal_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_csl_symbol_ts        ON crypto_signal_log(symbol, timestamp);
CREATE INDEX IF NOT EXISTS idx_csl_regime_ts        ON crypto_signal_log(regime_confirmed, timestamp);
CREATE INDEX IF NOT EXISTS idx_csl_decision_ts      ON crypto_signal_log(direction, timestamp);
CREATE INDEX IF NOT EXISTS idx_csl_would_enter_ts   ON crypto_signal_log(would_enter, timestamp);
CREATE INDEX IF NOT EXISTS idx_csl_btc_strength     ON crypto_signal_log(btc_strength);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply incremental migrations to existing databases."""
    try:
        conn.execute("ALTER TABLE crypto_orders ADD COLUMN binance_order_id TEXT")
        conn.commit()
        logger.info("crypto_ledger: migrated — added crypto_orders.binance_order_id")
    except sqlite3.OperationalError:
        pass

    # Taker upgrade + raw field columns — safe no-op if already present.
    for _col, _ddl in (
        ("taker_score",           "ALTER TABLE crypto_signal_log ADD COLUMN taker_score REAL NOT NULL DEFAULT 0.0"),
        ("oi_breakout_confirmed", "ALTER TABLE crypto_signal_log ADD COLUMN oi_breakout_confirmed INTEGER NOT NULL DEFAULT 0"),
        ("breakout_bonus",        "ALTER TABLE crypto_signal_log ADD COLUMN breakout_bonus REAL NOT NULL DEFAULT 0.0"),
        ("raw_funding_rate",      "ALTER TABLE crypto_signal_log ADD COLUMN raw_funding_rate REAL NOT NULL DEFAULT 0.0"),
        ("raw_oi_delta_pct",      "ALTER TABLE crypto_signal_log ADD COLUMN raw_oi_delta_pct REAL NOT NULL DEFAULT 0.0"),
        ("raw_taker_ratio",       "ALTER TABLE crypto_signal_log ADD COLUMN raw_taker_ratio REAL NOT NULL DEFAULT 0.5"),
        ("raw_ls_ratio",          "ALTER TABLE crypto_signal_log ADD COLUMN raw_ls_ratio REAL NOT NULL DEFAULT 1.0"),
    ):
        try:
            conn.execute(_ddl)
            conn.commit()
            logger.info("crypto_ledger: migrated — added crypto_signal_log.%s", _col)
        except sqlite3.OperationalError:
            pass

    # crypto_signal_log was added in v2 — safe no-op if already exists.
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS crypto_signal_log (
                event_id TEXT PRIMARY KEY, timestamp REAL NOT NULL,
                symbol TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'paper',
                regime_raw TEXT NOT NULL DEFAULT 'unknown',
                regime_confirmed TEXT NOT NULL DEFAULT 'unknown',
                regime_persistence INTEGER NOT NULL DEFAULT 0,
                tech_signed REAL NOT NULL DEFAULT 0.0,
                rsi_score REAL NOT NULL DEFAULT 0.0,
                macd_score REAL NOT NULL DEFAULT 0.0,
                vwap_score REAL NOT NULL DEFAULT 0.0,
                volume_score REAL NOT NULL DEFAULT 0.0,
                news_score REAL NOT NULL DEFAULT 0.0,
                onchain_score REAL NOT NULL DEFAULT 0.0,
                btc_strength REAL NOT NULL DEFAULT 0.0,
                btc_modifier REAL NOT NULL DEFAULT 1.0,
                combined_before_btc REAL NOT NULL DEFAULT 0.0,
                combined_after_btc REAL NOT NULL DEFAULT 0.0,
                threshold REAL NOT NULL DEFAULT 0.63,
                threshold_reason TEXT NOT NULL DEFAULT 'normal',
                htf_trend TEXT NOT NULL DEFAULT 'neutral',
                htf_alignment INTEGER NOT NULL DEFAULT 0,
                direction TEXT NOT NULL DEFAULT 'flat',
                confidence REAL NOT NULL DEFAULT 0.0,
                would_enter INTEGER NOT NULL DEFAULT 0,
                skip_reason TEXT,
                regime_size_mult REAL NOT NULL DEFAULT 1.0,
                kelly_fraction REAL NOT NULL DEFAULT 0.0,
                position_size_usd REAL NOT NULL DEFAULT 0.0,
                entry_price REAL NOT NULL DEFAULT 0.0,
                stop_loss REAL NOT NULL DEFAULT 0.0,
                take_profit REAL NOT NULL DEFAULT 0.0,
                ranging_mean_reversion INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_csl_timestamp      ON crypto_signal_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_csl_symbol_ts      ON crypto_signal_log(symbol, timestamp);
            CREATE INDEX IF NOT EXISTS idx_csl_regime_ts      ON crypto_signal_log(regime_confirmed, timestamp);
            CREATE INDEX IF NOT EXISTS idx_csl_decision_ts    ON crypto_signal_log(direction, timestamp);
            CREATE INDEX IF NOT EXISTS idx_csl_would_enter_ts ON crypto_signal_log(would_enter, timestamp);
            CREATE INDEX IF NOT EXISTS idx_csl_btc_strength   ON crypto_signal_log(btc_strength);
        """)
        conn.commit()
    except sqlite3.OperationalError as exc:
        logger.debug("crypto_ledger: signal_log migration: %s", exc)


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


def get_symbol_win_rate(
    conn: sqlite3.Connection,
    symbol: str,
    mode: str,
    window: int = 10,
) -> float | None:
    """Return the win rate for a symbol over the last `window` closed trades.

    Used by the trading loop to skip symbols that are performing poorly —
    symbols with a win rate below the caller's threshold are candidates for
    temporary exclusion.

    Args:
        conn: Open sqlite3 connection.
        symbol: Trading pair (e.g. "BTCUSDT").
        mode: "paper" or "live".
        window: Number of most-recent trades to sample (default 10).

    Returns:
        Win rate in [0.0, 1.0], or None when fewer than `window` trades exist
        (insufficient history to make a reliable judgement).
    """
    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) AS wins
            FROM (
                SELECT realized_pnl
                  FROM crypto_trades
                 WHERE mode    = ?
                   AND symbol  = ?
                 ORDER BY closed_at DESC
                 LIMIT ?
            )
            """,
            (mode, symbol, window),
        ).fetchone()
    except sqlite3.Error as exc:
        logger.warning("get_symbol_win_rate(%s): %s", symbol, exc)
        return None

    total = int(row["total"]) if row and row["total"] else 0
    # Require at least 75% of the window before the gate can fire.
    # With window=20: needs 15 trades — avoids banning on small samples.
    min_required = max(5, int(window * 0.75))
    if total < min_required:
        return None

    wins = int(row["wins"]) if row and row["wins"] else 0
    return round(wins / total, 4)


# ---------------------------------------------------------------------------
# Signal decision log
# ---------------------------------------------------------------------------

def insert_signal_log(conn: sqlite3.Connection, entry: dict) -> None:
    """Persist one signal decision log row.

    Silently drops on error — observability must never crash the trading loop.

    Args:
        conn: Open sqlite3 connection.
        entry: Dict produced by the loop's _build_signal_log() helper.
    """
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO crypto_signal_log (
                event_id, timestamp, symbol, mode,
                regime_raw, regime_confirmed, regime_persistence,
                tech_signed, rsi_score, macd_score, vwap_score, volume_score,
                news_score, onchain_score,
                btc_strength, btc_modifier,
                combined_before_btc, combined_after_btc,
                threshold, threshold_reason,
                htf_trend, htf_alignment,
                direction, confidence, would_enter, skip_reason,
                regime_size_mult, kelly_fraction, position_size_usd,
                entry_price, stop_loss, take_profit,
                ranging_mean_reversion,
                taker_score, oi_breakout_confirmed, breakout_bonus,
                raw_funding_rate, raw_oi_delta_pct, raw_taker_ratio, raw_ls_ratio
            ) VALUES (
                :event_id, :timestamp, :symbol, :mode,
                :regime_raw, :regime_confirmed, :regime_persistence,
                :tech_signed, :rsi_score, :macd_score, :vwap_score, :volume_score,
                :news_score, :onchain_score,
                :btc_strength, :btc_modifier,
                :combined_before_btc, :combined_after_btc,
                :threshold, :threshold_reason,
                :htf_trend, :htf_alignment,
                :direction, :confidence, :would_enter, :skip_reason,
                :regime_size_mult, :kelly_fraction, :position_size_usd,
                :entry_price, :stop_loss, :take_profit,
                :ranging_mean_reversion,
                :taker_score, :oi_breakout_confirmed, :breakout_bonus,
                :raw_funding_rate, :raw_oi_delta_pct, :raw_taker_ratio, :raw_ls_ratio
            )
            """,
            entry,
        )
        conn.commit()
    except sqlite3.Error as exc:
        logger.warning("insert_signal_log: %s", exc)


# ---------------------------------------------------------------------------
# Analytics queries
# ---------------------------------------------------------------------------

def analytics_regimes(
    conn: sqlite3.Connection,
    mode: str = "paper",
    days: int = 30,
) -> list[dict]:
    """Win rate and PnL breakdown by confirmed regime.

    Joins signal_log decisions with closed trades to compute per-regime stats.
    Trades are matched to signal decisions on (symbol, mode) within ±5 minutes.
    """
    cutoff = time.time() - days * 86_400
    try:
        rows = conn.execute(
            """
            WITH decided AS (
                SELECT regime_confirmed, direction, would_enter,
                       entry_price, symbol, timestamp AS sig_ts
                  FROM crypto_signal_log
                 WHERE mode = ? AND timestamp >= ?
                   AND would_enter = 1
            ),
            matched AS (
                SELECT d.regime_confirmed,
                       t.realized_pnl,
                       CASE WHEN t.realized_pnl > 0 THEN 1 ELSE 0 END AS win
                  FROM decided d
                  JOIN crypto_trades t
                    ON t.symbol = d.symbol
                   AND t.mode   = ?
                   AND t.opened_at BETWEEN d.sig_ts - 300 AND d.sig_ts + 300
            )
            SELECT
                regime_confirmed                     AS regime,
                COUNT(*)                             AS signals,
                SUM(would_enter)                     AS entries,
                0                                   AS trades,
                0.0                                 AS winrate,
                0.0                                 AS avg_pnl
            FROM crypto_signal_log
            WHERE mode = ? AND timestamp >= ?
            GROUP BY regime_confirmed
            """,
            (mode, cutoff, mode, mode, cutoff),
        ).fetchall()
        # Separate query for trade outcomes joined by timing
        trade_rows = conn.execute(
            """
            SELECT
                sl.regime_confirmed                  AS regime,
                COUNT(t.id)                          AS trades,
                COALESCE(AVG(CASE WHEN t.realized_pnl > 0 THEN 1.0 ELSE 0.0 END), 0) AS winrate,
                COALESCE(AVG(t.realized_pnl), 0)     AS avg_pnl,
                COALESCE(SUM(t.realized_pnl), 0)     AS total_pnl
              FROM crypto_signal_log sl
              JOIN crypto_trades t
                ON t.symbol   = sl.symbol
               AND t.mode     = sl.mode
               AND t.opened_at BETWEEN sl.timestamp - 300 AND sl.timestamp + 300
             WHERE sl.mode = ? AND sl.timestamp >= ? AND sl.would_enter = 1
             GROUP BY sl.regime_confirmed
            """,
            (mode, cutoff),
        ).fetchall()

        trade_by_regime: dict[str, dict] = {
            r["regime"]: {
                "trades": int(r["trades"]),
                "winrate": round(float(r["winrate"]), 4),
                "avg_pnl": round(float(r["avg_pnl"]), 4),
                "total_pnl": round(float(r["total_pnl"]), 4),
            }
            for r in trade_rows
        }

        result = []
        for row in rows:
            regime = row["regime"]
            td = trade_by_regime.get(regime, {"trades": 0, "winrate": 0.0, "avg_pnl": 0.0, "total_pnl": 0.0})
            result.append({
                "regime": regime,
                "signals": int(row["signals"]),
                "entries": int(row["entries"]),
                **td,
            })
        return result
    except sqlite3.Error as exc:
        logger.warning("analytics_regimes: %s", exc)
        return []


def analytics_btc(
    conn: sqlite3.Connection,
    mode: str = "paper",
    days: int = 30,
) -> list[dict]:
    """Signal and trade distribution bucketed by btc_strength."""
    cutoff = time.time() - days * 86_400
    try:
        rows = conn.execute(
            """
            SELECT
                CASE
                    WHEN btc_strength <= -0.6 THEN 'very_bearish'
                    WHEN btc_strength <= -0.2 THEN 'bearish'
                    WHEN btc_strength <   0.2 THEN 'neutral'
                    WHEN btc_strength <   0.6 THEN 'bullish'
                    ELSE 'very_bullish'
                END                             AS bucket,
                COUNT(*)                        AS signals,
                SUM(would_enter)                AS entries,
                AVG(btc_modifier)               AS avg_modifier,
                AVG(combined_after_btc)         AS avg_combined,
                AVG(combined_before_btc)        AS avg_combined_pre
              FROM crypto_signal_log
             WHERE mode = ? AND timestamp >= ?
             GROUP BY bucket
             ORDER BY MIN(btc_strength)
            """,
            (mode, cutoff),
        ).fetchall()
        return [
            {
                "bucket": r["bucket"],
                "signals": int(r["signals"]),
                "entries": int(r["entries"]),
                "avg_modifier": round(float(r["avg_modifier"]), 4),
                "avg_combined": round(float(r["avg_combined"]), 4),
                "avg_combined_pre": round(float(r["avg_combined_pre"]), 4),
            }
            for r in rows
        ]
    except sqlite3.Error as exc:
        logger.warning("analytics_btc: %s", exc)
        return []


def analytics_signals(
    conn: sqlite3.Connection,
    mode: str = "paper",
    days: int = 30,
) -> list[dict]:
    """Combined score distribution and threshold calibration by bucket."""
    cutoff = time.time() - days * 86_400
    try:
        rows = conn.execute(
            """
            SELECT
                ROUND(combined_after_btc * 20) / 20  AS bucket_center,
                COUNT(*)                              AS count,
                SUM(would_enter)                      AS entries,
                AVG(confidence)                       AS avg_confidence,
                direction
              FROM crypto_signal_log
             WHERE mode = ? AND timestamp >= ?
               AND direction != 'flat'
             GROUP BY bucket_center, direction
             ORDER BY bucket_center
            """,
            (mode, cutoff),
        ).fetchall()
        return [
            {
                "bucket_center": round(float(r["bucket_center"]), 2),
                "direction": r["direction"],
                "count": int(r["count"]),
                "entries": int(r["entries"]),
                "avg_confidence": round(float(r["avg_confidence"]), 4),
            }
            for r in rows
        ]
    except sqlite3.Error as exc:
        logger.warning("analytics_signals: %s", exc)
        return []


def analytics_skips(
    conn: sqlite3.Connection,
    mode: str = "paper",
    days: int = 30,
) -> list[dict]:
    """Frequency and context of skip_reason values."""
    cutoff = time.time() - days * 86_400
    try:
        rows = conn.execute(
            """
            SELECT
                COALESCE(skip_reason, 'entered')        AS reason,
                COUNT(*)                                AS count,
                AVG(combined_after_btc)                 AS avg_combined,
                AVG(btc_strength)                       AS avg_btc_strength
              FROM crypto_signal_log
             WHERE mode = ? AND timestamp >= ?
             GROUP BY reason
             ORDER BY count DESC
            """,
            (mode, cutoff),
        ).fetchall()
        return [
            {
                "reason": r["reason"],
                "count": int(r["count"]),
                "avg_combined": round(float(r["avg_combined"]), 4),
                "avg_btc_strength": round(float(r["avg_btc_strength"]), 4),
            }
            for r in rows
        ]
    except sqlite3.Error as exc:
        logger.warning("analytics_skips: %s", exc)
        return []


def analytics_calibration(
    conn: sqlite3.Connection,
    mode: str = "paper",
    days: int = 30,
) -> list[dict]:
    """Confidence calibration: combined score bucket vs realised winrate."""
    cutoff = time.time() - days * 86_400
    try:
        rows = conn.execute(
            """
            SELECT
                ROUND(sl.combined_after_btc / 0.05) * 0.05  AS bucket,
                COUNT(t.id)                                   AS trades,
                COALESCE(AVG(CASE WHEN t.realized_pnl > 0 THEN 1.0 ELSE 0.0 END), 0) AS winrate,
                COALESCE(AVG(t.realized_pnl), 0)              AS avg_pnl
              FROM crypto_signal_log sl
              JOIN crypto_trades t
                ON t.symbol   = sl.symbol
               AND t.mode     = sl.mode
               AND t.opened_at BETWEEN sl.timestamp - 300 AND sl.timestamp + 300
             WHERE sl.mode = ? AND sl.timestamp >= ? AND sl.would_enter = 1
             GROUP BY bucket
             ORDER BY bucket
            """,
            (mode, cutoff),
        ).fetchall()
        return [
            {
                "combined_bucket": round(float(r["bucket"]), 2),
                "trades": int(r["trades"]),
                "winrate": round(float(r["winrate"]), 4),
                "avg_pnl": round(float(r["avg_pnl"]), 4),
            }
            for r in rows
        ]
    except sqlite3.Error as exc:
        logger.warning("analytics_calibration: %s", exc)
        return []
