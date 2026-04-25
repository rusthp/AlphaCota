"""
core/crypto_signal_engine.py — Pure signal generation combining TA + news.

Given OHLCV candles and a news sentiment score, produces a CryptoSignal with
direction ("long" / "short" / "flat"), confidence, entry, stop-loss, and
take-profit levels. No I/O — the caller supplies all external inputs.

Market regime detection:
    detect_market_regime(candles) -> "trending" | "ranging" | "volatile"
    ADX < 20 → ranging → no new positions opened (avoids sideways noise).
    Weights shift automatically: trending favours EMA/MACD; ranging favours RSI.

Multi-timeframe support:
    pass htf_candles (e.g. 4H) to suppress signals that contradict the
    higher-timeframe trend (EMA50/200 filter).

Adaptive risk:
    get_adaptive_multipliers(conn, mode, window) -> (sl_mult, tp_mult)
    Adjusts SL/TP multipliers based on recent win rate to avoid systematic
    stop-outs in adverse regimes and maximise profit in favourable ones.

Public API:
    calculate_adx(candles, period) -> float
    detect_market_regime(candles) -> "trending" | "ranging" | "volatile"
    compute_technical_signal(candles, order_book_imbalance) -> (direction, confidence)
    compute_htf_trend(candles) -> "bullish" | "bearish" | "neutral"
    calculate_atr(candles, period) -> float
    get_adaptive_multipliers(conn, mode, window) -> (sl_mult, tp_mult)
    generate_signal(symbol, candles, news_score, order_book_imbalance,
                    htf_candles) -> CryptoSignal
"""

from __future__ import annotations

import math
import sqlite3
import time
from datetime import date
from typing import TYPE_CHECKING

from core.crypto_chart_engine import calculate_ema, calculate_macd, calculate_rsi
from core.crypto_types import CryptoCandle, CryptoSignal

# Static weights — overridden dynamically by regime (see _regime_weights).
_WEIGHT_EMA = 0.4
_WEIGHT_MACD = 0.3
_WEIGHT_RSI = 0.2
_WEIGHT_OBI = 0.1

# Per-regime weight tables (EMA, MACD, RSI, OBI — must each sum to 1.0).
_REGIME_WEIGHTS: dict[str, tuple[float, float, float, float]] = {
    "trending":  (0.45, 0.35, 0.10, 0.10),  # follow the trend
    "ranging":   (0.20, 0.20, 0.45, 0.15),  # mean-reversion via RSI
    "volatile":  (0.30, 0.30, 0.25, 0.15),  # balanced — extra caution
}

# Weights for final (TA vs news) combination.
_WEIGHT_TECHNICAL = 0.7
_WEIGHT_NEWS = 0.3

# Thresholds.
_LONG_THRESHOLD = 0.6
_SHORT_THRESHOLD = -0.6
_MIN_SIGNAL_CONFIDENCE = 0.65

# ADX thresholds for regime classification.
_ADX_TRENDING = 25.0    # above → trending
_ADX_RANGING  = 20.0    # below → ranging (no trade)

# Risk sizing constants.
_ATR_PERIOD = 14
_ATR_SL_MULT = 1.5
_ATR_TP_MULT = 3.0   # 2:1 reward/risk

# Adaptive multiplier clamp bounds (win-rate feedback).
_SL_MULT_MIN = 1.0
_SL_MULT_MAX = 3.0
_TP_MULT_MIN = 2.0
_TP_MULT_MAX = 5.0


# ---------------------------------------------------------------------------
# Adaptive SL/TP multipliers (performance feedback)
# ---------------------------------------------------------------------------


def get_adaptive_multipliers(
    conn: sqlite3.Connection,
    mode: str,
    window: int = 30,
) -> tuple[float, float]:
    """Compute SL/TP multipliers adapted to recent trading performance.

    Queries the last `window` closed trades to calculate win rate and adjusts
    the ATR multipliers accordingly:
        - Win rate < 40 % → widen SL (× 1.25) and tighten TP (× 0.90)
          to survive noisy regimes without being stopped out prematurely.
        - Win rate > 60 % → tighten SL (× 0.90) and widen TP (× 1.20)
          to maximise capture in strong trending markets.
        - 40 % ≤ win rate ≤ 60 % → use base defaults.

    Multipliers are clamped to [SL: 1.0–3.0] × [TP: 2.0–5.0] so that
    no adjustment can produce invalid SL/TP structures.

    Requires at least 10 closed trades to activate; otherwise returns
    the static defaults (_ATR_SL_MULT, _ATR_TP_MULT).

    Args:
        conn: Open sqlite3.Connection to the AlphaCota database.
        mode: "paper" or "live".
        window: Number of most-recent trades to sample (default 30).

    Returns:
        (sl_mult, tp_mult) — floats ready to pass to generate_signal().
    """
    from core.logger import logger

    sl_mult = _ATR_SL_MULT
    tp_mult = _ATR_TP_MULT

    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) AS wins
            FROM (
                SELECT realized_pnl
                  FROM crypto_trades
                 WHERE mode = ?
                 ORDER BY closed_at DESC
                 LIMIT ?
            )
            """,
            (mode, window),
        ).fetchone()

        total = int(row[0]) if row and row[0] else 0
        wins  = int(row[1]) if row and row[1] else 0

        if total < 10:
            logger.debug(
                "get_adaptive_multipliers: only %d trades — using defaults", total
            )
            return (sl_mult, tp_mult)

        win_rate = wins / total
        logger.debug(
            "get_adaptive_multipliers: mode=%s window=%d win_rate=%.2f (%d/%d)",
            mode, window, win_rate, wins, total,
        )

        if win_rate < 0.40:
            # Losing regime — give trades more room, accept smaller wins.
            sl_mult *= 1.25
            tp_mult *= 0.90
        elif win_rate > 0.60:
            # Winning regime — ride winners longer, risk less per trade.
            sl_mult *= 0.90
            tp_mult *= 1.20

        sl_mult = round(max(_SL_MULT_MIN, min(_SL_MULT_MAX, sl_mult)), 3)
        tp_mult = round(max(_TP_MULT_MIN, min(_TP_MULT_MAX, tp_mult)), 3)

    except sqlite3.Error as exc:
        logger.warning("get_adaptive_multipliers: db error — %s", exc)

    return (sl_mult, tp_mult)


# ---------------------------------------------------------------------------
# ADX — trend strength (pure)
# ---------------------------------------------------------------------------


def calculate_adx(candles: list[CryptoCandle], period: int = 14) -> float:
    """Wilder's Average Directional Index (ADX).

    ADX measures trend *strength* (not direction) in [0, 100].
    Values above 25 indicate a trending market; below 20 indicate sideways.

    Args:
        candles: Ordered oldest → newest. Need at least (2 × period + 1) candles.
        period: Wilder smoothing period (default 14).

    Returns:
        Latest ADX value in [0, 100], or 0.0 if insufficient data.
    """
    n = len(candles)
    if n < 2 * period + 1 or period < 1:
        return 0.0

    plus_dm: list[float] = []
    minus_dm: list[float] = []
    trs: list[float] = []

    for i in range(1, n):
        h, lo, prev_c = candles[i].high, candles[i].low, candles[i - 1].close
        prev_h, prev_l = candles[i - 1].high, candles[i - 1].low

        tr = max(h - lo, abs(h - prev_c), abs(lo - prev_c))
        trs.append(tr)

        up   = h - prev_h
        down = prev_l - lo
        plus_dm.append(up   if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)

    def _wilder(values: list[float], p: int) -> list[float]:
        out = [sum(values[:p])]
        for v in values[p:]:
            out.append(out[-1] - out[-1] / p + v)
        return out

    atr14   = _wilder(trs, period)
    plus14  = _wilder(plus_dm, period)
    minus14 = _wilder(minus_dm, period)

    dx_vals: list[float] = []
    for a, p, m in zip(atr14, plus14, minus14):
        if a <= 0:
            dx_vals.append(0.0)
            continue
        pdi = 100 * p / a
        mdi = 100 * m / a
        denom = pdi + mdi
        dx_vals.append(100 * abs(pdi - mdi) / denom if denom > 0 else 0.0)

    if len(dx_vals) < period:
        return 0.0

    adx = sum(dx_vals[:period]) / period
    for dx in dx_vals[period:]:
        adx = (adx * (period - 1) + dx) / period
    return round(float(adx), 4)


# ---------------------------------------------------------------------------
# Market regime detection (pure)
# ---------------------------------------------------------------------------


def detect_market_regime(candles: list[CryptoCandle]) -> str:
    """Classify the current market regime using ADX and ATR-based volatility.

    Regimes:
        "trending"  — ADX >= 25: strong directional move, follow the trend.
        "volatile"  — ADX in [20, 25) but ATR%  above 2-period average × 1.5:
                      high but choppy volatility, trade with caution.
        "ranging"   — ADX < 20: sideways, high noise-to-signal ratio.

    The caller should skip new entries when regime is "ranging".

    Args:
        candles: Ordered oldest → newest. At least 30 required.

    Returns:
        "trending", "volatile", or "ranging".
    """
    if len(candles) < 30:
        return "ranging"

    adx = calculate_adx(candles)

    if adx >= _ADX_TRENDING:
        return "trending"

    if adx >= _ADX_RANGING:
        # Borderline — check if volatility is notably elevated.
        closes = [c.close for c in candles[-20:]]
        atr_now = calculate_atr(candles[-20:])
        avg_close = sum(closes) / len(closes)
        atr_pct = atr_now / avg_close if avg_close > 0 else 0.0
        return "volatile" if atr_pct > 0.012 else "ranging"

    return "ranging"


# ---------------------------------------------------------------------------
# ATR (pure)
# ---------------------------------------------------------------------------


def calculate_atr(candles: list[CryptoCandle], period: int = 14) -> float:
    """Wilder's Average True Range over the last `period` candles.

    TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
    ATR is the Wilder-smoothed mean of TR (alpha = 1/period), seeded with
    the SMA of the first `period` TR values.

    Args:
        candles: Ordered oldest → newest. Need at least (period + 1) candles.
        period: Wilder lookback (default 14).

    Returns:
        The latest ATR value. Returns 0.0 if insufficient data.
    """
    n = len(candles)
    if n < period + 1 or period < 1:
        return 0.0

    trs: list[float] = []
    for i in range(1, n):
        h = candles[i].high
        low = candles[i].low
        prev_close = candles[i - 1].close
        tr = max(h - low, abs(h - prev_close), abs(low - prev_close))
        trs.append(tr)

    if len(trs) < period:
        return 0.0

    atr = sum(trs[:period]) / period
    for i in range(period, len(trs)):
        atr = (atr * (period - 1) + trs[i]) / period
    return float(atr)


# ---------------------------------------------------------------------------
# Technical composite (pure)
# ---------------------------------------------------------------------------


def compute_technical_signal(
    candles: list[CryptoCandle],
    order_book_imbalance: float = 0.0,
    regime: str = "trending",
) -> tuple[str, float]:
    """Combine EMA cross, MACD histogram, RSI, and order-book imbalance.

    Components (each in [-1, 1]):
        EMA  : +1 if EMA20 > EMA50, -1 if below, 0 if equal / warmup.
               Adjustment when RSI is overbought/oversold (see RSI component).
        MACD : sign of the most recent MACD histogram value.
        RSI  : -0.5 if RSI > 70 (overbought, bearish tilt), +0.5 if < 30
               (oversold, bullish tilt), 0 otherwise.
        OBI  : order-book imbalance passed through untouched (already in [-1, 1]).

    The weighted sum is normalised to [-1, 1] and returned as
    (direction, confidence), where direction is "long" / "short" / "flat"
    and confidence is |composite| — a flat direction is emitted when the
    signal magnitude is below 0.25 (noise floor).

    Args:
        candles: Ordered oldest → newest. Need at least 50 candles for the
                 slow EMA to warm up. Fewer returns ("flat", 0.0).
        order_book_imbalance: Book imbalance in [-1, 1].

    Returns:
        (direction, confidence) with confidence in [0, 1].
    """
    if len(candles) < 50:
        return ("flat", 0.0)

    closes = [c.close for c in candles]

    # ---- EMA component ----
    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)
    ema_component = 0.0
    if not math.isnan(ema20[-1]) and not math.isnan(ema50[-1]):
        if ema20[-1] > ema50[-1]:
            ema_component = 1.0
        elif ema20[-1] < ema50[-1]:
            ema_component = -1.0

    # ---- MACD component ----
    _, _, hist = calculate_macd(closes)
    macd_component = 0.0
    if hist and not math.isnan(hist[-1]):
        if hist[-1] > 0:
            macd_component = 1.0
        elif hist[-1] < 0:
            macd_component = -1.0

    # ---- RSI component (contrarian near extremes) ----
    rsi_vals = calculate_rsi(closes, 14)
    rsi_component = 0.0
    if rsi_vals and not math.isnan(rsi_vals[-1]):
        last_rsi = rsi_vals[-1]
        if last_rsi >= 70:
            rsi_component = -0.5
        elif last_rsi <= 30:
            rsi_component = 0.5

    # ---- OBI component (clamped) ----
    obi_component = max(-1.0, min(1.0, float(order_book_imbalance)))

    w_ema, w_macd, w_rsi, w_obi = _REGIME_WEIGHTS.get(regime, _REGIME_WEIGHTS["trending"])
    composite = (
        w_ema  * ema_component
        + w_macd * macd_component
        + w_rsi  * rsi_component
        + w_obi  * obi_component
    )
    # Composite already in [-1, 1] given the weights sum to 1 and components clamped.
    composite = max(-1.0, min(1.0, composite))

    # Noise floor — treat tiny composites as flat.
    if abs(composite) < 0.25:
        return ("flat", abs(composite))

    direction = "long" if composite > 0 else "short"
    return (direction, round(abs(composite), 4))


# ---------------------------------------------------------------------------
# Higher-timeframe trend filter (pure)
# ---------------------------------------------------------------------------


def compute_htf_trend(candles: list[CryptoCandle]) -> str:
    """Determine higher-timeframe trend direction using EMA50 and EMA200.

    Both EMAs must agree for a definitive trend reading. When the fast EMA
    (50) is above the slow EMA (200) the trend is bullish; when below it is
    bearish. If data is insufficient or EMAs are equal the trend is neutral,
    meaning no restriction is applied to lower-timeframe signals.

    Args:
        candles: Higher-timeframe candles (e.g. 4H), oldest → newest.
                 At least 200 candles required for EMA200 to be meaningful.

    Returns:
        "bullish", "bearish", or "neutral".
    """
    if len(candles) < 60:
        return "neutral"

    closes = [c.close for c in candles]
    ema50 = calculate_ema(closes, 50)
    ema200 = calculate_ema(closes, 200) if len(closes) >= 200 else None

    last_ema50 = ema50[-1] if ema50 and not math.isnan(ema50[-1]) else None

    if ema200 is not None:
        last_ema200 = ema200[-1] if not math.isnan(ema200[-1]) else None
        if last_ema50 is not None and last_ema200 is not None:
            if last_ema50 > last_ema200 * 1.001:
                return "bullish"
            if last_ema50 < last_ema200 * 0.999:
                return "bearish"
        return "neutral"

    # Fallback when fewer than 200 candles: use price vs EMA50
    last_price = closes[-1]
    if last_ema50 is not None:
        if last_price > last_ema50 * 1.001:
            return "bullish"
        if last_price < last_ema50 * 0.999:
            return "bearish"
    return "neutral"


# ---------------------------------------------------------------------------
# Unified signal (pure)
# ---------------------------------------------------------------------------


def generate_signal(
    symbol: str,
    candles: list[CryptoCandle],
    news_score: float,
    order_book_imbalance: float = 0.0,
    sl_mult: float | None = None,
    tp_mult: float | None = None,
    htf_candles: list[CryptoCandle] | None = None,
) -> CryptoSignal:
    """Produce a CryptoSignal combining technicals and news sentiment.

    Pipeline:
        1. compute_technical_signal -> (tech_dir, tech_conf)
        2. Convert both sides to signed magnitudes in [-1, 1].
        3. combined = 0.7 * tech_signed + 0.3 * clamped_news_score
        4. Direction = long if combined >  0.6
                       short if combined < -0.6
                       flat  otherwise
        5. ATR(14) drives SL/TP: SL = entry - 1.5*ATR (long) or +1.5*ATR (short);
                                 TP = entry + 3.0*ATR (long) or -3.0*ATR (short).
        6. Only emit non-flat signals with confidence >= 0.65; otherwise flat.

    Args:
        symbol: Exchange symbol (e.g. "BTCUSDT").
        candles: Ordered oldest → newest, length >= 50 ideal.
        news_score: Aggregate news sentiment in [-1, 1].
        order_book_imbalance: Book imbalance in [-1, 1].

    Returns:
        CryptoSignal — flat when data is thin or confidence is below threshold.
    """
    now = time.time()
    entry_price = candles[-1].close if candles else 0.0

    if len(candles) < 50 or entry_price <= 0.0:
        return CryptoSignal(
            symbol=symbol,
            direction="flat",
            confidence=0.0,
            reason="insufficient_data",
            entry_price=entry_price,
            stop_loss=0.0,
            take_profit=0.0,
            timestamp=now,
        )

    # Regime detection — ranging markets skip new entries entirely.
    regime = detect_market_regime(candles)
    if regime == "ranging":
        return CryptoSignal(
            symbol=symbol,
            direction="flat",
            confidence=0.0,
            reason="ranging_market_adx_too_low",
            entry_price=entry_price,
            stop_loss=0.0,
            take_profit=0.0,
            timestamp=now,
        )

    tech_dir, tech_conf = compute_technical_signal(candles, order_book_imbalance, regime)
    tech_signed = 0.0
    if tech_dir == "long":
        tech_signed = tech_conf
    elif tech_dir == "short":
        tech_signed = -tech_conf

    clamped_news = max(-1.0, min(1.0, float(news_score)))
    combined = _WEIGHT_TECHNICAL * tech_signed + _WEIGHT_NEWS * clamped_news
    combined = max(-1.0, min(1.0, combined))
    confidence = round(abs(combined), 4)

    if combined > _LONG_THRESHOLD:
        direction = "long"
    elif combined < _SHORT_THRESHOLD:
        direction = "short"
    else:
        direction = "flat"

    # Multi-timeframe filter: suppress signals that contradict HTF trend.
    htf_trend = "neutral"
    if htf_candles:
        htf_trend = compute_htf_trend(htf_candles)
        if htf_trend == "bullish" and direction == "short":
            direction = "flat"
        elif htf_trend == "bearish" and direction == "long":
            direction = "flat"

    if direction == "flat" or confidence < _MIN_SIGNAL_CONFIDENCE:
        return CryptoSignal(
            symbol=symbol,
            direction="flat",
            confidence=confidence,
            reason=(
                f"regime={regime} below_threshold combined={combined:.3f} "
                f"tech={tech_signed:.3f} news={clamped_news:.3f}"
                + (f" htf={htf_trend}" if htf_trend != "neutral" else "")
            ),
            entry_price=entry_price,
            stop_loss=0.0,
            take_profit=0.0,
            timestamp=now,
        )

    atr = calculate_atr(candles, _ATR_PERIOD)
    if atr <= 0.0:
        return CryptoSignal(
            symbol=symbol,
            direction="flat",
            confidence=confidence,
            reason="atr_unavailable",
            entry_price=entry_price,
            stop_loss=0.0,
            take_profit=0.0,
            timestamp=now,
        )

    _sl = sl_mult if sl_mult is not None else _ATR_SL_MULT
    _tp = tp_mult if tp_mult is not None else _ATR_TP_MULT
    if direction == "long":
        stop_loss = entry_price - _sl * atr
        take_profit = entry_price + _tp * atr
    else:
        stop_loss = entry_price + _sl * atr
        take_profit = entry_price - _tp * atr

    # Guard against negative / absurd SL on low-priced pairs.
    if stop_loss <= 0.0 or take_profit <= 0.0:
        return CryptoSignal(
            symbol=symbol,
            direction="flat",
            confidence=confidence,
            reason="invalid_sl_tp_levels",
            entry_price=entry_price,
            stop_loss=0.0,
            take_profit=0.0,
            timestamp=now,
        )

    reason = (
        f"regime={regime} tech_dir={tech_dir} tech_conf={tech_conf:.3f} "
        f"news={clamped_news:.3f} combined={combined:.3f} atr={atr:.6f}"
        + (f" htf={htf_trend}" if htf_trend != "neutral" else "")
    )
    return CryptoSignal(
        symbol=symbol,
        direction=direction,
        confidence=confidence,
        reason=reason,
        entry_price=round(entry_price, 8),
        stop_loss=round(stop_loss, 8),
        take_profit=round(take_profit, 8),
        timestamp=now,
    )
