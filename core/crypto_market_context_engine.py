"""
core/crypto_market_context_engine.py — Global market context for trading decisions.

Two signals layered on top of the per-symbol pipeline:

    1. Fear & Greed Index (alternative.me, no key required)
       Maps the 0–100 sentiment index to a contrarian score in [-1, 1]:
           Extreme Fear  (0–24)  →  +1.0  (crowd scared → long opportunity)
           Fear          (25–46) →  +0.5
           Neutral       (47–53) →   0.0
           Greed         (54–74) →  -0.5
           Extreme Greed (75+)   →  -1.0  (crowd euphoric → reduce exposure)

       Callers use `fg_score` as a macro bias: multiply position size by
       `size_multiplier` (1.2 in Extreme Fear, 0.7 in Extreme Greed) and log
       the regime for each iteration.

    2. News-driven pair discovery
       Scans the current NewsItem list to find assets with strong positive
       sentiment that are not already in the top-volume watchlist. Returns up
       to `max_extra` USDT pairs to append to the scan list. A ticker must
       appear in ≥ 2 items and have a mean score ≥ 0.20 to qualify.

Fear & Greed is cached for 1 hour (it only updates once daily).
Trending discovery is recomputed each call from the live news_items.

Public API:
    MarketContext  — dataclass returned by fetch_market_context().
    fetch_market_context(news_items, known_symbols, max_extra) -> MarketContext
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from collections import defaultdict

import httpx

from core.crypto_types import NewsItem
from core.logger import logger

_FNG_URL = "https://api.alternative.me/fng/"
_TIMEOUT = 8.0
_FNG_CACHE_TTL = 3600.0  # 1 hour — index only updates once a day

# Minimum news items and score threshold to qualify a ticker as "trending".
_MIN_ITEMS = 2
_MIN_SCORE = 0.20

# Tickers that map to valid Binance USDT pairs (subset of common assets).
_KNOWN_BASES = {
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "MATIC",
    "LINK", "UNI", "LTC", "ATOM", "ETC", "XLM", "TRX", "NEAR", "APT", "ARB",
    "OP", "SUI", "TON", "SHIB", "PEPE", "FIL", "INJ", "AAVE", "MKR", "LDO",
    "FTM", "ALGO", "VET", "SAND", "MANA", "AXS", "GALA", "CHZ", "FLOW", "ICP",
    "HBAR", "EGLD", "THETA", "ZEC", "DASH", "NEO", "KAVA", "BAND", "REN", "BAT",
}

_fg_cache: tuple[float, "MarketContext"] | None = None


@dataclass
class MarketContext:
    """Market-wide context for one trading iteration."""

    fg_value: int           # raw Fear & Greed index 0–100
    fg_label: str           # "Extreme Fear" | "Fear" | "Neutral" | "Greed" | "Extreme Greed"
    fg_score: float         # contrarian score in [-1, 1]
    size_multiplier: float  # apply to Kelly size: > 1 in fear, < 1 in greed
    trending_pairs: list[str] = field(default_factory=list)  # extra USDT pairs from news
    timestamp: float = 0.0
    available: bool = True


def _fetch_fear_greed() -> tuple[int, str]:
    """Return (value, label) from the Alternative.me Fear & Greed API."""
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(_FNG_URL, params={"limit": 1, "format": "json"})
            resp.raise_for_status()
            data = resp.json()
        entry = data["data"][0]
        value = int(entry["value"])
        label = str(entry["value_classification"])
        return (value, label)
    except Exception as exc:
        raise exc


def _fg_to_score(value: int) -> tuple[float, float]:
    """Return (fg_score, size_multiplier) from raw 0–100 index."""
    if value <= 24:
        return (1.0, 1.20)   # Extreme Fear
    if value <= 46:
        return (0.5, 1.10)   # Fear
    if value <= 53:
        return (0.0, 1.00)   # Neutral
    if value <= 74:
        return (-0.5, 0.85)  # Greed
    return (-1.0, 0.70)      # Extreme Greed


def _discover_trending_pairs(
    news_items: list[NewsItem],
    known_symbols: set[str],
    max_extra: int,
) -> list[str]:
    """Return USDT pairs with positive news momentum not already in the watchlist.

    Algorithm:
        1. Group items by ticker (from item.currencies, filtered to _KNOWN_BASES).
        2. Keep tickers with ≥ _MIN_ITEMS articles and mean score ≥ _MIN_SCORE.
        3. Sort by mean score descending.
        4. Map to USDT pairs, skip if already in known_symbols.
        5. Return at most max_extra results.
    """
    ticker_scores: dict[str, list[float]] = defaultdict(list)

    for item in news_items:
        for ticker in item.currencies:
            t = ticker.upper()
            if t in _KNOWN_BASES:
                ticker_scores[t].append(float(item.score))

    candidates: list[tuple[float, str]] = []
    for ticker, scores in ticker_scores.items():
        if len(scores) < _MIN_ITEMS:
            continue
        mean = sum(scores) / len(scores)
        if mean >= _MIN_SCORE:
            candidates.append((mean, ticker))

    candidates.sort(reverse=True)

    result: list[str] = []
    for _, ticker in candidates:
        pair = f"{ticker}USDT"
        if pair not in known_symbols:
            result.append(pair)
        if len(result) >= max_extra:
            break
    return result


def fetch_market_context(
    news_items: list[NewsItem],
    known_symbols: set[str] | None = None,
    max_extra: int = 5,
) -> MarketContext:
    """Fetch Fear & Greed index and discover trending pairs from news.

    The F&G result is cached for 1 hour; trending discovery always runs
    against the current news_items. On F&G failure the context is still
    returned with fg_score=0.0 and available=False but trending discovery
    still runs (it has no network dependency).

    Args:
        news_items: Current news batch (already fetched by fetch_news()).
        known_symbols: Symbols already in the watchlist (to avoid duplicates).
        max_extra: Maximum number of extra pairs to append (default 5).

    Returns:
        MarketContext with fg fields and trending_pairs populated.
    """
    global _fg_cache
    now = time.time()

    # Try cached F&G first.
    fg_value, fg_label, fg_score, size_mult, fg_available = 50, "Neutral", 0.0, 1.0, True
    if _fg_cache is not None:
        cached_ts, cached_ctx = _fg_cache
        if (now - cached_ts) < _FNG_CACHE_TTL:
            fg_value = cached_ctx.fg_value
            fg_label = cached_ctx.fg_label
            fg_score = cached_ctx.fg_score
            size_mult = cached_ctx.size_multiplier
            fg_available = cached_ctx.available
        else:
            _fg_cache = None

    if _fg_cache is None:
        try:
            fg_value, fg_label = _fetch_fear_greed()
            fg_score, size_mult = _fg_to_score(fg_value)
            fg_available = True
            logger.info(
                "market_context: F&G=%d (%s) score=%.1f size_mult=%.2f",
                fg_value, fg_label, fg_score, size_mult,
            )
        except Exception as exc:
            logger.warning("market_context: F&G fetch failed: %s — using neutral", exc)
            fg_available = False

    trending = _discover_trending_pairs(
        news_items,
        set(known_symbols or ()),
        max_extra,
    )
    if trending:
        logger.info("market_context: trending pairs from news: %s", ", ".join(trending))

    ctx = MarketContext(
        fg_value=fg_value,
        fg_label=fg_label,
        fg_score=fg_score,
        size_multiplier=size_mult,
        trending_pairs=trending,
        timestamp=now,
        available=fg_available,
    )
    if fg_available:
        _fg_cache = (now, ctx)
    return ctx
