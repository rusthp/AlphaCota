"""
core/crypto_ml_features.py — Feature engineering and label generation for ML model.

Converts raw OHLCV DataFrames into ML-ready feature matrices with forward-looking
labels. Features = all 9+ technical indicators + price-derived. Labels = direction
of the profitable trade in the next N candles (long=1, short=-1, flat=0).

Public API:
    build_features(df) -> pd.DataFrame
    generate_labels(df, lookahead, sl_pct, tp_pct) -> pd.Series
    prepare_dataset(df) -> tuple[pd.DataFrame, pd.Series]
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from core.crypto_indicators import (
    calculate_ema,
    calculate_rsi,
    calculate_macd,
    calculate_atr,
    calculate_bollinger,
    calculate_stochastic,
    calculate_williams_r,
    calculate_cci,
    calculate_adx,
    calculate_supertrend,
)


def _series(vals: list[float]) -> pd.Series:
    return pd.Series(vals, dtype=float)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all technical indicator features for every row in df.

    Args:
        df: DataFrame with columns: open, high, low, close, volume.
            Must have at least 120 rows for all indicators to have valid values.

    Returns:
        DataFrame with one feature column per indicator. Rows with NaN are
        included — the caller should drop them after merging with labels.
    """
    closes = df["close"].tolist()
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    volumes = df["volume"].tolist()
    n = len(df)

    feat = pd.DataFrame(index=df.index)

    # --- Price-derived ---
    feat["returns_1"] = df["close"].pct_change(1)
    feat["returns_3"] = df["close"].pct_change(3)
    feat["returns_5"] = df["close"].pct_change(5)
    feat["returns_10"] = df["close"].pct_change(10)

    # High-low range as % of close
    feat["hl_pct"] = (df["high"] - df["low"]) / df["close"]

    # --- RSI ---
    rsi = _series(calculate_rsi(closes, 14))
    feat["rsi"] = rsi.values
    feat["rsi_7"] = _series(calculate_rsi(closes, 7)).values
    feat["rsi_oversold"] = (rsi < 30).astype(float).values
    feat["rsi_overbought"] = (rsi > 70).astype(float).values

    # --- EMA ---
    ema9 = _series(calculate_ema(closes, 9))
    ema21 = _series(calculate_ema(closes, 21))
    ema50 = _series(calculate_ema(closes, 50))
    ema200 = _series(calculate_ema(closes, 200))
    close_s = df["close"]

    feat["ema9_dist"] = (close_s.values - ema9.values) / close_s.values
    feat["ema21_dist"] = (close_s.values - ema21.values) / close_s.values
    feat["ema50_dist"] = (close_s.values - ema50.values) / close_s.values
    feat["ema200_dist"] = (close_s.values - ema200.values) / close_s.values
    feat["ema9_21_cross"] = (ema9.values > ema21.values).astype(float)
    feat["ema21_50_cross"] = (ema21.values > ema50.values).astype(float)
    feat["triple_ema_bull"] = ((ema9.values > ema21.values) & (ema21.values > ema50.values)).astype(float)
    feat["triple_ema_bear"] = ((ema9.values < ema21.values) & (ema21.values < ema50.values)).astype(float)

    # --- MACD ---
    macd_line, sig_line, hist = calculate_macd(closes, 12, 26, 9)
    feat["macd_hist"] = _series(hist).values
    feat["macd_positive"] = (_series(hist) > 0).astype(float).values
    feat["macd_cross_up"] = (
        (_series(hist) > 0) & (_series(hist).shift(1) <= 0)
    ).astype(float).values
    feat["macd_cross_dn"] = (
        (_series(hist) < 0) & (_series(hist).shift(1) >= 0)
    ).astype(float).values

    # --- ATR ---
    atr_series = _series(calculate_atr(highs, lows, closes, 14))
    feat["atr_pct"] = (atr_series.values / close_s.values)
    feat["atr_14"] = atr_series.values

    # --- Bollinger Bands ---
    upper, mid, lower = calculate_bollinger(closes, 20, 2.0)
    upper_s = _series(upper)
    lower_s = _series(lower)
    band_width = upper_s - lower_s
    feat["bb_pct_b"] = ((close_s.values - lower_s.values) / (band_width.values + 1e-9))
    feat["bb_width_pct"] = (band_width.values / close_s.values)
    feat["bb_above_upper"] = (close_s.values >= upper_s.values).astype(float)
    feat["bb_below_lower"] = (close_s.values <= lower_s.values).astype(float)

    # --- Stochastic ---
    pct_k, pct_d = calculate_stochastic(highs, lows, closes, 14, 3)
    feat["stoch_k"] = _series(pct_k).values
    feat["stoch_d"] = _series(pct_d).values
    feat["stoch_oversold"] = (_series(pct_k) < 20).astype(float).values
    feat["stoch_overbought"] = (_series(pct_k) > 80).astype(float).values
    feat["stoch_cross_up"] = (
        (_series(pct_k) > _series(pct_d)) & (_series(pct_k).shift(1) <= _series(pct_d).shift(1))
    ).astype(float).values

    # --- Williams %R ---
    wr = _series(calculate_williams_r(highs, lows, closes, 14))
    feat["williams_r"] = wr.values
    feat["wr_oversold"] = (wr < -80).astype(float).values
    feat["wr_overbought"] = (wr > -20).astype(float).values

    # --- CCI ---
    cci = _series(calculate_cci(highs, lows, closes, 20))
    feat["cci"] = cci.values
    feat["cci_bull"] = (cci > 100).astype(float).values
    feat["cci_bear"] = (cci < -100).astype(float).values

    # --- ADX ---
    adx_vals, di_plus, di_minus = calculate_adx(highs, lows, closes, 14)
    adx_s = _series(adx_vals)
    feat["adx"] = adx_s.values
    feat["di_plus"] = _series(di_plus).values
    feat["di_minus"] = _series(di_minus).values
    feat["adx_strong"] = (adx_s > 25).astype(float).values
    feat["di_bull"] = (_series(di_plus) > _series(di_minus)).astype(float).values

    # --- Supertrend ---
    st_vals, st_dirs = calculate_supertrend(highs, lows, closes, 10, 3.0)
    feat["supertrend_dir"] = _series(st_dirs).values
    feat["supertrend_bull"] = (_series(st_dirs) == -1).astype(float).values
    feat["supertrend_flip"] = (
        _series(st_dirs) != _series(st_dirs).shift(1)
    ).astype(float).values

    # --- Volume ---
    vol_s = df["volume"]
    vol_avg20 = vol_s.rolling(20).mean()
    feat["rel_volume"] = (vol_s / (vol_avg20 + 1e-9)).values
    feat["vol_spike"] = (feat["rel_volume"] > 2.0).astype(float)

    # --- Time features (cyclical) ---
    if hasattr(df.index, "hour") or "open_time" in df.columns:
        times = pd.to_datetime(df["open_time"]) if "open_time" in df.columns else df.index
        hour = times.dt.hour
        dow = times.dt.dayofweek
        feat["hour_sin"] = np.sin(2 * np.pi * hour / 24).values
        feat["hour_cos"] = np.cos(2 * np.pi * hour / 24).values
        feat["dow_sin"] = np.sin(2 * np.pi * dow / 7).values
        feat["dow_cos"] = np.cos(2 * np.pi * dow / 7).values

    return feat


def generate_labels(
    df: pd.DataFrame,
    lookahead: int = 8,
    sl_pct: float = 0.006,
    tp_pct: float = 0.006,
) -> pd.Series:
    """Generate forward-looking trade labels for each candle.

    For each candle i, simulates a long and short trade over the next
    `lookahead` candles. Whichever hits its target first determines the label.
    If neither hits, the label is 0 (flat).

    SL and TP are intentionally symmetric (both default 0.6%) so label
    generation does not artificially favour long or short trades. An
    asymmetric sl_pct < tp_pct would bias the model toward LONG because
    the TP bar is always easier to reach than the SL bar.

    Args:
        df: OHLCV DataFrame.
        lookahead: Max candles to look forward (default 8 = 2h on 15m data).
        sl_pct: Stop-loss threshold as fraction (default 0.006 = 0.6%).
        tp_pct: Take-profit threshold as fraction (default 0.006 = 0.6%).

    Returns:
        pd.Series of int: 1=long profitable, -1=short profitable, 0=flat/neutral.
    """
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    n = len(closes)
    labels = np.zeros(n, dtype=int)

    for i in range(n - lookahead):
        entry = closes[i]
        long_tp = entry * (1 + tp_pct)
        long_sl = entry * (1 - sl_pct)
        short_tp = entry * (1 - tp_pct)
        short_sl = entry * (1 + sl_pct)

        long_hit = short_hit = False
        for j in range(i + 1, min(i + lookahead + 1, n)):
            h, lo = highs[j], lows[j]
            if not long_hit and h >= long_tp:
                long_hit = True
            if not short_hit and lo <= short_tp:
                short_hit = True
            if long_hit and not short_hit:
                labels[i] = 1
                break
            if short_hit and not long_hit:
                labels[i] = -1
                break
            # Both hit on same candle or SL hit first → flat
            if (h >= long_tp and lo <= short_tp):
                break
            if lo <= long_sl:
                long_hit = False
                break
            if h >= short_sl:
                short_hit = False
                break

    return pd.Series(labels, index=df.index, name="label")


def prepare_dataset(
    df: pd.DataFrame,
    lookahead: int = 8,
    sl_pct: float = 0.006,
    tp_pct: float = 0.006,
) -> tuple[pd.DataFrame, pd.Series]:
    """Build feature matrix X and label vector y, dropping NaN rows.

    Args:
        df: OHLCV DataFrame from load_pair() or download_pair().
        lookahead: Candles to look forward for labeling.
        sl_pct: Stop-loss fraction.
        tp_pct: Take-profit fraction.

    Returns:
        (X, y) tuple — both aligned, NaN rows removed, ready for model.fit(X, y).
    """
    feat = build_features(df)
    labels = generate_labels(df, lookahead, sl_pct, tp_pct)

    combined = feat.copy()
    combined["label"] = labels

    combined = combined.replace([float("inf"), float("-inf")], float("nan"))
    combined = combined.dropna()

    X = combined.drop(columns=["label"])
    y = combined["label"]

    return X, y
