"""
core/polymarket_calibration.py — Forecast calibration engine for Polymarket.

Tracks AI probability forecasts against actual market outcomes, computes
Brier scores per category, and produces reliability diagrams.

Public API:
    record_outcome(position_id, condition_id, entry_prob, ai_estimate,
                   resolved_yes, category, edge_at_entry, conn) -> bool
    compute_calibration_stats(conn, lookback_days) -> CalibrationReport
    reliability_bins(conn, lookback_days) -> list[ReliabilityPoint]
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field


@dataclass
class CategoryStats:
    """Calibration statistics for a single market category."""

    category: str
    brier_score: float       # Mean squared error (0.0 = perfect, 0.25 = random)
    win_rate: float          # Fraction of resolved YES positions that were correct
    mean_edge: float         # Mean |ai_estimate - entry_prob| at entry
    resolved_count: int      # Number of resolved markets in this category


@dataclass
class CalibrationReport:
    """Aggregate calibration report across all categories."""

    overall_brier: float
    overall_win_rate: float
    total_resolved: int
    lookback_days: int
    categories: list[CategoryStats] = field(default_factory=list)
    generated_at: float = field(default_factory=time.time)


@dataclass
class ReliabilityPoint:
    """A single bin in a reliability diagram."""

    bin_low: float           # Lower bound of probability bin (e.g. 0.20)
    bin_high: float          # Upper bound of probability bin (e.g. 0.30)
    predicted_prob: float    # Mean AI estimate within this bin
    actual_win_rate: float   # Actual fraction that resolved YES
    count: int               # Number of observations in this bin


def record_outcome(
    condition_id: str,
    entry_prob: float,
    ai_estimate: float | None,
    resolved_yes: bool,
    conn: sqlite3.Connection,
    category: str = "",
    edge_at_entry: float = 0.0,
) -> bool:
    """Record a calibration entry for a resolved market.

    Idempotent: a second call for the same condition_id is silently ignored.

    Args:
        condition_id: Polymarket condition ID.
        entry_prob: Market YES price at trade entry.
        ai_estimate: AI-estimated fair probability, or None.
        resolved_yes: True if the market resolved YES.
        conn: Open ledger connection.
        category: Market category label.
        edge_at_entry: |ai_estimate - entry_prob| at entry time.

    Returns:
        True if a new record was written, False if already present.
    """
    from core.polymarket_ledger import insert_calibration_record

    return insert_calibration_record(
        conn=conn,
        condition_id=condition_id,
        entry_prob=entry_prob,
        ai_estimate=ai_estimate,
        resolved_yes=resolved_yes,
        category=category,
        edge_at_entry=edge_at_entry,
    )


def _brier_score(forecasts: list[float], outcomes: list[float]) -> float:
    """Compute mean Brier score: mean((forecast - outcome)^2).

    Args:
        forecasts: List of probability forecasts in [0, 1].
        outcomes: List of binary outcomes (1.0 = YES, 0.0 = NO).

    Returns:
        Mean Brier score. Returns 0.25 (random baseline) for empty inputs.
    """
    if not forecasts:
        return 0.25
    n = len(forecasts)
    return sum((f - o) ** 2 for f, o in zip(forecasts, outcomes, strict=True)) / n


def compute_calibration_stats(
    conn: sqlite3.Connection,
    lookback_days: int = 90,
) -> CalibrationReport:
    """Compute calibration statistics from resolved market records.

    Args:
        conn: Open ledger connection.
        lookback_days: How far back to look (default 90 days).

    Returns:
        CalibrationReport with overall and per-category statistics.
    """
    cutoff = time.time() - lookback_days * 86400.0
    rows = conn.execute(
        """
        SELECT condition_id, entry_prob, ai_estimate, resolved_yes,
               category, edge_at_entry
        FROM pm_calibration
        WHERE created_at >= ?
        ORDER BY created_at DESC
        """,
        (cutoff,),
    ).fetchall()

    if not rows:
        return CalibrationReport(
            overall_brier=0.25,
            overall_win_rate=0.0,
            total_resolved=0,
            lookback_days=lookback_days,
            categories=[],
        )

    # Compute overall stats using AI estimate as forecast; fall back to entry_prob
    all_forecasts: list[float] = []
    all_outcomes: list[float] = []
    wins = 0

    categories_data: dict[str, dict] = {}

    for row in rows:
        ai_est = row["ai_estimate"]
        forecast = float(ai_est) if ai_est is not None else float(row["entry_prob"])
        outcome = 1.0 if row["resolved_yes"] else 0.0

        all_forecasts.append(forecast)
        all_outcomes.append(outcome)
        if row["resolved_yes"]:
            wins += 1

        cat = row["category"] or "unknown"
        if cat not in categories_data:
            categories_data[cat] = {"forecasts": [], "outcomes": [], "edges": [], "wins": 0}
        categories_data[cat]["forecasts"].append(forecast)
        categories_data[cat]["outcomes"].append(outcome)
        categories_data[cat]["edges"].append(float(row["edge_at_entry"]))
        if row["resolved_yes"]:
            categories_data[cat]["wins"] += 1

    overall_brier = _brier_score(all_forecasts, all_outcomes)
    overall_win_rate = wins / len(rows) if rows else 0.0

    category_stats: list[CategoryStats] = []
    for cat, data in categories_data.items():
        n = len(data["forecasts"])
        cat_brier = _brier_score(data["forecasts"], data["outcomes"])
        cat_win_rate = data["wins"] / n if n else 0.0
        cat_mean_edge = sum(data["edges"]) / n if n else 0.0
        category_stats.append(CategoryStats(
            category=cat,
            brier_score=round(cat_brier, 6),
            win_rate=round(cat_win_rate, 4),
            mean_edge=round(cat_mean_edge, 4),
            resolved_count=n,
        ))

    # Sort by resolved count descending for readability
    category_stats.sort(key=lambda s: s.resolved_count, reverse=True)

    return CalibrationReport(
        overall_brier=round(overall_brier, 6),
        overall_win_rate=round(overall_win_rate, 4),
        total_resolved=len(rows),
        lookback_days=lookback_days,
        categories=category_stats,
    )


def reliability_bins(
    conn: sqlite3.Connection,
    lookback_days: int = 90,
) -> list[ReliabilityPoint]:
    """Group AI forecasts into 10 probability bins and compute actual win rates.

    Produces the data for a reliability (calibration) diagram. A perfectly
    calibrated model has predicted_prob ≈ actual_win_rate in every bin.

    Args:
        conn: Open ledger connection.
        lookback_days: How far back to look.

    Returns:
        List of 10 ReliabilityPoint objects (one per decile bin), in order
        from lowest to highest predicted probability.
    """
    cutoff = time.time() - lookback_days * 86400.0
    rows = conn.execute(
        """
        SELECT ai_estimate, entry_prob, resolved_yes
        FROM pm_calibration
        WHERE created_at >= ?
        """,
        (cutoff,),
    ).fetchall()

    # 10 bins: [0,0.1), [0.1,0.2), ..., [0.9,1.0]
    bins: list[dict] = [
        {"low": i / 10.0, "high": (i + 1) / 10.0, "forecasts": [], "outcomes": []}
        for i in range(10)
    ]

    for row in rows:
        ai_est = row["ai_estimate"]
        forecast = float(ai_est) if ai_est is not None else float(row["entry_prob"])
        outcome = 1.0 if row["resolved_yes"] else 0.0

        # Assign to bin; clamp forecast to [0, 1] first
        forecast = max(0.0, min(1.0, forecast))
        bin_idx = min(int(forecast * 10), 9)
        bins[bin_idx]["forecasts"].append(forecast)
        bins[bin_idx]["outcomes"].append(outcome)

    points: list[ReliabilityPoint] = []
    for b in bins:
        n = len(b["forecasts"])
        predicted = sum(b["forecasts"]) / n if n else (b["low"] + b["high"]) / 2.0
        actual = sum(b["outcomes"]) / n if n else 0.0
        points.append(ReliabilityPoint(
            bin_low=b["low"],
            bin_high=b["high"],
            predicted_prob=round(predicted, 4),
            actual_win_rate=round(actual, 4),
            count=n,
        ))

    return points
