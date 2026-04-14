"""
core/polymarket_alpha_detector.py — Rank Polymarket wallets by alpha quality.

Scoring formula (all components 0–1, weighted sum):
  alpha_score = 0.50 * win_rate
              + 0.30 * recency_weight   (exponential decay, half-life 30 days)
              + 0.20 * diversity_score  (unique categories / 5, capped at 1)

Only wallets with >= min_trades resolved positions are scored.

Usage:
    from core.polymarket_alpha_detector import rank_wallets, detect_top_alpha_wallets

    scores = rank_wallets(["0xabc...", "0xdef..."])
    top = detect_top_alpha_wallets(limit=5)
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass

from core.polymarket_wallet_tracker import WalletHistory, get_wallet_history

_HALF_LIFE_DAYS = 30.0  # recency weight half-life


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class WalletScore:
    address: str
    alpha_score: float       # 0.0 – 1.0 composite score
    win_rate: float          # 0.0 – 1.0
    total_trades: int
    recency_weight: float    # 0.0 – 1.0
    diversity_score: float   # 0.0 – 1.0
    preferred_categories: list[str]
    last_active_ts: float


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _recency_weight(last_active_ts: float) -> float:
    """Exponential decay: score=1.0 if active today, 0.5 after 30 days."""
    if last_active_ts <= 0:
        return 0.0
    days_since = (time.time() - last_active_ts) / 86400.0
    return math.exp(-math.log(2) * days_since / _HALF_LIFE_DAYS)


def _diversity_score(categories: list[str]) -> float:
    """Unique category count / 5, capped at 1.0."""
    return min(len(set(categories)) / 5.0, 1.0)


def _score_wallet(history: WalletHistory) -> WalletScore:
    recency = _recency_weight(history.last_active_ts)
    diversity = _diversity_score(history.preferred_categories)
    alpha = (
        0.50 * history.win_rate
        + 0.30 * recency
        + 0.20 * diversity
    )
    return WalletScore(
        address=history.address,
        alpha_score=round(alpha, 4),
        win_rate=history.win_rate,
        total_trades=history.total_trades,
        recency_weight=round(recency, 4),
        diversity_score=round(diversity, 4),
        preferred_categories=history.preferred_categories,
        last_active_ts=history.last_active_ts,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def rank_wallets(
    addresses: list[str],
    min_trades: int = 20,
) -> list[WalletScore]:
    """
    Fetch history for each address, filter by min_trades, and return ranked list.

    Args:
        addresses: List of Polygon wallet addresses.
        min_trades: Minimum resolved trades required to qualify.

    Returns:
        List of WalletScore sorted descending by alpha_score.
    """
    scores: list[WalletScore] = []
    for addr in addresses:
        try:
            history = get_wallet_history(addr)
            if history.total_trades < min_trades:
                continue
            scores.append(_score_wallet(history))
        except Exception:
            continue
    return sorted(scores, key=lambda s: s.alpha_score, reverse=True)


def detect_top_alpha_wallets(limit: int = 10) -> list[WalletScore]:
    """
    Rank wallets from the configured watchlist and return top `limit`.

    Watchlist is read from env var POLYMARKET_WATCH_WALLETS (comma-separated addresses).
    If not set, returns empty list.

    Args:
        limit: Maximum number of wallets to return.

    Returns:
        Top-ranked WalletScore list.
    """
    raw = os.environ.get("POLYMARKET_WATCH_WALLETS", "")
    addresses = [a.strip() for a in raw.split(",") if a.strip()]
    if not addresses:
        return []
    ranked = rank_wallets(addresses)
    return ranked[:limit]
