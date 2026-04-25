"""
core/polymarket_wallet_ranker.py — Wallet alpha ranking based on resolved history.

Evaluates tracked wallets against their 30-day resolved-market win rate.
Wallets above 65% win rate are promoted; below 55% are demoted. Wallets with
fewer than 5 resolved markets in the window are excluded from ranking changes.

Public API:
    rerank_wallets(conn, tracker) -> list[WalletRank]
    update_wallet_alpha_scores(rankings, db_path) -> None
"""

from __future__ import annotations

import contextlib
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from core.logger import logger

_WIN_RATE_PROMOTE = 0.65
_WIN_RATE_DEMOTE = 0.55
_MIN_RESOLVED = 5
_LOOKBACK_DAYS = 30
_WALLET_CACHE_DB = Path("data/wallet_cache.db")


@dataclass
class WalletRank:
    """Ranking result for a single wallet."""

    address: str
    win_rate: float
    resolved_count: int
    rank_change: str      # "promoted", "demoted", or "stable"
    alpha_score: float    # Normalised composite score (0–1)
    last_active: float    # Unix timestamp of most recent position


def _get_wallet_positions(address: str, db_path: Path, lookback_days: int) -> list[dict]:
    """Fetch resolved positions for a wallet from the cache DB."""
    cutoff = time.time() - lookback_days * 86400.0
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM wallet_positions
            WHERE address = ? AND resolved = 1 AND closed_at >= ?
            ORDER BY closed_at DESC
            """,
            (address, cutoff),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        # Table may not exist yet — treat as empty
        return []
    except Exception as exc:
        logger.warning("_get_wallet_positions(%s): %s", address, exc)
        return []


def _compute_win_rate(positions: list[dict]) -> tuple[float, float]:
    """Return (win_rate, last_active_ts) for a list of resolved position rows."""
    if not positions:
        return 0.0, 0.0
    wins = sum(1 for p in positions if p.get("pnl", 0.0) > 0)
    last_active = max((p.get("closed_at", 0.0) for p in positions), default=0.0)
    return wins / len(positions), float(last_active)


def rerank_wallets(
    _conn: sqlite3.Connection,
    tracker: object,
    db_path: Path | None = None,
) -> list[WalletRank]:
    """Rank all tracked wallets by their 30-day resolved win rate.

    Wallets with fewer than _MIN_RESOLVED resolved markets in the lookback
    window are excluded from the result list.

    Args:
        conn: Open ledger connection (not used directly but kept for interface
              consistency with the main loop).
        tracker: polymarket_wallet_tracker instance — provides .watchlist
                 attribute (list of wallet addresses).
        db_path: Path to wallet_cache.db. Defaults to _WALLET_CACHE_DB.

    Returns:
        List of WalletRank objects sorted by alpha_score descending.
    """
    cache_db = db_path or _WALLET_CACHE_DB

    watchlist: list[str] = []
    with contextlib.suppress(AttributeError):
        watchlist = list(tracker.watchlist)  # type: ignore[union-attr]

    if not watchlist:
        logger.info("rerank_wallets: empty watchlist")
        return []

    rankings: list[WalletRank] = []

    for address in watchlist:
        positions = _get_wallet_positions(address, cache_db, _LOOKBACK_DAYS)
        if len(positions) < _MIN_RESOLVED:
            logger.debug("rerank_wallets: %s has only %d resolved — skipping", address, len(positions))
            continue

        win_rate, last_active = _compute_win_rate(positions)

        if win_rate >= _WIN_RATE_PROMOTE:
            rank_change = "promoted"
        elif win_rate < _WIN_RATE_DEMOTE:
            rank_change = "demoted"
        else:
            rank_change = "stable"

        # Alpha score: win_rate weighted by recency (decays over 30 days)
        recency_factor = max(0.0, 1.0 - (time.time() - last_active) / (_LOOKBACK_DAYS * 86400.0))
        alpha_score = win_rate * (0.7 + 0.3 * recency_factor)

        rankings.append(WalletRank(
            address=address,
            win_rate=round(win_rate, 4),
            resolved_count=len(positions),
            rank_change=rank_change,
            alpha_score=round(alpha_score, 4),
            last_active=last_active,
        ))

    rankings.sort(key=lambda r: r.alpha_score, reverse=True)

    promotions = sum(1 for r in rankings if r.rank_change == "promoted")
    demotions = sum(1 for r in rankings if r.rank_change == "demoted")
    logger.info(
        "rerank_wallets: %d ranked, %d promoted, %d demoted",
        len(rankings), promotions, demotions,
    )

    return rankings


def update_wallet_alpha_scores(
    rankings: list[WalletRank],
    db_path: Path | None = None,
) -> None:
    """Update alpha_score column in wallet_cache.db for each ranked wallet.

    Args:
        rankings: Output from rerank_wallets.
        db_path: Path to wallet_cache.db. Defaults to _WALLET_CACHE_DB.
    """
    cache_db = db_path or _WALLET_CACHE_DB
    if not cache_db.exists():
        logger.warning("update_wallet_alpha_scores: cache db not found at %s", cache_db)
        return

    try:
        conn = sqlite3.connect(str(cache_db))
        for rank in rankings:
            try:
                conn.execute(
                    "UPDATE wallet_scores SET alpha_score = ? WHERE address = ?",
                    (rank.alpha_score, rank.address),
                )
                if conn.execute("SELECT changes()").fetchone()[0] == 0:
                    conn.execute(
                        "INSERT OR REPLACE INTO wallet_scores (address, alpha_score) VALUES (?, ?)",
                        (rank.address, rank.alpha_score),
                    )
            except sqlite3.OperationalError:
                # Table may not exist yet — create it
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS wallet_scores "
                    "(address TEXT PRIMARY KEY, alpha_score REAL NOT NULL DEFAULT 0.0)"
                )
                conn.execute(
                    "INSERT OR REPLACE INTO wallet_scores (address, alpha_score) VALUES (?, ?)",
                    (rank.address, rank.alpha_score),
                )

            change = "promoted" if rank.rank_change == "promoted" else (
                "demoted" if rank.rank_change == "demoted" else None
            )
            if change:
                logger.info(
                    "update_wallet_alpha_scores: %s %s (alpha_score=%.3f, win_rate=%.1f%%)",
                    rank.address[:10] + "...",
                    change,
                    rank.alpha_score,
                    rank.win_rate * 100,
                )

        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error("update_wallet_alpha_scores: %s", exc)
