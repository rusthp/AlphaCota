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

from core.crypto_chart_engine import calculate_ema, calculate_macd, calculate_rsi
from core.crypto_types import CryptoCandle, CryptoSignal

# Static weights — overridden dynamically by regime (see _regime_weights).
_WEIGHT_EMA = 0.4
_WEIGHT_MACD = 0.3
_WEIGHT_RSI = 0.2
_WEIGHT_OBI = 0.1

# Per-regime weight tables (EMA, MACD, RSI, OBI, VWAP, Volume — must each sum to 1.0).
_REGIME_WEIGHTS: dict[str, tuple[float, float, float, float, float, float]] = {
    "trending":  (0.35, 0.25, 0.10, 0.10, 0.10, 0.10),  # follow the trend
    "ranging":   (0.15, 0.15, 0.35, 0.15, 0.10, 0.10),  # mean-reversion via RSI
    "volatile":  (0.25, 0.25, 0.20, 0.10, 0.10, 0.10),  # balanced — extra caution
}

# Weights for final combination.
# Technical (0.75): EMA+MACD agreement (composite=0.80) → combined=0.60; needs on-chain
#                   or news confirmation to clear 0.63, preventing noise entries.
# On-chain (0.15): funding rate, OI change, L/S ratio — structural market state.
# News (0.10):     sentiment boost/drag; intentionally lowest weight (most noisy).
_WEIGHT_TECHNICAL = 0.75
_WEIGHT_ONCHAIN   = 0.15
_WEIGHT_NEWS      = 0.10

# Thresholds.
# 0.63: EMA+MACD alone give 0.75×0.80=0.60; on-chain confirmation (score≥0.20)
#       or strongly bullish news (score≥0.30) tips it over. Single indicator never clears.
_LONG_THRESHOLD = 0.63
_SHORT_THRESHOLD = -0.63
# Must equal _LONG_THRESHOLD — setting higher creates a dead zone where
# direction="long/short" but confidence check immediately returns flat.
_MIN_SIGNAL_CONFIDENCE = 0.63

# ADX thresholds for regime classification.
_ADX_TRENDING = 25.0    # above → trending
_ADX_RANGING  = 12.0    # below → ranging (no trade); was 15 — lowered to allow entry in moderate ranging

# On-chain override: if |onchain_agg| exceeds this threshold the ranging
# block is bypassed.  Confidence threshold is raised to _ONCHAIN_RANGING_THRESHOLD
# to compensate for the weaker directional regime.
_ONCHAIN_RANGING_OVERRIDE = 0.45
_ONCHAIN_RANGING_THRESHOLD = 0.70

# Ranging mean-reversion threshold: RSI < 30 or RSI > 70 allows a mean-reversion
# entry in ranging markets, but with a higher confidence bar and reduced position size.
_RANGING_MR_RSI_LOW = 30.0
_RANGING_MR_RSI_HIGH = 70.0
_RANGING_MR_THRESHOLD = 0.70   # higher than trending threshold (0.63)
_RANGING_MR_SIZE_MULT = 0.7    # 30% smaller positions in ranging mean-reversion

# Volatile regime size multiplier: reduce position size to limit drawdown in choppy markets.
_VOLATILE_SIZE_MULT = 0.6

# BTC global regime filter: continuous modifier based on EMA50/EMA200 spread strength.
# btc_strength ∈ [-1, 1] (normalised ±5% EMA spread cap).
# Aligned signal:  modifier = 1.0 + strength × _BTC_ALIGN_SCALE   → max ×1.18
# Opposing signal: modifier = 1.0 - strength × _BTC_OPPOSE_SCALE  → min ×0.75
# Not applied to BTCUSDT itself to avoid circular self-filtering.
_BTC_ALIGN_SCALE  = 0.18    # aligned boost scale  (strength=1 → ×1.18)
_BTC_OPPOSE_SCALE = 0.25    # opposing dampen scale (strength=1 → ×0.75)
_BTC_STRENGTH_CAP = 0.05    # EMA spread % cap before normalisation

# Regime persistence — minimum consecutive candles before a regime change is confirmed.
# Volatile needs more evidence to enter (avoid reacting to brief spikes) and
# more evidence to exit (volatile conditions unwind slowly).
_REGIME_PERSIST_ENTER: dict[str, int] = {
    "trending": 2,
    "ranging":  2,
    "volatile": 3,
    "unknown":  1,
}
_REGIME_PERSIST_EXIT_VOLATILE = 5   # candles of non-volatile needed to leave volatile

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
    return round(adx, 4)


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
# Regime persistence — hysteresis filter to prevent rapid regime flipping
# ---------------------------------------------------------------------------

class _RegimeState:
    """Per-symbol mutable state for regime hysteresis."""
    __slots__ = ("current", "candidate", "candidate_count")

    def __init__(self) -> None:
        self.current: str = "unknown"
        self.candidate: str = "unknown"
        self.candidate_count: int = 0


_regime_states: dict[str, _RegimeState] = {}


def get_confirmed_regime(symbol: str, raw_regime: str) -> str:
    """Apply hysteresis to raw regime detection and return the confirmed regime.

    A regime change is only accepted after it persists for N consecutive
    candles (see _REGIME_PERSIST_ENTER).  Exiting "volatile" requires even
    more evidence (_REGIME_PERSIST_EXIT_VOLATILE) because volatile conditions
    tend to unwind gradually rather than snap back instantly.

    Args:
        symbol:     Trading symbol — state is tracked per symbol.
        raw_regime: Output of detect_market_regime() for the current candle.

    Returns:
        The confirmed regime string.  Starts as "unknown" until enough
        candles accumulate to confirm the first regime.
    """
    state = _regime_states.setdefault(symbol, _RegimeState())

    if raw_regime == state.candidate:
        state.candidate_count += 1
    else:
        state.candidate = raw_regime
        state.candidate_count = 1

    if state.candidate == state.current:
        return state.current

    if state.current == "volatile":
        threshold = _REGIME_PERSIST_EXIT_VOLATILE
    else:
        threshold = _REGIME_PERSIST_ENTER.get(state.candidate, 2)

    if state.candidate_count >= threshold:
        state.current = state.candidate
        state.candidate_count = 0

    return state.current


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
    return atr


# ---------------------------------------------------------------------------
# VWAP and volume spike helpers (pure)
# ---------------------------------------------------------------------------


def calculate_vwap(candles: list[CryptoCandle], period: int = 50) -> float:
    """Rolling VWAP over the last `period` candles.

    Typical price = (high + low + close) / 3.
    Returns 0.0 when volume sums to zero (e.g. synthetic test data).
    """
    recent = candles[-period:] if len(candles) >= period else candles
    tp_vol = sum((c.high + c.low + c.close) / 3.0 * c.volume for c in recent)
    vol_sum = sum(c.volume for c in recent)
    return tp_vol / vol_sum if vol_sum > 0 else 0.0


def compute_volume_spike(
    candles: list[CryptoCandle],
    period: int = 20,
    multiplier: float = 1.5,
) -> float:
    """Detect a volume spike on the last candle relative to the prior `period`.

    Returns +1.0 if current candle is bullish (close > open) with a spike,
    -1.0 if bearish with a spike, 0.0 if no spike or insufficient data.
    Spikes without a clear body direction return 0.0 (doji candles).
    """
    if len(candles) < period + 1:
        return 0.0
    avg_vol = sum(c.volume for c in candles[-(period + 1):-1]) / period
    if avg_vol <= 0:
        return 0.0
    last = candles[-1]
    if last.volume <= avg_vol * multiplier:
        return 0.0
    body = last.close - last.open
    if abs(body) < (last.high - last.low) * 0.1:
        return 0.0  # doji — spike with no direction
    return 1.0 if body > 0 else -1.0


# ---------------------------------------------------------------------------
# Technical composite (pure)
# ---------------------------------------------------------------------------


def compute_technical_signal(
    candles: list[CryptoCandle],
    order_book_imbalance: float = 0.0,
    regime: str = "trending",
) -> tuple[str, float]:
    """Combine EMA cross, MACD histogram, RSI, OBI, VWAP, and volume spike.

    Components (each in [-1, 1]):
        EMA    : +1 if EMA20 > EMA50, -1 if below, 0 if equal / warmup.
        MACD   : sign of the most recent MACD histogram value.
        RSI    : -0.5 if RSI > 70 (overbought), +0.5 if < 30 (oversold), 0 otherwise.
        OBI    : order-book imbalance in [-1, 1].
        VWAP   : +1 if close > VWAP(50), -1 if below — institutional price anchor.
        Volume : +1/-1 if a volume spike (>1.5× avg) with bullish/bearish body; else 0.

    Regime weights (sum to 1.0 per regime):
        trending : EMA 0.35, MACD 0.25, RSI 0.10, OBI 0.10, VWAP 0.10, Vol 0.10
        ranging  : EMA 0.15, MACD 0.15, RSI 0.35, OBI 0.15, VWAP 0.10, Vol 0.10
        volatile : EMA 0.25, MACD 0.25, RSI 0.20, OBI 0.10, VWAP 0.10, Vol 0.10

    Returns:
        (direction, confidence) — flat when composite < 0.25 noise floor.
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
    obi_component = max(-1.0, min(1.0, order_book_imbalance))

    # ---- VWAP component ----
    vwap = calculate_vwap(candles, period=50)
    last_close = candles[-1].close
    vwap_component = 0.0
    if vwap > 0:
        if last_close > vwap * 1.0005:
            vwap_component = 1.0
        elif last_close < vwap * 0.9995:
            vwap_component = -1.0

    # ---- Volume spike component ----
    vol_component = compute_volume_spike(candles, period=20, multiplier=1.5)

    w_ema, w_macd, w_rsi, w_obi, w_vwap, w_vol = _REGIME_WEIGHTS.get(
        regime, _REGIME_WEIGHTS["trending"]
    )
    composite = (
        w_ema  * ema_component
        + w_macd * macd_component
        + w_rsi  * rsi_component
        + w_obi  * obi_component
        + w_vwap * vwap_component
        + w_vol  * vol_component
    )
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


def compute_btc_strength(candles: list[CryptoCandle]) -> float:
    """Return a continuous BTC trend strength score in [-1, 1].

    Uses the EMA50/EMA200 spread as a proxy for trend intensity:
        strength = (ema50 - ema200) / ema200  (capped at ±_BTC_STRENGTH_CAP)
        normalised to [-1, 1]

    Positive → BTC bullish; negative → bearish; 0.0 → neutral/insufficient data.
    """
    if len(candles) < 60:
        return 0.0
    closes = [c.close for c in candles]
    ema50 = calculate_ema(closes, 50)
    last_ema50 = ema50[-1] if ema50 and not math.isnan(ema50[-1]) else None
    if last_ema50 is None:
        return 0.0
    if len(closes) >= 200:
        ema200 = calculate_ema(closes, 200)
        last_ema200 = ema200[-1] if ema200 and not math.isnan(ema200[-1]) else None
    else:
        last_ema200 = None
    reference = last_ema200 if last_ema200 and last_ema200 > 0 else (closes[-1] if closes[-1] > 0 else None)
    if reference is None:
        return 0.0
    raw_spread = (last_ema50 - reference) / reference
    clamped = max(-_BTC_STRENGTH_CAP, min(_BTC_STRENGTH_CAP, raw_spread))
    return round(clamped / _BTC_STRENGTH_CAP, 4)


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
    onchain_score: float = 0.0,
    btc_strength: float = 0.0,
) -> CryptoSignal:
    """Produce a CryptoSignal combining technicals, on-chain signals, and news.

    Pipeline:
        1. compute_technical_signal -> (tech_dir, tech_conf)
        2. Convert to signed magnitude in [-1, 1].
        3. combined = 0.75 * tech_signed + 0.15 * onchain_score + 0.10 * news_score
        4. BTC global regime modifier: amplify combined when 15m aligns with
           BTC 4H trend (×1.12), attenuate when opposing (×0.82). No-op for BTCUSDT.
        5. Ranging mean-reversion: instead of hard block, allow entry only at
           RSI extremes (< 30 or > 70) with raised threshold (0.70) and reduced size.
        6. Direction = long  if combined >  threshold
                       short if combined < -threshold
                       flat  otherwise
        7. Multi-timeframe filter: suppress signals contradicting 4H HTF trend.
        8. ATR(14) drives SL/TP levels.
        9. Only emit non-flat signals with confidence >= 0.63; otherwise flat.

    Args:
        symbol: Exchange symbol (e.g. "BTCUSDT").
        candles: Ordered oldest → newest, length >= 50 ideal.
        news_score: Aggregate news sentiment in [-1, 1].
        order_book_imbalance: Book imbalance in [-1, 1].
        onchain_score: Weighted on-chain composite (funding + OI + L/S) in [-1, 1].
        btc_trend: Pre-computed BTC 4H trend ("bullish"/"bearish"/"neutral").
                   Passed by the loop; "neutral" disables the BTC modifier.

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

    # --- Regime detection (with hysteresis persistence filter) ---
    regime = get_confirmed_regime(symbol, detect_market_regime(candles))
    onchain_override_active = (
        regime == "ranging"
        and abs(onchain_score) >= _ONCHAIN_RANGING_OVERRIDE
    )

    # Ranging mean-reversion gate: instead of an absolute block, allow entries
    # only at RSI extremes (< 30 oversold / > 70 overbought) with a higher
    # confidence threshold and reduced position size.
    ranging_mean_reversion = False
    if regime == "ranging" and not onchain_override_active:
        rsi_vals = calculate_rsi([c.close for c in candles], 14)
        last_rsi = rsi_vals[-1] if rsi_vals and not math.isnan(rsi_vals[-1]) else 50.0
        if _RANGING_MR_RSI_LOW <= last_rsi <= _RANGING_MR_RSI_HIGH:
            return CryptoSignal(
                symbol=symbol,
                direction="flat",
                confidence=0.0,
                reason=f"ranging_market_rsi={last_rsi:.1f}_not_extreme",
                entry_price=entry_price,
                stop_loss=0.0,
                take_profit=0.0,
                timestamp=now,
                regime=regime,
            )
        ranging_mean_reversion = True  # RSI at extreme → proceed with higher threshold

    tech_dir, tech_conf = compute_technical_signal(candles, order_book_imbalance, regime)
    tech_signed = 0.0
    if tech_dir == "long":
        tech_signed = tech_conf
    elif tech_dir == "short":
        tech_signed = -tech_conf

    clamped_news = max(-1.0, min(1.0, news_score))
    clamped_onchain = max(-1.0, min(1.0, onchain_score))
    combined = (
        _WEIGHT_TECHNICAL * tech_signed
        + _WEIGHT_ONCHAIN * clamped_onchain
        + _WEIGHT_NEWS * clamped_news
    )
    combined = max(-1.0, min(1.0, combined))

    # --- BTC global regime modifier (continuous strength score) ---
    # btc_strength ∈ [-1, 1]: positive = BTC bullish, negative = bearish.
    # effective_strength > 0 means the 15m signal aligns with BTC direction.
    # Aligned:  modifier = 1 + effective × 0.18  → max ×1.18
    # Opposing: modifier = 1 + effective × 0.25  → min ×0.75
    btc_factor_applied = 1.0
    if symbol != "BTCUSDT" and btc_strength != 0.0:
        if combined > 0:    # long-leaning: positive BTC = aligned
            effective = btc_strength
        elif combined < 0:  # short-leaning: negative BTC = aligned
            effective = -btc_strength
        else:
            effective = 0.0
        if effective > 0:
            btc_factor_applied = 1.0 + effective * _BTC_ALIGN_SCALE
        elif effective < 0:
            btc_factor_applied = 1.0 + effective * _BTC_OPPOSE_SCALE
        combined = max(-1.0, min(1.0, combined * btc_factor_applied))

    confidence = round(abs(combined), 4)

    # Effective threshold: raised for ranging mean-reversion and on-chain override.
    if onchain_override_active:
        long_thresh = _ONCHAIN_RANGING_THRESHOLD
    elif ranging_mean_reversion:
        long_thresh = _RANGING_MR_THRESHOLD
    else:
        long_thresh = _LONG_THRESHOLD
    short_thresh = -long_thresh

    if combined > long_thresh:
        direction = "long"
    elif combined < short_thresh:
        direction = "short"
    else:
        direction = "flat"

    # --- Multi-timeframe filter: suppress signals contradicting 4H HTF trend ---
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
                + (f" btc_str={btc_strength:.2f}(×{btc_factor_applied:.3f})" if btc_factor_applied != 1.0 else "")
                + (f" htf={htf_trend}" if htf_trend != "neutral" else "")
            ),
            entry_price=entry_price,
            stop_loss=0.0,
            take_profit=0.0,
            timestamp=now,
            regime=regime,
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
            regime=regime,
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
            regime=regime,
        )

    # Regime-aware position size multiplier:
    #   volatile        → 0.6 (choppy market, limit exposure)
    #   ranging MR      → 0.7 (counter-trend, smaller size)
    #   trending/other  → 1.0
    if regime == "volatile":
        regime_size_mult = _VOLATILE_SIZE_MULT
    elif ranging_mean_reversion:
        regime_size_mult = _RANGING_MR_SIZE_MULT
    else:
        regime_size_mult = 1.0

    reason = (
        f"regime={regime} tech_dir={tech_dir} tech_conf={tech_conf:.3f} "
        f"news={clamped_news:.3f} combined={combined:.3f} atr={atr:.6f}"
        + (f" btc_str={btc_strength:.2f}(×{btc_factor_applied:.3f})" if btc_factor_applied != 1.0 else "")
        + (f" htf={htf_trend}" if htf_trend != "neutral" else "")
        + (f" size_mult={regime_size_mult}" if regime_size_mult != 1.0 else "")
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
        regime=regime,
        regime_size_mult=regime_size_mult,
    )


def decompose_signal(
    symbol: str,
    candles: list[CryptoCandle],
    news_score: float = 0.0,
    order_book_imbalance: float = 0.0,
    htf_candles: list[CryptoCandle] | None = None,
    onchain_score: float = 0.0,
    onchain_detail: dict | None = None,
    btc_strength: float = 0.0,
) -> dict:
    """Return full signal decomposition without emitting a CryptoSignal.

    Used by the /api/crypto/signal/decomposition endpoint to populate the
    Confiança IA dashboard tab.  Mirrors generate_signal internals exactly
    so every number shown in the UI matches what the live loop uses.

    Returns:
        dict with keys: symbol, price, regime, adx, tech, onchain, news_score,
        combined, threshold, htf_trend, decision, would_enter, skip_reason.
    """
    entry_price = candles[-1].close if candles else 0.0

    _flat_tech = {"direction": "flat", "confidence": 0.0, "signed": 0.0, "weight_contribution": 0.0}
    _flat_ml = {"available": False, "direction": "flat", "confidence": 0.0, "prob_long": 0.0, "prob_flat": 1.0, "prob_short": 0.0}
    _flat_vwap = {"value": 0.0, "price_vs_vwap": 0.0, "above": False}
    _flat_vol = {"detected": False, "direction": "none"}

    if len(candles) < 50 or entry_price <= 0.0:
        return {
            "symbol": symbol, "price": entry_price, "regime": "unknown",
            "adx": 0.0, "tech": _flat_tech, "ml": _flat_ml,
            "onchain": onchain_detail or {"available": False}, "news_score": 0.0,
            "news_weight_contribution": 0.0,
            "combined": 0.0, "threshold": _LONG_THRESHOLD,
            "htf_trend": "neutral", "decision": "flat",
            "would_enter": False, "skip_reason": "insufficient_data",
            "vwap": _flat_vwap, "volume_spike": _flat_vol,
        }

    adx = calculate_adx(candles, 14)
    regime = get_confirmed_regime(symbol, detect_market_regime(candles))
    onchain_override_active = (
        regime == "ranging"
        and abs(onchain_score) >= _ONCHAIN_RANGING_OVERRIDE
    )

    ranging_mean_reversion = False
    if regime == "ranging" and not onchain_override_active:
        rsi_vals = calculate_rsi([c.close for c in candles], 14)
        last_rsi = rsi_vals[-1] if rsi_vals and not math.isnan(rsi_vals[-1]) else 50.0
        if _RANGING_MR_RSI_LOW <= last_rsi <= _RANGING_MR_RSI_HIGH:
            return {
                "symbol": symbol, "price": round(entry_price, 8), "regime": regime,
                "adx": round(adx, 2), "tech": _flat_tech, "ml": _flat_ml,
                "onchain": onchain_detail or {"available": False},
                "news_score": round(news_score, 4),
                "news_weight_contribution": round(_WEIGHT_NEWS * max(-1.0, min(1.0, news_score)), 4),
                "combined": 0.0, "threshold": _LONG_THRESHOLD,
                "htf_trend": "neutral", "decision": "flat",
                "would_enter": False, "skip_reason": f"ranging_market_rsi={last_rsi:.1f}_not_extreme",
                "vwap": _flat_vwap, "volume_spike": _flat_vol,
                "btc_strength": btc_strength, "btc_factor_applied": 1.0,
                "ranging_mean_reversion": False, "regime_size_mult": 1.0,
            }
        ranging_mean_reversion = True

    tech_dir, tech_conf = compute_technical_signal(candles, order_book_imbalance, regime)
    tech_signed = tech_conf if tech_dir == "long" else (-tech_conf if tech_dir == "short" else 0.0)

    vwap = calculate_vwap(candles, period=50)
    last_close = candles[-1].close
    vol_spike = compute_volume_spike(candles, period=20, multiplier=1.5)

    clamped_news = max(-1.0, min(1.0, news_score))
    clamped_onchain = max(-1.0, min(1.0, onchain_score))
    combined = (
        _WEIGHT_TECHNICAL * tech_signed
        + _WEIGHT_ONCHAIN * clamped_onchain
        + _WEIGHT_NEWS * clamped_news
    )
    combined = max(-1.0, min(1.0, combined))

    btc_factor_applied = 1.0
    if symbol != "BTCUSDT" and btc_strength != 0.0:
        if combined > 0:
            effective = btc_strength
        elif combined < 0:
            effective = -btc_strength
        else:
            effective = 0.0
        if effective > 0:
            btc_factor_applied = 1.0 + effective * _BTC_ALIGN_SCALE
        elif effective < 0:
            btc_factor_applied = 1.0 + effective * _BTC_OPPOSE_SCALE
        combined = max(-1.0, min(1.0, combined * btc_factor_applied))

    if onchain_override_active:
        threshold = _ONCHAIN_RANGING_THRESHOLD
    elif ranging_mean_reversion:
        threshold = _RANGING_MR_THRESHOLD
    else:
        threshold = _LONG_THRESHOLD

    if regime == "volatile":
        regime_size_mult = _VOLATILE_SIZE_MULT
    elif ranging_mean_reversion:
        regime_size_mult = _RANGING_MR_SIZE_MULT
    else:
        regime_size_mult = 1.0

    if combined > threshold:
        decision = "long"
    elif combined < -threshold:
        decision = "short"
    else:
        decision = "flat"

    htf_trend = "neutral"
    if htf_candles:
        htf_trend = compute_htf_trend(htf_candles)
        if htf_trend == "bullish" and decision == "short":
            decision = "flat"
        elif htf_trend == "bearish" and decision == "long":
            decision = "flat"

    skip_reason = None if decision != "flat" else "below_threshold"

    return {
        "symbol": symbol,
        "price": round(entry_price, 8),
        "regime": regime,
        "adx": round(adx, 2),
        "tech": {
            "direction": tech_dir,
            "confidence": round(tech_conf, 4),
            "signed": round(tech_signed, 4),
            "weight_contribution": round(_WEIGHT_TECHNICAL * tech_signed, 4),
        },
        "onchain": onchain_detail or {
            "aggregate": round(clamped_onchain, 4),
            "weight_contribution": round(_WEIGHT_ONCHAIN * clamped_onchain, 4),
        },
        "news_score": round(clamped_news, 4),
        "news_weight_contribution": round(_WEIGHT_NEWS * clamped_news, 4),
        "combined": round(combined, 4),
        "threshold": threshold,
        "htf_trend": htf_trend,
        "decision": decision,
        "would_enter": decision != "flat",
        "skip_reason": skip_reason,
        "btc_strength": round(btc_strength, 4),
        "btc_factor_applied": round(btc_factor_applied, 4),
        "ranging_mean_reversion": ranging_mean_reversion,
        "regime_size_mult": regime_size_mult,
        "vwap": {
            "value": round(vwap, 8),
            "price_vs_vwap": round((last_close - vwap) / vwap * 100, 3) if vwap > 0 else 0.0,
            "above": last_close > vwap,
        },
        "volume_spike": {
            "detected": vol_spike != 0.0,
            "direction": "long" if vol_spike > 0 else ("short" if vol_spike < 0 else "none"),
        },
    }
