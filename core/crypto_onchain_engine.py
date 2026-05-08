"""
core/crypto_onchain_engine.py — Binance Futures on-chain signals.

Four signals from public endpoints (no API key required):

    1. Funding Rate       — contrarian: extreme positive → shorts favoured,
                            extreme negative → longs favoured.
    2. Open Interest      — directional: rising OI = conviction; falling = caution.
    3. Long/Short Ratio   — contrarian: too many longs → potential unwind;
                            too many shorts → potential squeeze.
    4. Taker Buy/Sell     — directional: aggressive buyer flow = bullish momentum.
                            Non-linear: extreme aggression slightly degraded
                            (very extreme taker often precedes short-term reversal).

All endpoints use fapi.binance.com (Futures REST, public tier).
Results are cached per symbol with a 15-minute TTL so the loop can call
fetch_onchain_signals() every iteration without hitting rate limits.

Public API:
    OnChainSignal — dataclass with all four components and aggregate score.
    fetch_onchain_signals(symbol) -> OnChainSignal
    score_onchain(signal) -> float          # aggregate in [-1, 1]
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from core.logger import logger

_FAPI_BASE = "https://fapi.binance.com"
_TIMEOUT = 8.0
_CACHE_TTL = 900.0  # 15 minutes — matches 15m candle interval

# Normalisation denominators (empirically chosen):
#   Funding rate: ±0.03% is "extreme" in most markets; max at ±0.10%.
#   OI change:    ±2% per 15m is a strong move.
#   L/S ratio:    centred at 1.0; ±0.8 covers most regimes (0.2 – 1.8).
#   Taker ratio:  0.5 = neutral; ±0.1 from neutral is a strong lean.
_FUNDING_NORM   = 0.0003   # 0.03%
_OI_NORM        = 0.02     # 2%
_LS_NORM        = 1.2      # ratio deviation from 1.0; raised from 0.8 — crypto stays crowded-long in bull trends
_TAKER_NORM     = 0.10     # deviation from 0.5 (neutral)
_TAKER_EXTREME  = 0.8      # |score| above which aggression is slightly degraded

# Aggregate on-chain score weights (must sum to 1.0).
_W_FUNDING = 0.35
_W_OI      = 0.30
_W_TAKER   = 0.20
_W_LS      = 0.15

_cache: dict[str, tuple[float, "OnChainSignal"]] = {}


@dataclass
class OnChainSignal:
    symbol: str
    funding_rate: float      # raw value (e.g. 0.0001)
    funding_score: float     # in [-1, 1], contrarian
    oi_change_pct: float     # % change in open interest
    oi_score: float          # in [-1, 1], directional
    ls_ratio: float          # long/short account ratio (raw)
    ls_score: float          # in [-1, 1], contrarian
    taker_ratio: float       # raw buy/(buy+sell) volume ratio, 0.0–1.0; 0.5 = neutral
    taker_score: float       # in [-1, 1], directional, non-linear at extremes
    aggregate: float         # weighted composite in [-1, 1]
    timestamp: float
    available: bool          # False when futures data doesn't exist for symbol


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _get_json(path: str, params: dict | None = None) -> object:
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(f"{_FAPI_BASE}{path}", params=params)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        raise exc


def _fetch_funding_rate(symbol: str) -> tuple[float, float]:
    """Return (raw_funding_rate, funding_score).

    Funding score is *contrarian*:
        positive funding (longs pay shorts) → market over-long → score negative.
        negative funding (shorts pay longs) → market over-short → score positive.
    """
    data = _get_json("/fapi/v1/premiumIndex", {"symbol": symbol.upper()})
    if not isinstance(data, dict):
        return (0.0, 0.0)
    rate = float(data.get("lastFundingRate", 0.0) or 0.0)
    score = _clamp(-rate / _FUNDING_NORM)
    return (rate, score)


def _fetch_oi_change(symbol: str) -> tuple[float, float]:
    """Return (oi_change_pct, oi_score) from last 2 OI snapshots.

    OI score is *directional*:
        rising OI = more conviction (positive if used with current price direction,
        here treated as a raw magnitude — caller can further weight).
        We return a signed value: +1 if OI is growing, -1 if shrinking.
    """
    data = _get_json(
        "/futures/data/openInterestHist",
        {"symbol": symbol.upper(), "period": "15m", "limit": 2},
    )
    if not isinstance(data, list) or len(data) < 2:
        return (0.0, 0.0)

    # Snapshots are ordered oldest → newest.
    oi_prev = float(data[0].get("sumOpenInterest", 0.0) or 0.0)
    oi_now  = float(data[-1].get("sumOpenInterest", 0.0) or 0.0)

    if oi_prev <= 0.0:
        return (0.0, 0.0)

    pct_change = (oi_now - oi_prev) / oi_prev
    score = _clamp(pct_change / _OI_NORM)
    return (round(pct_change, 6), score)


def _fetch_taker_ratio(symbol: str) -> tuple[float, float]:
    """Return (taker_buy_ratio, taker_score) from Binance taker long/short ratio.

    `buySellRatio` from `/futures/data/takerlongshortRatio` is buy volume /
    (buy + sell) volume, so 0.5 = neutral, >0.5 = more aggressive buyers.

    Score is *directional* but non-linear: moderate aggression maps linearly
    to [-1, 1]; extreme aggression (|score| > _TAKER_EXTREME) is degraded by
    10% because very extreme taker flow often precedes a short-term reversal.
    """
    data = _get_json(
        "/futures/data/takerlongshortRatio",
        {"symbol": symbol.upper(), "period": "15m", "limit": 1},
    )
    if not isinstance(data, list) or not data:
        return (0.5, 0.0)

    raw = float(data[-1].get("buySellRatio", 1.0) or 1.0)
    # Convert raw buySellRatio (buy/sell) to buy/(buy+sell): r = raw/(1+raw)
    ratio = raw / (1.0 + raw)
    deviation = ratio - 0.5
    linear_score = _clamp(deviation / _TAKER_NORM)
    # Non-linear: degrade extreme readings by 10%
    if abs(linear_score) > _TAKER_EXTREME:
        linear_score *= 0.90
    return (round(ratio, 4), round(linear_score, 4))


def _fetch_ls_ratio(symbol: str) -> tuple[float, float]:
    """Return (long_short_ratio, ls_score) from global account ratio.

    Averages the global and top-trader ratios when both are available.
    L/S score is *contrarian*:
        ratio >> 1 (too many longs)  → negative score (fade the crowd).
        ratio << 1 (too many shorts) → positive score (squeeze potential).
    """
    ratios: list[float] = []
    for endpoint in (
        "/futures/data/globalLongShortAccountRatio",
        "/futures/data/topLongShortAccountRatio",
    ):
        try:
            data = _get_json(endpoint, {"symbol": symbol.upper(), "period": "15m", "limit": 1})
            if isinstance(data, list) and data:
                r = float(data[-1].get("longShortRatio", 1.0) or 1.0)
                ratios.append(r)
        except httpx.HTTPError:
            pass

    if not ratios:
        return (1.0, 0.0)

    avg_ratio = sum(ratios) / len(ratios)
    # Contrarian: deviation from 1.0 (neutral), inverted.
    score = _clamp(-(avg_ratio - 1.0) / _LS_NORM)
    return (round(avg_ratio, 4), score)


def fetch_onchain_signals(symbol: str) -> OnChainSignal:
    """Fetch and aggregate on-chain signals for a symbol.

    Results are cached with a 15-minute TTL. On any network error the
    returned OnChainSignal has available=False and all scores = 0.0 so
    callers can gracefully degrade.

    Args:
        symbol: Trading pair (e.g. "BTCUSDT").

    Returns:
        OnChainSignal with funding, OI, L/S components and weighted aggregate.
    """
    sym = symbol.upper()
    now = time.time()

    cached_ts, cached_sig = _cache.get(sym, (0.0, None))  # type: ignore[misc]
    if cached_sig is not None and (now - cached_ts) < _CACHE_TTL:
        return cached_sig

    try:
        funding_rate, funding_score = _fetch_funding_rate(sym)
    except httpx.HTTPError as exc:
        logger.debug("onchain(%s): funding fetch failed: %s", sym, exc)
        _unavailable = OnChainSignal(
            symbol=sym, funding_rate=0.0, funding_score=0.0,
            oi_change_pct=0.0, oi_score=0.0,
            ls_ratio=1.0, ls_score=0.0,
            taker_ratio=0.5, taker_score=0.0,
            aggregate=0.0, timestamp=now, available=False,
        )
        _cache[sym] = (now, _unavailable)
        return _unavailable

    try:
        oi_change_pct, oi_score = _fetch_oi_change(sym)
    except httpx.HTTPError as exc:
        logger.debug("onchain(%s): OI fetch failed: %s", sym, exc)
        oi_change_pct, oi_score = 0.0, 0.0

    try:
        ls_ratio, ls_score = _fetch_ls_ratio(sym)
    except httpx.HTTPError as exc:
        logger.debug("onchain(%s): L/S fetch failed: %s", sym, exc)
        ls_ratio, ls_score = 1.0, 0.0

    try:
        taker_ratio, taker_score = _fetch_taker_ratio(sym)
    except httpx.HTTPError as exc:
        logger.debug("onchain(%s): taker fetch failed: %s", sym, exc)
        taker_ratio, taker_score = 0.5, 0.0

    aggregate = _clamp(
        _W_FUNDING * funding_score
        + _W_OI     * oi_score
        + _W_TAKER  * taker_score
        + _W_LS     * ls_score
    )

    sig = OnChainSignal(
        symbol=sym,
        funding_rate=round(funding_rate, 8),
        funding_score=round(funding_score, 4),
        oi_change_pct=oi_change_pct,
        oi_score=round(oi_score, 4),
        ls_ratio=ls_ratio,
        ls_score=round(ls_score, 4),
        taker_ratio=taker_ratio,
        taker_score=taker_score,
        aggregate=round(aggregate, 4),
        timestamp=now,
        available=True,
    )
    _cache[sym] = (now, sig)

    logger.info(
        "onchain(%s): funding=%.5f(%.2f) oi_chg=%.3f%%(%.2f) "
        "taker=%.3f(%.2f) ls=%.3f(%.2f) agg=%.3f",
        sym,
        funding_rate, funding_score,
        oi_change_pct * 100, oi_score,
        taker_ratio, taker_score,
        ls_ratio, ls_score,
        aggregate,
    )
    return sig
