"""
data/universe_registry.py — SQLite registry for the dynamic FII universe.

Table: fii_registry
    One row per ticker. Tracks B3/CVM metadata, data-source health,
    liquidity, tier classification, and last-validation timestamp.

Tier definitions:
    1 — IFIX + daily liquidity ≥ R$1M  (highest-priority, scored every cycle)
    2 — IFIX + daily liquidity ≥ R$300k, or non-IFIX + liq ≥ R$1M
    3 — Small caps / low-liquidity (future expansion)

Public API:
    connect_registry()               -> sqlite3.Connection
    upsert_fii(conn, entry)
    get_active_universe(conn, ...)   -> list[dict]
    get_sector_map_from_db(conn)     -> dict[str, str]
    get_registry_stats(conn)         -> dict
    mark_inactive(conn, ticker)
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from core.logger import logger

_REGISTRY_DB = Path("data/fii_registry.db")

_DDL = """
CREATE TABLE IF NOT EXISTS fii_registry (
    ticker            TEXT PRIMARY KEY,
    nome              TEXT NOT NULL DEFAULT '',
    setor             TEXT NOT NULL DEFAULT 'Outros',
    ifix              INTEGER NOT NULL DEFAULT 0,     -- boolean: 1=in IFIX
    tier              INTEGER NOT NULL DEFAULT 2,     -- 1/2/3
    ativo             INTEGER NOT NULL DEFAULT 1,     -- boolean: 1=active
    yahoo_ok          INTEGER NOT NULL DEFAULT 0,     -- yfinance returns valid price
    si_ok             INTEGER NOT NULL DEFAULT 0,     -- StatusInvest returns data
    last_price        REAL NOT NULL DEFAULT 0.0,
    daily_liquidity   REAL NOT NULL DEFAULT 0.0,      -- R$/day (3-month avg)
    participacao_ifix REAL NOT NULL DEFAULT 0.0,      -- % weight in IFIX index
    cnpj              TEXT NOT NULL DEFAULT '',
    administrador     TEXT NOT NULL DEFAULT '',
    last_validated    TEXT NOT NULL DEFAULT '',       -- ISO date of last refresh run
    created_at        REAL NOT NULL DEFAULT 0.0,
    updated_at        REAL NOT NULL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_reg_ifix   ON fii_registry(ifix);
CREATE INDEX IF NOT EXISTS idx_reg_tier   ON fii_registry(tier);
CREATE INDEX IF NOT EXISTS idx_reg_ativo  ON fii_registry(ativo);
CREATE INDEX IF NOT EXISTS idx_reg_liq    ON fii_registry(daily_liquidity);
"""


def connect_registry(db_path: str | Path = _REGISTRY_DB) -> sqlite3.Connection:
    """Open (and initialise) the FII registry database."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    conn.commit()
    return conn


def upsert_fii(conn: sqlite3.Connection, entry: dict) -> None:
    """Insert or update one FII entry in the registry.

    On conflict (ticker already exists): all fields except ticker and created_at
    are updated. created_at is preserved to track when the FII was first seen.
    """
    now = time.time()
    try:
        conn.execute(
            """
            INSERT INTO fii_registry (
                ticker, nome, setor, ifix, tier, ativo,
                yahoo_ok, si_ok, last_price, daily_liquidity,
                participacao_ifix, cnpj, administrador,
                last_validated, created_at, updated_at
            ) VALUES (
                :ticker, :nome, :setor, :ifix, :tier, :ativo,
                :yahoo_ok, :si_ok, :last_price, :daily_liquidity,
                :participacao_ifix, :cnpj, :administrador,
                :last_validated, :created_at, :updated_at
            )
            ON CONFLICT(ticker) DO UPDATE SET
                nome              = excluded.nome,
                setor             = excluded.setor,
                ifix              = excluded.ifix,
                tier              = excluded.tier,
                ativo             = excluded.ativo,
                yahoo_ok          = excluded.yahoo_ok,
                si_ok             = excluded.si_ok,
                last_price        = excluded.last_price,
                daily_liquidity   = excluded.daily_liquidity,
                participacao_ifix = excluded.participacao_ifix,
                cnpj              = excluded.cnpj,
                administrador     = excluded.administrador,
                last_validated    = excluded.last_validated,
                updated_at        = excluded.updated_at
            """,
            {
                "ticker":            entry["ticker"].upper(),
                "nome":              entry.get("nome", ""),
                "setor":             entry.get("setor", "Outros"),
                "ifix":              1 if entry.get("ifix") else 0,
                "tier":              int(entry.get("tier", 2)),
                "ativo":             1 if entry.get("ativo", True) else 0,
                "yahoo_ok":          1 if entry.get("yahoo_ok") else 0,
                "si_ok":             1 if entry.get("si_ok") else 0,
                "last_price":        float(entry.get("last_price", 0.0)),
                "daily_liquidity":   float(entry.get("daily_liquidity", 0.0)),
                "participacao_ifix": float(entry.get("participacao_ifix", 0.0)),
                "cnpj":              entry.get("cnpj", ""),
                "administrador":     entry.get("administrador", ""),
                "last_validated":    entry.get("last_validated", ""),
                "created_at":        entry.get("created_at", now),
                "updated_at":        now,
            },
        )
        conn.commit()
    except sqlite3.Error as exc:
        logger.warning("upsert_fii(%s): %s", entry.get("ticker"), exc)


def mark_inactive(conn: sqlite3.Connection, ticker: str) -> None:
    """Mark a ticker as inactive (delisted / no data). Preserved for history."""
    try:
        conn.execute(
            "UPDATE fii_registry SET ativo = 0, updated_at = ? WHERE ticker = ?",
            (time.time(), ticker.upper()),
        )
        conn.commit()
    except sqlite3.Error as exc:
        logger.warning("mark_inactive(%s): %s", ticker, exc)


def get_active_universe(
    conn: sqlite3.Connection,
    ifix_only: bool = True,
    min_liquidity: float = 0.0,
    max_tier: int | None = None,
    yahoo_ok_only: bool = False,
) -> list[dict]:
    """Return active FIIs matching filters, ordered by IFIX weight then liquidity.

    Args:
        ifix_only:     Only return IFIX components.
        min_liquidity: Minimum daily liquidity in R$.
        max_tier:      Return tiers ≤ this value (e.g. max_tier=2 → tiers 1 and 2).
        yahoo_ok_only: Only return FIIs with valid yfinance data.

    Returns:
        List of dicts with all registry columns.
    """
    conditions = ["ativo = 1"]
    params: list = []

    if ifix_only:
        conditions.append("ifix = 1")
    if min_liquidity > 0:
        conditions.append("daily_liquidity >= ?")
        params.append(min_liquidity)
    if max_tier is not None:
        conditions.append("tier <= ?")
        params.append(max_tier)
    if yahoo_ok_only:
        conditions.append("yahoo_ok = 1")

    where = " AND ".join(conditions)
    try:
        rows = conn.execute(
            f"SELECT * FROM fii_registry WHERE {where} "
            f"ORDER BY participacao_ifix DESC, daily_liquidity DESC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        logger.warning("get_active_universe: %s", exc)
        return []


def get_sector_map_from_db(conn: sqlite3.Connection) -> dict[str, str]:
    """Return ticker → setor for ALL FIIs in the registry (including inactive)."""
    try:
        rows = conn.execute("SELECT ticker, setor FROM fii_registry").fetchall()
        return {r["ticker"]: r["setor"] for r in rows}
    except sqlite3.Error as exc:
        logger.warning("get_sector_map_from_db: %s", exc)
        return {}


def get_registry_stats(conn: sqlite3.Connection) -> dict:
    """Return summary counts for health monitoring."""
    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*)                                              AS total,
                SUM(ativo)                                            AS ativos,
                SUM(ifix)                                             AS ifix_count,
                SUM(yahoo_ok)                                         AS yahoo_ok,
                SUM(CASE WHEN yahoo_ok = 0 AND ativo = 1 THEN 1 END) AS yahoo_broken,
                MAX(last_validated)                                   AS last_validated
            FROM fii_registry
            """
        ).fetchone()
        return dict(row) if row else {}
    except sqlite3.Error as exc:
        logger.warning("get_registry_stats: %s", exc)
        return {}
