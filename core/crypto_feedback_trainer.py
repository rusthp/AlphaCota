"""
core/crypto_feedback_trainer.py — Periodic model re-training with feedback loop.

Orchestrates the full adaptive learning cycle for the crypto trader:
    1. Check if a re-train is due based on the last_feedback_at timestamp
       stored in the model meta JSON.
    2. If due (or force=True):
       a. Run train_from_trades() — feedback fine-tune with real outcomes.
       b. If ≥ 50 trades available and accepted: persist model update.
       c. Optionally trigger a full base re-train (weekly OHLCV, heavier).
    3. Log all outcomes so operators can audit via the daily summary.

This module is designed to be called from the autonomous loop every
_FEEDBACK_RETRAIN_EVERY iterations (default ≈ 7 days at 5-min candles),
or triggered manually via the API endpoint.

Public API:
    retrain_if_due(conn, mode, model_dir, force) -> bool
    retrain_full(mode, model_dir) -> TrainResult
    get_retrain_status(model_dir) -> dict
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from core.logger import logger

_DEFAULT_MODEL_DIR = Path(".models")
_META_FILE = "crypto_lgbm_meta.json"

# Re-train thresholds
_FEEDBACK_INTERVAL_DAYS = 7          # days between feedback fine-tunes
_FULL_RETRAIN_INTERVAL_DAYS = 30     # days between full OHLCV re-trains
_MIN_TRADES_FOR_FEEDBACK = 50        # minimum closed trades to trigger feedback
_MAX_ACCURACY_DROP = 0.05            # reject feedback model if accuracy drops > 5%


def get_retrain_status(model_dir: str | Path = _DEFAULT_MODEL_DIR) -> dict:
    """Return current model training status from the meta JSON.

    Args:
        model_dir: Directory containing the trained model and meta JSON.

    Returns:
        Dict with keys: trained_at, last_feedback_at, cv_accuracy,
        feedback_accuracy, feedback_trades, days_since_train,
        days_since_feedback, feedback_due, full_retrain_due.
    """
    meta_path = Path(model_dir) / _META_FILE
    if not meta_path.exists():
        return {
            "trained_at": None,
            "last_feedback_at": None,
            "cv_accuracy": None,
            "feedback_accuracy": None,
            "feedback_trades": 0,
            "days_since_train": None,
            "days_since_feedback": None,
            "feedback_due": True,
            "full_retrain_due": True,
        }

    try:
        meta = json.loads(meta_path.read_text())
    except Exception:
        return {"error": "could not parse meta JSON"}

    now = time.time()
    trained_at = meta.get("trained_at")
    last_feedback_at = meta.get("last_feedback_at")

    days_since_train = (now - trained_at) / 86_400 if trained_at else None
    days_since_feedback = (now - last_feedback_at) / 86_400 if last_feedback_at else None

    return {
        "trained_at": trained_at,
        "last_feedback_at": last_feedback_at,
        "cv_accuracy": meta.get("cv_accuracy"),
        "feedback_accuracy": meta.get("feedback_accuracy"),
        "feedback_trades": meta.get("feedback_trades", 0),
        "feedback_samples": meta.get("feedback_samples", 0),
        "days_since_train": round(days_since_train, 2) if days_since_train else None,
        "days_since_feedback": round(days_since_feedback, 2) if days_since_feedback else None,
        "feedback_due": (
            days_since_feedback is None
            or days_since_feedback >= _FEEDBACK_INTERVAL_DAYS
        ),
        "full_retrain_due": (
            days_since_train is None
            or days_since_train >= _FULL_RETRAIN_INTERVAL_DAYS
        ),
        "symbols": meta.get("symbols", []),
        "interval": meta.get("interval", "15m"),
    }


def retrain_if_due(
    conn: sqlite3.Connection,
    mode: str = "paper",
    model_dir: str | Path = _DEFAULT_MODEL_DIR,
    force: bool = False,
) -> bool:
    """Run a feedback fine-tune if the schedule requires it (or force=True).

    Decision logic:
        1. If force=True OR feedback_due (≥7 days since last) → run
           train_from_trades().
        2. If full_retrain_due (≥30 days since last full train) → also
           trigger full OHLCV train (expensive, runs async-style in-process).
        3. Returns True if any re-train actually ran, False otherwise.

    Args:
        conn: Open sqlite3.Connection to the AlphaCota database.
        mode: \"paper\" or \"live\" — passed to train_from_trades.
        model_dir: Directory where model artefacts are stored.
        force: If True, bypass the time-based guard and run immediately.

    Returns:
        True when at least one re-train was executed, False when skipped.
    """
    from core.crypto_ml_model import train_from_trades

    status = get_retrain_status(model_dir)
    did_retrain = False

    # --- Feedback fine-tune ------------------------------------------------
    if force or status.get("feedback_due", True):
        logger.info(
            "crypto_feedback_trainer: running feedback fine-tune "
            "(mode=%s force=%s days_since=%.1f)",
            mode,
            force,
            status.get("days_since_feedback") or 0.0,
        )
        try:
            result = train_from_trades(
                conn=conn,
                mode=mode,
                model_dir=model_dir,
                min_trades=_MIN_TRADES_FOR_FEEDBACK,
                max_accuracy_drop=_MAX_ACCURACY_DROP,
            )
            if result.accepted:
                logger.info(
                    "crypto_feedback_trainer: feedback accepted — "
                    "trades=%d samples=%d accuracy=%.4f",
                    result.trades_used,
                    result.samples_built,
                    result.feedback_accuracy,
                )
                did_retrain = True
            elif result.trades_used == 0:
                logger.info(
                    "crypto_feedback_trainer: skipped — insufficient trades (%d < %d)",
                    result.trades_used,
                    _MIN_TRADES_FOR_FEEDBACK,
                )
            else:
                logger.warning(
                    "crypto_feedback_trainer: feedback rejected — "
                    "accuracy_drop=%.4f > threshold=%.2f",
                    result.baseline_accuracy - result.feedback_accuracy,
                    _MAX_ACCURACY_DROP,
                )
        except Exception as exc:
            logger.error("crypto_feedback_trainer: feedback fine-tune failed: %s", exc)
    else:
        logger.debug(
            "crypto_feedback_trainer: feedback not due "
            "(%.1f days since last, need %.1f)",
            status.get("days_since_feedback") or 0.0,
            _FEEDBACK_INTERVAL_DAYS,
        )

    # --- Full OHLCV re-train (monthly) ------------------------------------
    if status.get("full_retrain_due", False) and not status.get("days_since_train") is None:
        logger.info(
            "crypto_feedback_trainer: triggering full OHLCV re-train "
            "(%.1f days since last)",
            status.get("days_since_train") or 0.0,
        )
        try:
            train_result = retrain_full(mode=mode, model_dir=model_dir)
            logger.info(
                "crypto_feedback_trainer: full re-train complete — "
                "accuracy=%.4f candles=%d",
                train_result.accuracy,
                train_result.candles_total,
            )
            did_retrain = True
        except Exception as exc:
            logger.error("crypto_feedback_trainer: full re-train failed: %s", exc)

    return did_retrain


def retrain_full(
    mode: str = "paper",  # noqa: ARG001 — reserved for future live-only data
    model_dir: str | Path = _DEFAULT_MODEL_DIR,
    symbols: list[str] | None = None,
    days: int = 730,
    download: bool = False,
) -> "TrainResult":  # type: ignore[name-defined]
    """Trigger a full base re-train on OHLCV historical data.

    This is the heavyweight monthly operation. It re-trains the LightGBM
    from scratch on the full OHLCV history, replacing the model entirely
    (doesn't blend with feedback model).

    Args:
        mode: Unused; reserved for future mode-specific data selection.
        model_dir: Where to save the trained model.
        symbols: Pairs to train on. Defaults to all AlphaCota pairs.
        days: Historical time window in days (default 730 = 2 years).
        download: If True, re-downloads OHLCV from Binance first.

    Returns:
        TrainResult from crypto_ml_model.train().
    """
    from core.crypto_ml_model import train

    logger.info(
        "crypto_feedback_trainer: starting full re-train (days=%d download=%s)",
        days, download,
    )
    return train(
        symbols=symbols,
        interval="15m",
        days=days,
        model_dir=model_dir,
        download=download,
    )
