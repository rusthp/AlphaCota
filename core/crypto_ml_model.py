"""
core/crypto_ml_model.py — LightGBM trade signal classifier.

Trains a multiclass classifier (long=1, flat=0, short=-1) on historical
OHLCV feature matrices. Exports confidence scores [0,1] per direction
that integrate directly into the strategy engine as "ml_signal".

Public API:
    train(symbols, interval, days, model_dir) -> TrainResult
    train_from_trades(conn, mode, model_dir, min_trades) -> TradesFeedbackResult
    load_model(model_dir) -> BotModel
    predict(model, df_recent) -> MLSignal
    get_confidence(symbol, interval, model_dir) -> MLSignal
"""

from __future__ import annotations

import json
import pickle
import time
from dataclasses import dataclass
from pathlib import Path

import sqlite3

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import LabelEncoder

from core.crypto_data_collector import download_pair, load_pair, SYMBOLS
from core.crypto_ml_features import prepare_dataset, build_features
from core.logger import logger

_DEFAULT_MODEL_DIR = Path(".models")
_MODEL_FILE = "crypto_lgbm.pkl"
_META_FILE = "crypto_lgbm_meta.json"


@dataclass
class MLSignal:
    symbol: str
    direction: str          # "long", "short", "flat"
    confidence: float       # 0.0–1.0 (probability of the predicted class)
    prob_long: float
    prob_flat: float
    prob_short: float
    timestamp: float


@dataclass
class TrainResult:
    symbols: list[str]
    candles_total: int
    features: int
    accuracy: float
    report: str
    model_path: str
    trained_at: float


@dataclass
class BotModel:
    clf: LGBMClassifier
    feature_names: list[str]
    label_map: dict[int, str]   # encoded int → "long"/"flat"/"short"
    trained_at: float
    symbols: list[str]


@dataclass
class TradesFeedbackResult:
    """Result of a real-trade feedback fine-tune cycle."""
    trades_used: int
    samples_built: int
    feedback_accuracy: float
    accepted: bool              # False when accuracy drop exceeded guard
    baseline_accuracy: float
    model_path: str
    trained_at: float


def _lgbm_params() -> dict:
    return {
        "n_estimators": 500,
        "learning_rate": 0.05,
        "max_depth": 6,
        "num_leaves": 31,
        "min_child_samples": 50,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "class_weight": "balanced",
        "n_jobs": -1,
        "random_state": 42,
        "verbose": -1,
    }


def train(
    symbols: list[str] | None = None,
    interval: str = "15m",
    days: int = 730,
    model_dir: str | Path = _DEFAULT_MODEL_DIR,
    download: bool = True,
    data_dir: str | Path = ".data",
) -> TrainResult:
    """Download (optional) + feature-engineer + train LightGBM model.

    Args:
        symbols: Pairs to include. Defaults to all 12 AlphaCota pairs.
        interval: Kline interval (default "15m").
        days: Historical days to use (default 730).
        model_dir: Where to save the trained model.
        download: If True, re-downloads data from Binance before training.
        data_dir: Directory for Parquet cache files.

    Returns:
        TrainResult with accuracy metrics and saved model path.
    """
    symbols = symbols or SYMBOLS
    model_dir = Path(model_dir)
    data_dir = Path(data_dir)
    model_dir.mkdir(parents=True, exist_ok=True)

    all_X: list[pd.DataFrame] = []
    all_y: list[pd.Series] = []

    for sym in symbols:
        if download:
            logger.info("train: downloading %s...", sym)
            df = download_pair(sym, interval, days, data_dir)
        else:
            df = load_pair(sym, interval, data_dir)

        if df.empty or len(df) < 200:
            logger.warning("train: skipping %s — insufficient data (%d rows)", sym, len(df))
            continue

        X, y = prepare_dataset(df)
        if len(X) < 100:
            logger.warning("train: skipping %s — too few clean rows (%d)", sym, len(X))
            continue

        all_X.append(X)
        all_y.append(y)
        logger.info("train: %s — %d samples, %d features", sym, len(X), X.shape[1])

    if not all_X:
        raise RuntimeError("train: no usable data across all symbols")

    X_all = pd.concat(all_X, ignore_index=True)
    y_all = pd.concat(all_y, ignore_index=True)

    # Encode labels: -1→0 (short), 0→1 (flat), 1→2 (long)
    le = LabelEncoder()
    y_enc = le.fit_transform(y_all)
    label_map = {int(enc): str(orig) for enc, orig in zip(le.transform(le.classes_), le.classes_)}
    # Map encoded ints back to readable names
    readable = {int(le.transform([-1])[0]): "short", int(le.transform([0])[0]): "flat", int(le.transform([1])[0]): "long"}

    logger.info("train: total dataset — %d samples, %d features, labels: %s",
                len(X_all), X_all.shape[1], dict(zip(*np.unique(y_all, return_counts=True))))

    # Time-series cross-validation (no shuffle — temporal integrity)
    tscv = TimeSeriesSplit(n_splits=5)
    fold_accs: list[float] = []

    for fold, (train_idx, val_idx) in enumerate(tscv.split(X_all)):
        clf_fold = LGBMClassifier(**_lgbm_params())
        clf_fold.fit(
            X_all.iloc[train_idx], y_enc[train_idx],
            eval_set=[(X_all.iloc[val_idx], y_enc[val_idx])],
        )
        acc = (clf_fold.predict(X_all.iloc[val_idx]) == y_enc[val_idx]).mean()
        fold_accs.append(acc)
        logger.info("train: fold %d accuracy = %.4f", fold + 1, acc)

    avg_acc = float(np.mean(fold_accs))

    # Train final model on all data
    clf = LGBMClassifier(**_lgbm_params())
    clf.fit(X_all, y_enc)

    y_pred = clf.predict(X_all)
    report = classification_report(y_enc, y_pred, target_names=["short", "flat", "long"])

    # Save model
    bot_model = BotModel(
        clf=clf,
        feature_names=list(X_all.columns),
        label_map=readable,
        trained_at=time.time(),
        symbols=symbols,
    )
    model_path = model_dir / _MODEL_FILE
    with open(model_path, "wb") as f:
        pickle.dump(bot_model, f)

    meta = {
        "symbols": symbols,
        "interval": interval,
        "days": days,
        "features": list(X_all.columns),
        "label_map": readable,
        "cv_accuracy": avg_acc,
        "candles_total": len(X_all),
        "trained_at": time.time(),
    }
    with open(model_dir / _META_FILE, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info("train: model saved to %s (cv_acc=%.4f)", model_path, avg_acc)

    return TrainResult(
        symbols=symbols,
        candles_total=len(X_all),
        features=X_all.shape[1],
        accuracy=round(avg_acc, 4),
        report=report,
        model_path=str(model_path),
        trained_at=time.time(),
    )


def load_model(model_dir: str | Path = _DEFAULT_MODEL_DIR) -> BotModel:
    """Load a previously trained BotModel from disk.

    Args:
        model_dir: Directory containing crypto_lgbm.pkl.

    Returns:
        BotModel ready for inference.

    Raises:
        FileNotFoundError: If model file does not exist.
    """
    path = Path(model_dir) / _MODEL_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"No trained model at {path}. Run train() first or call POST /api/crypto/ml/train."
        )
    with open(path, "rb") as f:
        return pickle.load(f)


def predict(model: BotModel, df_recent: pd.DataFrame) -> MLSignal:
    """Run inference on the most recent candles and return a directional signal.

    Args:
        model: Loaded BotModel.
        df_recent: DataFrame with at least 120 rows of OHLCV (most recent last).

    Returns:
        MLSignal with direction, confidence, and per-class probabilities.
    """
    symbol = df_recent["symbol"].iloc[-1] if "symbol" in df_recent.columns else "UNKNOWN"

    feat = build_features(df_recent)
    # Align features to training columns — fill missing with 0, drop extras
    for col in model.feature_names:
        if col not in feat.columns:
            feat[col] = 0.0
    feat = feat[model.feature_names]
    feat = feat.replace([float("inf"), float("-inf")], float("nan")).fillna(0.0)

    # Use last valid row
    last_row = feat.iloc[[-1]]
    proba = model.clf.predict_proba(last_row)[0]

    # Map class probabilities to long/flat/short
    classes = model.clf.classes_
    prob_map: dict[str, float] = {}
    for enc_cls, p in zip(classes, proba):
        name = model.label_map.get(int(enc_cls), "flat")
        prob_map[name] = float(p)

    prob_long = prob_map.get("long", 0.0)
    prob_flat = prob_map.get("flat", 0.0)
    prob_short = prob_map.get("short", 0.0)

    # Direction = highest probability class; confidence = that class's probability
    best = max(prob_map, key=prob_map.get)  # type: ignore[arg-type]
    confidence = prob_map[best]

    # Require minimum confidence gap over flat to avoid marginal calls
    if best == "long" and prob_long - prob_flat < 0.05:
        best, confidence = "flat", prob_flat
    elif best == "short" and prob_short - prob_flat < 0.05:
        best, confidence = "flat", prob_flat

    return MLSignal(
        symbol=symbol,
        direction=best,
        confidence=round(confidence, 4),
        prob_long=round(prob_long, 4),
        prob_flat=round(prob_flat, 4),
        prob_short=round(prob_short, 4),
        timestamp=time.time(),
    )


def get_confidence(
    symbol: str,
    interval: str = "15m",
    model_dir: str | Path = _DEFAULT_MODEL_DIR,
    candles_needed: int = 200,
) -> MLSignal:
    """Convenience: load model + fetch live candles + predict in one call.

    Args:
        symbol: e.g. "BTCUSDT"
        interval: Kline interval.
        model_dir: Directory containing the trained model.
        candles_needed: How many recent candles to fetch (default 200).

    Returns:
        MLSignal with current market confidence.
    """
    from core.crypto_data_collector import download_pair

    model = load_model(model_dir)
    df = download_pair(symbol, interval, days=candles_needed // 96 + 2)
    if df.empty:
        return MLSignal(symbol, "flat", 0.0, 0.0, 1.0, 0.0, time.time())

    return predict(model, df.tail(candles_needed))


def train_from_trades(
    conn: sqlite3.Connection,
    mode: str = "paper",
    model_dir: str | Path = _DEFAULT_MODEL_DIR,
    min_trades: int = 50,
    data_dir: str | Path = ".data",
    candles_per_trade: int = 200,
    max_accuracy_drop: float = 0.05,
) -> TradesFeedbackResult:
    """Fine-tune the model using real closed-trade outcomes as feedback labels.

    Pipeline:
        1. Load recent trades from the DB (via get_recent_trades).
        2. For each trade: load parquet OHLCV, slice to [entry-200 : entry].
        3. Extract features with build_features(); assign label from exit_reason:
               tp_hit      \u2192  1  (trade succeeded)
               sl_hit      \u2192 -1  (trade failed)
               signal_flip \u2192  0  (neutral exit)
        4. Train a secondary LightGBM on (X_feedback, y_feedback).
        5. Guard: compare feedback CV accuracy against baseline in meta JSON.
           If accuracy drop > max_accuracy_drop \u2192 reject, log warning, return.
        6. Accept: overwrite the model file with the updated estimator.

    Args:
        conn: Open sqlite3.Connection to the AlphaCota database.
        mode: \"paper\" or \"live\".
        model_dir: Directory where model artefacts are stored.
        min_trades: Minimum trades required before attempting (default 50).
        data_dir: Directory with OHLCV parquet cache files.
        candles_per_trade: Candles to extract per trade for features.
        max_accuracy_drop: Maximum tolerated accuracy degradation (5%).

    Returns:
        TradesFeedbackResult describing what happened.
    """
    from core.crypto_ledger import get_recent_trades

    model_dir = Path(model_dir)
    data_dir = Path(data_dir)
    now = time.time()

    # --- Load baseline accuracy from meta ----------------------------------
    meta_path = model_dir / _META_FILE
    baseline_accuracy = 0.0
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            baseline_accuracy = float(meta.get("cv_accuracy", 0.0))
        except Exception:
            pass

    # --- Load recent trades -------------------------------------------------
    trades = get_recent_trades(conn, mode, days=90, min_count=min_trades)
    if not trades:
        logger.info(
            "train_from_trades: not enough trades (%d < %d) \u2014 skipping",
            len(trades), min_trades,
        )
        return TradesFeedbackResult(
            trades_used=0,
            samples_built=0,
            feedback_accuracy=0.0,
            accepted=False,
            baseline_accuracy=baseline_accuracy,
            model_path=str(model_dir / _MODEL_FILE),
            trained_at=now,
        )

    logger.info("train_from_trades: processing %d trades", len(trades))

    # --- Map exit_reason to labels -----------------------------------------
    _reason_to_label: dict[str, int] = {
        "tp_hit":      1,
        "sl_hit":     -1,
        "signal_flip": 0,
    }

    all_X: list[pd.DataFrame] = []
    all_y: list[int] = []
    symbols_seen: set[str] = set()

    for trade in trades:
        symbol = trade["symbol"]
        entry_ts = trade["opened_at"]
        reason = trade["exit_reason"]
        label = _reason_to_label.get(reason, 0)

        try:
            df = load_pair(symbol, "15m", data_dir)
        except Exception as exc:
            logger.debug("train_from_trades: cannot load %s parquet: %s", symbol, exc)
            continue

        if df.empty or len(df) < candles_per_trade:
            continue

        # Slice to candles ending at or just before entry timestamp.
        if "open_time" in df.columns:
            df_ts = pd.to_datetime(df["open_time"], unit="ms", utc=True)
            mask = df_ts.values <= (entry_ts * 1_000)  # ms comparison
            idx = int(mask.sum())
        else:
            # Fallback: use positional index
            idx = len(df)

        start = max(0, idx - candles_per_trade)
        df_slice = df.iloc[start:idx].copy()

        if len(df_slice) < 50:
            continue

        try:
            feat = build_features(df_slice)
            feat = feat.replace([float("inf"), float("-inf")], float("nan")).fillna(0.0)
            last = feat.iloc[[-1]]
            if last.isnull().all(axis=None):
                continue
            all_X.append(last)
            all_y.append(label)
            symbols_seen.add(symbol)
        except Exception as exc:
            logger.debug("train_from_trades: feature build failed for %s: %s", symbol, exc)
            continue

    samples_built = len(all_X)
    logger.info("train_from_trades: built %d feature samples from %d trades", samples_built, len(trades))

    if samples_built < 10:
        logger.warning("train_from_trades: too few valid samples (%d) \u2014 aborting", samples_built)
        return TradesFeedbackResult(
            trades_used=len(trades),
            samples_built=samples_built,
            feedback_accuracy=0.0,
            accepted=False,
            baseline_accuracy=baseline_accuracy,
            model_path=str(model_dir / _MODEL_FILE),
            trained_at=now,
        )

    X_fb = pd.concat(all_X, ignore_index=True)
    y_fb = pd.Series(all_y, dtype=int)

    # Align columns to base model features if a model exists.
    base_model: BotModel | None = None
    try:
        base_model = load_model(model_dir)
        for col in base_model.feature_names:
            if col not in X_fb.columns:
                X_fb[col] = 0.0
        X_fb = X_fb[base_model.feature_names]
    except FileNotFoundError:
        pass

    # --- Encode labels ------------------------------------------------------
    le = LabelEncoder()
    le.fit([-1, 0, 1])
    y_enc = le.transform(y_fb.clip(lower=-1, upper=1))
    readable = {
        int(le.transform([-1])[0]): "short",
        int(le.transform([0])[0]):  "flat",
        int(le.transform([1])[0]):  "long",
    }

    # --- Cross-validate on feedback data ------------------------------------
    tscv = TimeSeriesSplit(n_splits=min(3, max(2, samples_built // 5)))
    fold_accs: list[float] = []
    for _, (tr_idx, val_idx) in enumerate(tscv.split(X_fb)):
        if len(val_idx) == 0:
            continue
        clf_cv = LGBMClassifier(**_lgbm_params())
        clf_cv.fit(X_fb.iloc[tr_idx], y_enc[tr_idx])
        acc = (clf_cv.predict(X_fb.iloc[val_idx]) == y_enc[val_idx]).mean()
        fold_accs.append(acc)

    feedback_accuracy = float(np.mean(fold_accs)) if fold_accs else 0.0
    logger.info(
        "train_from_trades: feedback CV accuracy=%.4f baseline=%.4f",
        feedback_accuracy, baseline_accuracy,
    )

    # --- Accuracy guard: reject if drop too large --------------------------
    if baseline_accuracy > 0 and (baseline_accuracy - feedback_accuracy) > max_accuracy_drop:
        logger.warning(
            "train_from_trades: accuracy drop %.4f exceeds threshold %.2f \u2014 rejecting update",
            baseline_accuracy - feedback_accuracy, max_accuracy_drop,
        )
        return TradesFeedbackResult(
            trades_used=len(trades),
            samples_built=samples_built,
            feedback_accuracy=feedback_accuracy,
            accepted=False,
            baseline_accuracy=baseline_accuracy,
            model_path=str(model_dir / _MODEL_FILE),
            trained_at=now,
        )

    # --- Train final feedback model on all samples -------------------------
    clf_fb = LGBMClassifier(**_lgbm_params())
    clf_fb.fit(X_fb, y_enc)

    # Persist updated model (replaces base if no base existed, else wraps it).
    feature_names = list(X_fb.columns)
    symbols_list = list(symbols_seen)
    if base_model is not None:
        feature_names = base_model.feature_names
        symbols_list = list(set(base_model.symbols) | symbols_seen)

    updated_model = BotModel(
        clf=clf_fb,
        feature_names=feature_names,
        label_map=readable,
        trained_at=now,
        symbols=symbols_list,
    )

    model_path = model_dir / _MODEL_FILE
    with open(model_path, "wb") as fh:
        pickle.dump(updated_model, fh)

    # Update meta with feedback run info.
    meta_update: dict = {
        "last_feedback_at": now,
        "feedback_accuracy": feedback_accuracy,
        "feedback_trades": len(trades),
        "feedback_samples": samples_built,
    }
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            meta.update(meta_update)
            meta_path.write_text(json.dumps(meta, indent=2))
        except Exception:
            pass
    else:
        meta_path.write_text(json.dumps(meta_update, indent=2))

    logger.info(
        "train_from_trades: model updated \u2014 trades=%d samples=%d feedback_acc=%.4f",
        len(trades), samples_built, feedback_accuracy,
    )
    return TradesFeedbackResult(
        trades_used=len(trades),
        samples_built=samples_built,
        feedback_accuracy=feedback_accuracy,
        accepted=True,
        baseline_accuracy=baseline_accuracy,
        model_path=str(model_path),
        trained_at=now,
    )
