"""
core/fii_score_analytics.py — Score velocity, acceleration, persistence,
and relative strength metrics from the fii_daily_snapshot table.

All functions operate on history lists (newest-first). The bulk helper
get_universe_analytics issues a single SQL query for the entire universe.

EMA smoothing (span=3) is applied to score series before computing velocity
to suppress single-cycle spikes from data quality noise.

Public API:
    compute_score_velocity(history, window, ema_span)  -> float | None
    compute_score_acceleration(history, window)         -> float | None
    compute_score_persistence(history, threshold, above) -> int
    get_score_analytics(conn, ticker, days)             -> dict
    get_universe_analytics(conn, tickers, days)         -> dict[str, dict]
    get_relative_strength_bulk(conn, tickers, days)     -> dict[str, float | None]
"""

from __future__ import annotations

import datetime
import sqlite3

from core.fii_ledger import get_fii_history
from core.logger import logger


# ---------------------------------------------------------------------------
# EMA helper
# ---------------------------------------------------------------------------

def _ema_smooth(values: list[float], span: int) -> list[float]:
    """Exponential moving average (oldest-first input, oldest-first output).

    alpha = 2 / (span + 1). span=3 gives 50% weight to last 2 observations.
    At least 1 element required.
    """
    if not values:
        return []
    alpha = 2.0 / (span + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(alpha * v + (1 - alpha) * out[-1])
    return out


# ---------------------------------------------------------------------------
# Primitive metrics — operate on newest-first history lists
# ---------------------------------------------------------------------------

def compute_score_velocity(
    history: list[dict],
    window: int = 7,
    ema_span: int = 3,
) -> float | None:
    """EMA-smoothed points-per-day score change over the last `window` days.

    EMA (span=3) suppresses single-cycle data noise before computing slope.
    Returns None with fewer than 2 data points in the window.
    """
    if len(history) < 2:
        return None
    cutoff = _cutoff_date(window)
    recent = [h for h in history if h["date"] >= cutoff]
    if len(recent) < 2:
        return None

    # Reverse to oldest-first, smooth, then read endpoints
    oldest_first = list(reversed(recent))
    raw_scores   = [h["alpha_score"] for h in oldest_first]
    smoothed     = _ema_smooth(raw_scores, span=ema_span)

    days = _days_between(oldest_first[0]["date"], oldest_first[-1]["date"])
    if days == 0:
        return None
    return round((smoothed[-1] - smoothed[0]) / days, 3)


def compute_score_acceleration(history: list[dict], window: int = 14) -> float | None:
    """Second derivative of score: is momentum increasing or decreasing?

    Splits the window in half; compares EMA-smoothed velocity of the newer
    half against the older half. Positive = acceleration, negative = deceleration.
    Returns None with fewer than 4 data points in the window.
    """
    if len(history) < 4:
        return None
    cutoff = _cutoff_date(window)
    recent = [h for h in history if h["date"] >= cutoff]
    if len(recent) < 4:
        return None
    half = len(recent) // 2
    v_older = _velocity_of_segment(recent[half:])   # older half (newest-first)
    v_newer = _velocity_of_segment(recent[:half])   # newer half (newest-first)
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
    history must be newest-first.
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
    """Return complete analytics dict for one ticker.

    Keys:
        velocity_7d     float | None  — EMA-smoothed pts/day over 7 days
        velocity_30d    float | None  — EMA-smoothed pts/day over 30 days
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

    Returns dict mapping ticker (uppercase) → analytics dict.
    Tickers with no snapshots get empty analytics.
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
# Relative strength vs IFIX benchmark
# ---------------------------------------------------------------------------

def get_relative_strength_bulk(
    conn: sqlite3.Connection,
    tickers: list[str],
    days: int = 30,
) -> dict[str, float | None]:
    """Compute relative strength vs IFIX11.SA for each ticker.

    RS = fii_price_return_Nd - ifix_price_return_Nd

    Positive RS means the FII outperformed IFIX over the period.
    Returns dict ticker → RS (None if insufficient price history).

    IFIX11.SA prices are fetched once from yfinance and cached in-process.
    """
    if not tickers:
        return {}

    ifix_return = _get_ifix_return(days)
    upper = [t.upper() for t in tickers]
    cutoff = _cutoff_date(days)
    rs_map: dict[str, float | None] = {t: None for t in upper}
    rows = _price_returns_fallback(conn, upper, cutoff)

    for row in rows:
        p0 = float(row["price_start"] or 0)
        p1 = float(row["price_end"]   or 0)
        if p0 <= 0 or p1 <= 0:
            continue
        fii_return = (p1 / p0) - 1.0
        rs_map[row["ticker"]] = round(fii_return - ifix_return, 4) if ifix_return is not None else None

    return rs_map


# ---------------------------------------------------------------------------
# IFIX price return (cached per process run)
# ---------------------------------------------------------------------------

_ifix_cache: dict[int, float | None] = {}   # days → return


def _get_ifix_return(days: int) -> float | None:
    """Fetch IFIX11.SA return over `days` calendar days. Cached per-process."""
    if days in _ifix_cache:
        return _ifix_cache[days]
    try:
        import yfinance as yf
        start = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        hist  = yf.Ticker("IFIX11.SA").history(start=start, auto_adjust=True)
        if hist.empty or len(hist) < 2:
            _ifix_cache[days] = None
            return None
        p0 = float(hist["Close"].iloc[0])
        p1 = float(hist["Close"].iloc[-1])
        ret = round((p1 / p0) - 1.0, 6) if p0 > 0 else None
        _ifix_cache[days] = ret
        return ret
    except Exception as exc:
        logger.warning("fii_score_analytics: IFIX11.SA fetch failed: %s", exc)
        _ifix_cache[days] = None
        return None


def _price_returns_fallback(
    conn: sqlite3.Connection,
    tickers: list[str],
    cutoff: str,
) -> list[dict]:
    """Compute first/last prices per ticker without SQL window functions."""
    param_marks = ",".join("?" * len(tickers))
    try:
        rows = conn.execute(
            f"""
            SELECT ticker, date, price
              FROM fii_daily_snapshot
             WHERE ticker IN ({param_marks})
               AND date >= ?
               AND price > 0
             ORDER BY ticker, date
            """,
            (*tickers, cutoff),
        ).fetchall()
    except sqlite3.Error:
        return []

    grouped: dict[str, list] = {}
    for row in rows:
        grouped.setdefault(row["ticker"], []).append(row)

    return [
        {
            "ticker":      ticker,
            "price_start": float(group[0]["price"]),
            "price_end":   float(group[-1]["price"]),
        }
        for ticker, group in grouped.items()
    ]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _cutoff_date(window_days: int) -> str:
    return (datetime.date.today() - datetime.timedelta(days=window_days)).isoformat()


def _days_between(date_a: str, date_b: str) -> int:
    a = datetime.date.fromisoformat(date_a)
    b = datetime.date.fromisoformat(date_b)
    return abs((b - a).days)


def _velocity_of_segment(segment: list[dict]) -> float | None:
    """EMA-smoothed velocity (pts/day) for a newest-first history segment."""
    if len(segment) < 2:
        return None
    oldest_first = list(reversed(segment))
    raw    = [h["alpha_score"] for h in oldest_first]
    smooth = _ema_smooth(raw, span=3)
    days   = _days_between(oldest_first[0]["date"], oldest_first[-1]["date"])
    if days == 0:
        return None
    return (smooth[-1] - smooth[0]) / days


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
