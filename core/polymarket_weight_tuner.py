"""
core/polymarket_weight_tuner.py — Adaptive weight tuning based on calibration.

Adjusts composite score weights based on per-category Brier scores.
Categories performing worse than the random baseline (0.25) lose weight;
categories performing better gain weight. Changes are bounded at ±5pp and
weights always sum to 1.0 after normalization.

Public API:
    tune_weights(report, current_weights) -> WeightUpdate
    save_learned_weights(weights, history_entry, conn) -> None
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from core.logger import logger
from core.polymarket_calibration import CalibrationReport

_LEARNED_WEIGHTS_PATH = Path("data/learned_weights.json")
_BRIER_BASELINE = 0.25       # Random 50/50 forecast Brier score
_MAX_DELTA_PP = 0.05         # Maximum weight change per tuning cycle (5 pp)
_MIN_CATEGORY_SAMPLES = 5    # Skip categories with fewer resolved markets

# Mapping from category label to the weight key it informs
_CATEGORY_TO_WEIGHT: dict[str, str] = {
    "politics": "w_news",
    "sports": "w_liquidity",
    "crypto": "w_edge",
    "economics": "w_edge",
    "science": "w_news",
    "entertainment": "w_copy",
    "unknown": "w_edge",
}


@dataclass
class WeightUpdate:
    """Result of a weight tuning cycle."""

    weights_before: dict[str, float]
    weights_after: dict[str, float]
    brier_score: float
    win_rate: float
    trigger_markets: int
    deltas: dict[str, float] = field(default_factory=dict)
    tuned_at: float = field(default_factory=time.time)


def _clamp_delta(delta: float) -> float:
    """Clamp a weight change to ±_MAX_DELTA_PP."""
    return max(-_MAX_DELTA_PP, min(_MAX_DELTA_PP, delta))


def tune_weights(
    report: CalibrationReport,
    current_weights: dict[str, float],
) -> WeightUpdate:
    """Compute updated weights based on per-category Brier performance.

    For each category with enough samples, the Brier score is compared to the
    random baseline (0.25). Categories performing better increase the weight
    of their associated scoring dimension; those performing worse decrease it.
    Changes are bounded at ±5pp. Final weights are normalised to sum to 1.0.

    Args:
        report: CalibrationReport from compute_calibration_stats.
        current_weights: Current weight dictionary (keys: w_edge etc.).

    Returns:
        WeightUpdate with before/after weights and per-key deltas.
    """
    weights = dict(current_weights)
    deltas: dict[str, float] = {}

    for cat_stats in report.categories:
        if cat_stats.resolved_count < _MIN_CATEGORY_SAMPLES:
            continue

        weight_key = _CATEGORY_TO_WEIGHT.get(cat_stats.category, "w_edge")

        # Positive delta when Brier is LOWER than baseline (better calibration)
        # Scale: 0.25 worse → -5pp, 0.25 better → +5pp
        brier_diff = _BRIER_BASELINE - cat_stats.brier_score  # positive = better
        raw_delta = (brier_diff / _BRIER_BASELINE) * _MAX_DELTA_PP
        clamped = _clamp_delta(raw_delta)

        # Accumulate deltas per weight key (multiple categories may map to same key)
        deltas[weight_key] = deltas.get(weight_key, 0.0) + clamped

    # Apply deltas
    for key, delta in deltas.items():
        if key in weights:
            weights[key] = max(0.01, weights[key] + delta)

    # Normalise to sum to 1.0
    total = sum(weights.values())
    if total > 0:
        weights = {k: round(v / total, 6) for k, v in weights.items()}

    # Ensure exact sum = 1.0 (fix floating-point residue on first key)
    residue = round(1.0 - sum(weights.values()), 6)
    if residue and weights:
        first_key = next(iter(weights))
        weights[first_key] = round(weights[first_key] + residue, 6)

    return WeightUpdate(
        weights_before=dict(current_weights),
        weights_after=weights,
        brier_score=report.overall_brier,
        win_rate=report.overall_win_rate,
        trigger_markets=report.total_resolved,
        deltas=deltas,
    )


def save_learned_weights(
    weights: dict[str, float],
    history_entry: dict,
    conn: sqlite3.Connection,
) -> None:
    """Persist learned weights to disk and insert a history row in the ledger.

    Args:
        weights: The new weight dictionary to save.
        history_entry: Dict with keys: weights_before, brier_score, win_rate,
                       trigger_markets (all serialisable).
        conn: Open ledger connection.
    """
    _LEARNED_WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LEARNED_WEIGHTS_PATH.write_text(json.dumps(weights, indent=2))
    logger.info("save_learned_weights: wrote %s", _LEARNED_WEIGHTS_PATH)

    try:
        conn.execute(
            """
            INSERT INTO pm_weight_history
                (tuned_at, trigger_markets, weights_before, weights_after,
                 brier_score, win_rate)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                time.time(),
                history_entry.get("trigger_markets", 0),
                json.dumps(history_entry.get("weights_before", {})),
                json.dumps(weights),
                history_entry.get("brier_score", 0.0),
                history_entry.get("win_rate", 0.0),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.error("save_learned_weights: DB insert failed: %s", exc)


def load_learned_weights() -> dict[str, float] | None:
    """Load previously saved learned weights from disk.

    Returns:
        Weight dictionary if the file exists and is valid, else None.
    """
    if not _LEARNED_WEIGHTS_PATH.exists():
        return None
    try:
        data = json.loads(_LEARNED_WEIGHTS_PATH.read_text())
        if not isinstance(data, dict):
            return None
        # Validate all values are positive floats
        if not all(isinstance(v, (int, float)) and v >= 0 for v in data.values()):
            return None
        return {k: float(v) for k, v in data.items()}
    except Exception as exc:
        logger.warning("load_learned_weights: could not load %s: %s", _LEARNED_WEIGHTS_PATH, exc)
        return None
