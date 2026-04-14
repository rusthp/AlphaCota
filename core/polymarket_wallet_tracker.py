"""
core/polymarket_wallet_tracker.py — Fetch and cache Polymarket wallet position history.

Uses gamma-api public endpoints (no auth required):
  GET /positions?user=<addr>&closed=true  — resolved positions for a wallet

Cache: data/wallet_cache.db (SQLite WAL), 1h TTL per address.

Usage:
    from core.polymarket_wallet_tracker import get_wallet_history, WalletHistory

    history = get_wallet_history("0xabc...")
    print(history.win_rate, history.total_trades)
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

_GAMMA_API = "https://gamma-api.polymarket.com"
_CACHE_DB = Path("data/wallet_cache.db")
_CACHE_TTL = 3600  # 1 hour in seconds
_REQUEST_TIMEOUT = 15
_HEADERS = {"User-Agent": "AlphaCota/1.0 Polymarket-Tracker", "Accept": "application/json"}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class WalletHistory:
    address: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float  # 0.0 – 1.0
    avg_size_usd: float
    preferred_categories: list[str] = field(default_factory=list)
    last_active_ts: float = 0.0  # unix timestamp of most recent resolved position
    fetched_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Cache — SQLite WAL
# ---------------------------------------------------------------------------


def _get_cache_conn() -> sqlite3.Connection:
    _CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_CACHE_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wallet_history_cache (
            address     TEXT PRIMARY KEY,
            data        TEXT NOT NULL,
            fetched_at  REAL NOT NULL,
            alpha_score REAL NOT NULL DEFAULT 0.0
        )
    """)
    conn.commit()
    return conn


def load_cached_history(address: str) -> WalletHistory | None:
    """Return cached WalletHistory if within TTL, else None."""
    try:
        conn = _get_cache_conn()
        row = conn.execute(
            "SELECT data, fetched_at FROM wallet_history_cache WHERE address = ?",
            (address.lower(),),
        ).fetchone()
        conn.close()
        if row is None:
            return None
        fetched_at = row[1]
        if time.time() - fetched_at > _CACHE_TTL:
            return None
        d = json.loads(row[0])
        return WalletHistory(**d)
    except Exception:
        return None


def save_history(address: str, history: WalletHistory) -> None:
    """Upsert WalletHistory into cache."""
    try:
        conn = _get_cache_conn()
        data = json.dumps({
            "address": history.address,
            "total_trades": history.total_trades,
            "wins": history.wins,
            "losses": history.losses,
            "win_rate": history.win_rate,
            "avg_size_usd": history.avg_size_usd,
            "preferred_categories": history.preferred_categories,
            "last_active_ts": history.last_active_ts,
            "fetched_at": history.fetched_at,
        })
        conn.execute(
            """
            INSERT INTO wallet_history_cache (address, data, fetched_at)
            VALUES (?, ?, ?)
            ON CONFLICT(address) DO UPDATE SET data=excluded.data, fetched_at=excluded.fetched_at
            """,
            (address.lower(), data, history.fetched_at),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Gamma-API fetcher
# ---------------------------------------------------------------------------


def _fetch_positions(address: str) -> list[dict]:
    """Fetch all resolved positions for an address from gamma-api."""
    results: list[dict] = []
    offset = 0
    limit = 100
    while True:
        try:
            resp = requests.get(
                f"{_GAMMA_API}/positions",
                params={
                    "user": address,
                    "closed": "true",
                    "limit": limit,
                    "offset": offset,
                },
                headers=_HEADERS,
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            positions = data if isinstance(data, list) else data.get("positions", [])
            if not positions:
                break
            results.extend(positions)
            if len(positions) < limit:
                break
            offset += limit
        except Exception:
            break
    return results


def _parse_history(address: str, positions: list[dict]) -> WalletHistory:
    """Convert raw position list into WalletHistory."""
    wins = 0
    losses = 0
    total_size = 0.0
    categories: dict[str, int] = {}
    last_active_ts = 0.0

    for pos in positions:
        cur_value = float(pos.get("currentValue") or 0)
        init_value = float(pos.get("initialValue") or pos.get("amountUSD") or 0)
        size = init_value or cur_value

        # Determine win/loss: currentValue > 0 after resolution means won
        # Polymarket sets currentValue=0 for losing positions on resolution
        resolved_value = float(pos.get("resolvedValue") or cur_value)
        if resolved_value > 0.01:
            wins += 1
        else:
            losses += 1

        total_size += size

        # Category from market tags
        market = pos.get("market") or {}
        tags = market.get("tags") or []
        for tag in tags:
            if isinstance(tag, str):
                label = tag.lower()
            elif isinstance(tag, dict):
                label = (tag.get("label") or "").lower()
            else:
                label = ""
            if label:
                categories[label] = categories.get(label, 0) + 1

        # Track recency
        end_ts = pos.get("endDate") or pos.get("closedAt") or 0
        try:
            ts = float(end_ts)
            if ts > last_active_ts:
                last_active_ts = ts
        except (TypeError, ValueError):
            pass

    total = wins + losses
    win_rate = wins / total if total > 0 else 0.0
    avg_size = total_size / total if total > 0 else 0.0
    top_categories = sorted(categories, key=lambda k: categories[k], reverse=True)[:5]

    return WalletHistory(
        address=address.lower(),
        total_trades=total,
        wins=wins,
        losses=losses,
        win_rate=round(win_rate, 4),
        avg_size_usd=round(avg_size, 2),
        preferred_categories=top_categories,
        last_active_ts=last_active_ts,
        fetched_at=time.time(),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_wallet_history(address: str, force_refresh: bool = False) -> WalletHistory:
    """
    Return WalletHistory for a Polygon wallet address.

    Tries cache first (1h TTL). Falls back to gamma-api if stale or missing.

    Args:
        address: Polygon EOA address (checksummed or lowercase).
        force_refresh: Skip cache and always fetch from API.

    Returns:
        WalletHistory with win_rate, total_trades, etc.
    """
    if not force_refresh:
        cached = load_cached_history(address)
        if cached is not None:
            return cached

    positions = _fetch_positions(address)
    history = _parse_history(address, positions)
    save_history(address, history)
    return history
