"""
core/crypto_indicators.py — Pure technical-indicator math for the crypto system.

These functions are deliberately dependency-free (stdlib only) so they can be
imported by signal engines, backtests, and chart renderers alike without
dragging a plotting stack into headless contexts.

Public API:
    calculate_ema(values, period) -> list[float]
    calculate_rsi(closes, period) -> list[float]
    calculate_macd(closes, fast, slow, signal) -> (macd, signal, histogram)
    calculate_atr(highs, lows, closes, period) -> list[float]
    calculate_bollinger(closes, period, std_dev) -> (upper, mid, lower)
    calculate_stochastic(highs, lows, closes, k, d) -> (pct_k, pct_d)
    calculate_williams_r(highs, lows, closes, period) -> list[float]
    calculate_cci(highs, lows, closes, period) -> list[float]
    calculate_adx(highs, lows, closes, period) -> (adx, di_plus, di_minus)
    calculate_supertrend(highs, lows, closes, period, multiplier) -> (supertrend, direction)
"""

from __future__ import annotations

import math


def calculate_ema(values: list[float], period: int) -> list[float]:
    """Exponential moving average, same-length output.

    The first (period - 1) entries are NaN. The value at index (period - 1) is
    seeded with the simple moving average of the first `period` values, and
    subsequent values use the standard EMA recurrence:

        ema[i] = alpha * values[i] + (1 - alpha) * ema[i - 1]
        alpha  = 2 / (period + 1)

    Args:
        values: Input series (e.g. closes).
        period: EMA window. Must be >= 1.

    Returns:
        List of the same length as `values`, with NaN for warmup positions.
    """
    n = len(values)
    if period < 1 or n == 0:
        return [float("nan")] * n
    if n < period:
        return [float("nan")] * n

    out: list[float] = [float("nan")] * n
    sma = sum(values[:period]) / period
    out[period - 1] = sma
    alpha = 2.0 / (period + 1)
    for i in range(period, n):
        out[i] = alpha * values[i] + (1.0 - alpha) * out[i - 1]
    return out


def calculate_rsi(closes: list[float], period: int = 14) -> list[float]:
    """Wilder's RSI, same-length output.

    Uses Wilder's smoothing (alpha = 1/period, NOT the EMA alpha). The first
    `period` entries are NaN. The value at index `period` is seeded with the
    simple average of the first `period` gains/losses, and subsequent values
    use Wilder's recurrence:

        avg_gain[i] = (avg_gain[i-1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i-1] * (period - 1) + loss[i]) / period
        rs          = avg_gain / avg_loss
        rsi         = 100 - 100 / (1 + rs)

    Args:
        closes: Closing-price series.
        period: Wilder lookback (default 14).

    Returns:
        List of same length as `closes`, with NaN for warmup positions.
    """
    n = len(closes)
    if period < 1 or n == 0:
        return [float("nan")] * n
    if n <= period:
        return [float("nan")] * n

    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        delta = closes[i] - closes[i - 1]
        if delta >= 0:
            gains[i] = delta
        else:
            losses[i] = -delta

    out: list[float] = [float("nan")] * n

    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period

    if avg_loss == 0.0:
        out[period] = 100.0 if avg_gain > 0 else 50.0
    else:
        rs = avg_gain / avg_loss
        out[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0.0:
            out[i] = 100.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def calculate_macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[float], list[float], list[float]]:
    """MACD indicator: (macd_line, signal_line, histogram).

    All three returned series are the same length as `closes`. Warmup values
    are NaN. The signal-line EMA is computed on the MACD line but skips the
    NaN warmup region by resetting the SMA seed at the first valid index.

    Args:
        closes: Closing-price series.
        fast: Fast EMA period (default 12).
        slow: Slow EMA period (default 26).
        signal: Signal EMA period applied to MACD line (default 9).

    Returns:
        Tuple of (macd_line, signal_line, histogram). Histogram = MACD - signal.
    """
    n = len(closes)
    if n == 0:
        return [], [], []

    ema_fast = calculate_ema(closes, fast)
    ema_slow = calculate_ema(closes, slow)

    macd_line: list[float] = []
    for f, s in zip(ema_fast, ema_slow):
        if math.isnan(f) or math.isnan(s):
            macd_line.append(float("nan"))
        else:
            macd_line.append(f - s)

    first_valid = -1
    for i, v in enumerate(macd_line):
        if not math.isnan(v):
            first_valid = i
            break

    signal_line: list[float] = [float("nan")] * n
    histogram: list[float] = [float("nan")] * n

    if first_valid >= 0 and n - first_valid >= signal:
        tail = macd_line[first_valid:]
        signal_tail = calculate_ema(tail, signal)
        for idx, sig_val in enumerate(signal_tail):
            pos = first_valid + idx
            signal_line[pos] = sig_val
            if not math.isnan(sig_val) and not math.isnan(macd_line[pos]):
                histogram[pos] = macd_line[pos] - sig_val

    return macd_line, signal_line, histogram


def calculate_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float]:
    """Average True Range using Wilder's smoothing.

    True range = max(H-L, |H-C_prev|, |L-C_prev|).
    First ATR value is the simple average of the first `period` TRs.

    Args:
        highs, lows, closes: OHLCV series (same length).
        period: Lookback window (default 14).

    Returns:
        List same length as inputs; NaN for warmup positions.
    """
    n = len(closes)
    if n == 0 or period < 1:
        return [float("nan")] * n

    trs: list[float] = [float("nan")]
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        trs.append(max(hl, hc, lc))

    out: list[float] = [float("nan")] * n
    if n <= period:
        return out

    seed = sum(trs[1 : period + 1]) / period
    out[period] = seed
    for i in range(period + 1, n):
        out[i] = (out[i - 1] * (period - 1) + trs[i]) / period
    return out


def calculate_bollinger(
    closes: list[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[list[float], list[float], list[float]]:
    """Bollinger Bands: (upper, mid, lower).

    Mid = SMA(period). Upper/lower = SMA ± std_dev * rolling_std.

    Args:
        closes: Closing-price series.
        period: SMA window (default 20).
        std_dev: Number of standard deviations (default 2.0).

    Returns:
        Tuple of (upper, mid, lower), each same length as `closes`.
    """
    n = len(closes)
    if n == 0 or period < 1:
        nan = [float("nan")] * n
        return nan, nan, nan

    upper = [float("nan")] * n
    mid = [float("nan")] * n
    lower = [float("nan")] * n

    for i in range(period - 1, n):
        window = closes[i - period + 1 : i + 1]
        sma = sum(window) / period
        variance = sum((v - sma) ** 2 for v in window) / period
        sigma = math.sqrt(variance)
        mid[i] = sma
        upper[i] = sma + std_dev * sigma
        lower[i] = sma - std_dev * sigma

    return upper, mid, lower


def calculate_stochastic(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[list[float], list[float]]:
    """Stochastic Oscillator: (%K, %D).

    %K = 100 * (close - lowest_low) / (highest_high - lowest_low) over k_period.
    %D = SMA(d_period) of %K (not an EMA).

    Args:
        highs, lows, closes: Price series (same length).
        k_period: Fast window (default 14).
        d_period: Slow smoothing window (default 3).

    Returns:
        Tuple of (%K, %D), each same length as inputs.
    """
    n = len(closes)
    if n == 0:
        return [float("nan")] * n, [float("nan")] * n

    pct_k: list[float] = [float("nan")] * n
    for i in range(k_period - 1, n):
        hh = max(highs[i - k_period + 1 : i + 1])
        ll = min(lows[i - k_period + 1 : i + 1])
        denom = hh - ll
        if denom == 0.0:
            pct_k[i] = 50.0
        else:
            pct_k[i] = 100.0 * (closes[i] - ll) / denom

    pct_d: list[float] = [float("nan")] * n
    for i in range(k_period - 1 + d_period - 1, n):
        window = [pct_k[j] for j in range(i - d_period + 1, i + 1) if not math.isnan(pct_k[j])]
        if len(window) == d_period:
            pct_d[i] = sum(window) / d_period

    return pct_k, pct_d


def calculate_williams_r(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float]:
    """Williams %R oscillator.

    %R = -100 * (highest_high - close) / (highest_high - lowest_low)
    Range: -100 (oversold) to 0 (overbought). Oversold < -80, overbought > -20.

    Args:
        highs, lows, closes: Price series (same length).
        period: Lookback window (default 14).

    Returns:
        List same length as inputs; NaN for warmup.
    """
    n = len(closes)
    if n == 0 or period < 1:
        return [float("nan")] * n

    out: list[float] = [float("nan")] * n
    for i in range(period - 1, n):
        hh = max(highs[i - period + 1 : i + 1])
        ll = min(lows[i - period + 1 : i + 1])
        denom = hh - ll
        if denom == 0.0:
            out[i] = -50.0
        else:
            out[i] = -100.0 * (hh - closes[i]) / denom
    return out


def calculate_cci(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 20,
) -> list[float]:
    """Commodity Channel Index.

    CCI = (typical_price - SMA_tp) / (0.015 * mean_deviation)
    Typical price = (H + L + C) / 3.
    Overbought > 100, oversold < -100.

    Args:
        highs, lows, closes: Price series (same length).
        period: Lookback window (default 20).

    Returns:
        List same length as inputs; NaN for warmup.
    """
    n = len(closes)
    if n == 0 or period < 1:
        return [float("nan")] * n

    tp = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(n)]
    out: list[float] = [float("nan")] * n

    for i in range(period - 1, n):
        window = tp[i - period + 1 : i + 1]
        sma = sum(window) / period
        mean_dev = sum(abs(v - sma) for v in window) / period
        if mean_dev == 0.0:
            out[i] = 0.0
        else:
            out[i] = (tp[i] - sma) / (0.015 * mean_dev)
    return out


def calculate_adx(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> tuple[list[float], list[float], list[float]]:
    """ADX / DI+ / DI- using Wilder's smoothing.

    Returns (adx, di_plus, di_minus). ADX > 25 signals a strong trend.
    DI+ > DI- indicates bullish trend; DI- > DI+ indicates bearish.

    Args:
        highs, lows, closes: Price series (same length).
        period: Wilder smoothing window (default 14).

    Returns:
        Tuple of (adx, di_plus, di_minus), each same length as inputs.
    """
    n = len(closes)
    nan_list = [float("nan")] * n
    if n <= period * 2 or period < 1:
        return nan_list, nan_list, nan_list

    atr_vals = calculate_atr(highs, lows, closes, period)

    plus_dm: list[float] = [0.0] * n
    minus_dm: list[float] = [0.0] * n
    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move

    # Wilder-smooth the DM series
    sm_plus = [float("nan")] * n
    sm_minus = [float("nan")] * n
    if n > period:
        sm_plus[period] = sum(plus_dm[1 : period + 1])
        sm_minus[period] = sum(minus_dm[1 : period + 1])
        for i in range(period + 1, n):
            sm_plus[i] = sm_plus[i - 1] - sm_plus[i - 1] / period + plus_dm[i]
            sm_minus[i] = sm_minus[i - 1] - sm_minus[i - 1] / period + minus_dm[i]

    di_plus: list[float] = [float("nan")] * n
    di_minus: list[float] = [float("nan")] * n
    for i in range(period, n):
        atr_i = atr_vals[i]
        if math.isnan(atr_i) or atr_i == 0.0:
            continue
        if not math.isnan(sm_plus[i]):
            di_plus[i] = 100.0 * sm_plus[i] / atr_i
        if not math.isnan(sm_minus[i]):
            di_minus[i] = 100.0 * sm_minus[i] / atr_i

    dx: list[float] = [float("nan")] * n
    for i in range(period, n):
        if math.isnan(di_plus[i]) or math.isnan(di_minus[i]):
            continue
        denom = di_plus[i] + di_minus[i]
        if denom == 0.0:
            dx[i] = 0.0
        else:
            dx[i] = 100.0 * abs(di_plus[i] - di_minus[i]) / denom

    adx: list[float] = [float("nan")] * n
    first_dx = next((i for i in range(n) if not math.isnan(dx[i])), -1)
    if first_dx >= 0 and n - first_dx >= period:
        valid_dx = [v for v in dx[first_dx:] if not math.isnan(v)]
        if len(valid_dx) >= period:
            seed_idx = first_dx + period - 1
            adx[seed_idx] = sum(dx[first_dx : first_dx + period]) / period
            for i in range(seed_idx + 1, n):
                if not math.isnan(dx[i]) and not math.isnan(adx[i - 1]):
                    adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

    return adx, di_plus, di_minus


def calculate_supertrend(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 10,
    multiplier: float = 3.0,
) -> tuple[list[float], list[int]]:
    """Supertrend indicator.

    Uses ATR-based dynamic support/resistance. Direction: 1 = bullish (price
    above supertrend), -1 = bearish (price below supertrend). A change in
    direction is a buy (1) or sell (-1) signal.

    Args:
        highs, lows, closes: Price series (same length).
        period: ATR period (default 10).
        multiplier: ATR multiplier for band width (default 3.0).

    Returns:
        Tuple of (supertrend_values, direction_list). Direction is 1 or -1;
        NaN supertrend and 0 direction during warmup.
    """
    n = len(closes)
    atr_vals = calculate_atr(highs, lows, closes, period)

    supertrend: list[float] = [float("nan")] * n
    direction: list[int] = [0] * n

    upper_band: list[float] = [float("nan")] * n
    lower_band: list[float] = [float("nan")] * n

    for i in range(n):
        if math.isnan(atr_vals[i]):
            continue
        hl2 = (highs[i] + lows[i]) / 2.0
        upper_band[i] = hl2 + multiplier * atr_vals[i]
        lower_band[i] = hl2 - multiplier * atr_vals[i]

    for i in range(period, n):
        if math.isnan(upper_band[i]) or math.isnan(lower_band[i]):
            continue

        if i == period:
            supertrend[i] = upper_band[i]
            direction[i] = -1
            continue

        prev_st = supertrend[i - 1]
        prev_dir = direction[i - 1]

        if math.isnan(prev_st):
            supertrend[i] = upper_band[i]
            direction[i] = -1
            continue

        # Adjust bands based on previous values
        if lower_band[i] < lower_band[i - 1] or math.isnan(lower_band[i - 1]):
            adj_lower = lower_band[i]
        else:
            adj_lower = lower_band[i - 1]

        if upper_band[i] > upper_band[i - 1] or math.isnan(upper_band[i - 1]):
            adj_upper = upper_band[i]
        else:
            adj_upper = upper_band[i - 1]

        if prev_dir == -1:
            if closes[i] <= adj_lower:
                direction[i] = 1
                supertrend[i] = adj_upper
            else:
                direction[i] = -1
                supertrend[i] = adj_lower
        else:
            if closes[i] >= adj_upper:
                direction[i] = -1
                supertrend[i] = adj_lower
            else:
                direction[i] = 1
                supertrend[i] = adj_upper

    return supertrend, direction
