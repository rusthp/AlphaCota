"""
core/fii_score_analytics.py — Score velocity, acceleration, and persistence
metrics derived from the fii_daily_snapshot table.

All functions operate on history lists returned by get_fii_history
(newest-first ordering). The bulk helper get_universe_analytics issues
a single SQL query for the entire universe rather than N individual calls.

Public API:
    compute_score_velocity(history, window)    -> float | None
    compute_score_acceleration(history, window) -> float | None
    compute_score_persistence(history, threshold, above) -> int
    get_score_analytics(conn, ticker, days)    -> dict
    get_universe_analytics(conn, tickers, days) -> dict[str, dict]
"""

from __future__ import annotations

import datetime
import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from core.fii_ledger import get_fii_history
from core.logger import logger


# ---------------------------------------------------------------------------
# Primitive metrics — operate on newest-first history lists
# ---------------------------------------------------------------------------

def compute_score_velocity(history: list[dict], window: int = 7) -> float | None:
    """Points-per-day score change over the last `window` calendar days.

    Positive = improving, negative = deteriorating.
    Returns None with fewer than 2 points in the window.
    """
    if len(history) < 2:
        return None
    cutoff = _cutoff_date(window)
    recent = [h for h in history if h["date"] >= cutoff]
    if len(recent) < 2:
        return None
    days = _days_between(recent[-1]["date"], recent[0]["date"])
    if days == 0:
        return None
    return round((recent[0]["alpha_score"] - recent[-1]["alpha_score"]) / days, 3)


def compute_score_acceleration(history: list[dict], window: int = 14) -> float | None:
    """Second derivative of score: is momentum increasing or decreasing?

    Splits the window in half; compares velocity of the newer half against
    the older half. Positive = acceleration, negative = deceleration.
    Returns None with fewer than 4 points in the window.
    """
    if len(history) < 4:
        return None
    cutoff = _cutoff_date(window)
    recent = [h for h in history if h["date"] >= cutoff]
    if len(recent) < 4:
        return None
    half = len(recent) // 2
    v_older  = _velocity_of(recent[half:])   # older half (indices half…end)
    v_newer  = _velocity_of(recent[:half])   # newer half (indices 0…half)
    if v_older is None or v_newer is None:
        return None
    return round(v_newer - v_older, 3)


def compute_score_persistence(
    history: list[dict],
    threshold: float,
    above: bool = True,
) -> int:
    """Consecutive snapshots satisfying (score >= threshold) or (score < threshold).

    Counts from the most recent snapshot backward until the condition breaks.
    history must be newest-first (standard output of get_fii_history).
    """
    count = 0
    for row in history:
        meets = (row["alpha_score"] >= threshold) if above else (row["alpha_score"] < threshold)
        if meets:
            count += 1
        else:
            break
    return count


# ---------------------------------------------------------------------------
# Single-ticker analytics
# ---------------------------------------------------------------------------

def get_score_analytics(
    conn: sqlite3.Connection,
    ticker: str,
    days: int = 60,
) -> dict:
    """Return a complete analytics dict for one ticker.

    Keys:
        velocity_7d     float | None  — pts/day over 7 days
        velocity_30d    float | None  — pts/day over 30 days
        acceleration    float | None  — change in velocity over 14 days
        days_above_80   int           — consecutive snapshots with score ≥ 80
        days_below_45   int           — consecutive snapshots with score < 45
        trend           str           — "rising" | "falling" | "stable" | "unknown"
        score_latest    float | None
        score_30d_ago   float | None
    """
    history = get_fii_history(conn, ticker, days)
    return _analytics_from_history(history)


# ---------------------------------------------------------------------------
# Bulk universe analytics (single SQL round-trip)
# ---------------------------------------------------------------------------

def get_universe_analytics(
    conn: sqlite3.Connection,
    tickers: list[str],
    days: int = 60,
) -> dict[str, dict]:
    """Return analytics for each ticker in one SQL query.

    Returns a dict mapping ticker (uppercase) → analytics dict.
    Tickers with no snapshots receive empty analytics (all None / 0).
    """
    if not tickers:
        return {}
    upper = [t.upper() for t in tickers]
    param_marks = ",".join("?" * len(upper))
    cutoff = _cutoff_date(days)
    per_ticker: dict[str, list[dict]] = {t: [] for t in upper}
    try:
        rows = conn.execute(
            f"""
            SELECT ticker, date, alpha_score
              FROM fii_daily_snapshot
             WHERE ticker IN ({param_marks})
               AND date >= ?
             ORDER BY ticker, date DESC
            """,
            (*upper, cutoff),
        ).fetchall()
        for row in rows:
            per_ticker[row["ticker"]].append({
                "date": row["date"],
                "alpha_score": float(row["alpha_score"]),
            })
    except sqlite3.Error as exc:
        logger.warning("get_universe_analytics: %s", exc)
        return {t: _empty_analytics() for t in upper}

    return {t: _analytics_from_history(per_ticker[t]) for t in upper}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _cutoff_date(window_days: int) -> str:
    return (datetime.date.today() - datetime.timedelta(days=window_days)).isoformat()


def _days_between(date_a: str, date_b: str) -> int:
    a = datetime.date.fromisoformat(date_a)
    b = datetime.date.fromisoformat(date_b)
    return abs((b - a).days)


def _velocity_of(segment: list[dict]) -> float | None:
    """Velocity (pts/day) for a newest-first history segment."""
    if len(segment) < 2:
        return None
    days = _days_between(segment[-1]["date"], segment[0]["date"])
    if days == 0:
        return None
    return (segment[0]["alpha_score"] - segment[-1]["alpha_score"]) / days


def _analytics_from_history(history: list[dict]) -> dict:
    if not history:
        return _empty_analytics()
    v7   = compute_score_velocity(history, window=7)
    v30  = compute_score_velocity(history, window=30)
    acc  = compute_score_acceleration(history, window=14)
    da80 = compute_score_persistence(history, threshold=80.0, above=True)
    db45 = compute_score_persistence(history, threshold=45.0, above=False)
    score_latest  = history[0]["alpha_score"]
    score_30d_ago = history[-1]["alpha_score"] if len(history) >= 2 else None
    if v7 is None:
        trend = "unknown"
    elif v7 >= 0.5:
        trend = "rising"
    elif v7 <= -0.5:
        trend = "falling"
    else:
        trend = "stable"
    return {
        "velocity_7d":   round(v7, 3) if v7 is not None else None,
        "velocity_30d":  round(v30, 3) if v30 is not None else None,
        "acceleration":  round(acc, 3) if acc is not None else None,
        "days_above_80": da80,
        "days_below_45": db45,
        "trend":         trend,
        "score_latest":  round(score_latest, 2),
        "score_30d_ago": round(score_30d_ago, 2) if score_30d_ago is not None else None,
    }


def _empty_analytics() -> dict:
    return {
        "velocity_7d":   None,
        "velocity_30d":  None,
        "acceleration":  None,
        "days_above_80": 0,
        "days_below_45": 0,
        "trend":         "unknown",
        "score_latest":  None,
        "score_30d_ago": None,
    }
