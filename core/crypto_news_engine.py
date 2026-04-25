"""
core/crypto_news_engine.py — News fetching + sentiment scoring for crypto.

Two sources, chosen at runtime:
    1. CryptoPanic API (preferred) — requires CRYPTOPANIC_API_KEY env var.
    2. Cointelegraph RSS feed (fallback) — no API key required.

Sentiment is first classified by heuristic (CryptoPanic votes / keyword
scoring for RSS), then optionally refined by a Groq LLM call for the
per-symbol aggregate.

Public API:
    fetch_news(currencies, limit) -> list[NewsItem]
    score_news_sentiment(items, symbol) -> float
    analyze_news_with_llm(headlines, symbol) -> tuple[str, float]
"""

from __future__ import annotations

import os
import re
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx

from core.crypto_types import NewsItem
from core.logger import logger

try:
    from groq import Groq
    _HAS_GROQ = True
except ImportError:  # pragma: no cover - import guard
    _HAS_GROQ = False


_CRYPTOPANIC_URL = "https://cryptopanic.com/api/free/v1/posts/"
_COINTELEGRAPH_RSS = "https://cointelegraph.com/rss"
_DEFAULT_TIMEOUT = 10.0

# Keyword heuristics for RSS fallback — used when no structured vote data exists.
_POSITIVE_KEYWORDS = (
    "surge", "rally", "soars", "bullish", "gains", "breakout", "record high",
    "all-time high", "ath", "adoption", "approval", "etf approved", "green",
    "rebound", "recovery", "buy", "accumulation", "partnership", "upgrade",
)
_NEGATIVE_KEYWORDS = (
    "crash", "plunge", "tumble", "bearish", "sell-off", "selloff", "hack",
    "exploit", "fraud", "lawsuit", "ban", "delist", "liquidation", "correction",
    "breakdown", "rejection", "fud", "fear", "dump", "rugpull", "bankruptcy",
)


def fetch_news(
    currencies: list[str] | None = None,
    limit: int = 20,
) -> list[NewsItem]:
    """Fetch recent crypto news from CryptoPanic, falling back to Cointelegraph RSS.

    Args:
        currencies: Optional list of base tickers to filter on (e.g. ["BTC", "ETH"]).
                    Only used when hitting CryptoPanic; the RSS fallback ignores it
                    since the RSS feed is mixed-topic.
        limit: Maximum number of items to return.

    Returns:
        List of NewsItem, newest first. Returns an empty list on total failure.
    """
    api_key = os.getenv("CRYPTOPANIC_API_KEY", "").strip()
    if api_key:
        items = _fetch_cryptopanic(api_key, currencies, limit)
        if items:
            return items
        logger.info("fetch_news: cryptopanic returned no items — falling back to RSS")

    return _fetch_cointelegraph_rss(limit)


def _fetch_cryptopanic(
    api_key: str,
    currencies: list[str] | None,
    limit: int,
) -> list[NewsItem]:
    """Fetch posts from CryptoPanic's free v1 API."""
    params: dict[str, str] = {"auth_token": api_key, "public": "true"}
    if currencies:
        params["currencies"] = ",".join(c.upper() for c in currencies)

    try:
        with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
            resp = client.get(_CRYPTOPANIC_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("_fetch_cryptopanic: %s", exc)
        return []

    results = payload.get("results", []) if isinstance(payload, dict) else []
    items: list[NewsItem] = []
    for post in results[:limit]:
        if not isinstance(post, dict):
            continue
        title = str(post.get("title", "")).strip()
        url = str(post.get("url", "")).strip()
        if not title or not url:
            continue

        votes = post.get("votes", {}) if isinstance(post.get("votes"), dict) else {}
        positive = int(votes.get("positive", 0) or 0)
        negative = int(votes.get("negative", 0) or 0)
        important = int(votes.get("important", 0) or 0)
        # Heuristic: use net votes normalised by total engagement.
        total_votes = positive + negative + important + 1
        score = (positive - negative) / total_votes
        score = max(-1.0, min(1.0, score))
        sentiment = _score_to_label(score)

        published = _parse_timestamp(post.get("published_at") or post.get("created_at"))
        curr_list = [
            str(c.get("code", "")).upper()
            for c in post.get("currencies") or []
            if isinstance(c, dict) and c.get("code")
        ]

        items.append(
            NewsItem(
                title=title,
                url=url,
                sentiment=sentiment,
                score=round(score, 4),
                published_at=published,
                currencies=curr_list,
            )
        )
    return items


def _fetch_cointelegraph_rss(limit: int) -> list[NewsItem]:
    """Fallback: parse Cointelegraph's RSS feed — no API key needed."""
    try:
        with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
            resp = client.get(_COINTELEGRAPH_RSS)
            resp.raise_for_status()
            body = resp.text
    except httpx.HTTPError as exc:
        logger.warning("_fetch_cointelegraph_rss: %s", exc)
        return []

    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        logger.warning("_fetch_cointelegraph_rss: parse error %s", exc)
        return []

    channel = root.find("channel")
    if channel is None:
        return []

    items: list[NewsItem] = []
    for item_el in channel.findall("item"):
        title = (item_el.findtext("title") or "").strip()
        url = (item_el.findtext("link") or "").strip()
        pub_raw = item_el.findtext("pubDate") or ""
        description = (item_el.findtext("description") or "").strip()
        if not title or not url:
            continue

        published = _parse_rss_timestamp(pub_raw)
        score = _heuristic_score(f"{title}. {description}")
        sentiment = _score_to_label(score)
        currencies = _extract_tickers(f"{title} {description}")

        items.append(
            NewsItem(
                title=title,
                url=url,
                sentiment=sentiment,
                score=round(score, 4),
                published_at=published,
                currencies=currencies,
            )
        )
        if len(items) >= limit:
            break
    return items


def _score_to_label(score: float) -> str:
    """Bucket a [-1..1] score into positive/negative/neutral."""
    if score >= 0.15:
        return "positive"
    if score <= -0.15:
        return "negative"
    return "neutral"


def _heuristic_score(text: str) -> float:
    """Score a free-form headline/body by keyword counting, normalised to [-1, 1]."""
    lower = text.lower()
    pos_hits = sum(1 for kw in _POSITIVE_KEYWORDS if kw in lower)
    neg_hits = sum(1 for kw in _NEGATIVE_KEYWORDS if kw in lower)
    total = pos_hits + neg_hits
    if total == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos_hits - neg_hits) / total))


_TICKER_RE = re.compile(r"\b([A-Z]{2,6})\b")
_COMMON_TICKERS = {
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "MATIC",
    "LINK", "UNI", "LTC", "ATOM", "ETC", "XLM", "TRX", "NEAR", "APT", "ARB",
    "OP", "SUI", "TON", "SHIB", "PEPE", "FIL", "INJ", "AAVE", "MKR", "LDO",
}


def _extract_tickers(text: str) -> list[str]:
    """Extract plausible crypto tickers by regex + whitelist."""
    candidates = {m.group(1) for m in _TICKER_RE.finditer(text)}
    return sorted(candidates & _COMMON_TICKERS)


def _parse_timestamp(value: object) -> float:
    """Parse an ISO-8601 or unix-epoch timestamp into unix seconds.

    Accepts strings, ints, floats, or None. Returns current time on any failure.
    """
    if value is None:
        return time.time()
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return time.time()
    try:
        # Normalise trailing 'Z' to the +00:00 offset used by fromisoformat.
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        from datetime import datetime
        return datetime.fromisoformat(s).timestamp()
    except (ValueError, TypeError):
        return time.time()


def _parse_rss_timestamp(value: str) -> float:
    """Parse an RFC 822 pubDate (Cointelegraph RSS) into unix seconds."""
    if not value:
        return time.time()
    try:
        dt = parsedate_to_datetime(value)
        if dt is None:
            return time.time()
        return dt.timestamp()
    except (TypeError, ValueError):
        return time.time()


# ---------------------------------------------------------------------------
# Sentiment scoring (pure function)
# ---------------------------------------------------------------------------


def score_news_sentiment(items: list[NewsItem], symbol: str) -> float:
    """Weighted average sentiment score for items relevant to a symbol.

    Weighting:
        positive = +1, negative = -1, neutral = 0
        Each item's contribution is its `.score` (already signed, -1..1).
        Items are filtered to those whose `currencies` list contains the
        symbol's base ticker OR whose title mentions the base ticker as a
        whole word.

    Args:
        items: Candidate NewsItem list.
        symbol: Exchange symbol (e.g. "BTCUSDT"). Base ticker is extracted by
                stripping common quote suffixes (USDT, USDC, BUSD, USD).

    Returns:
        Mean sentiment score in [-1.0, 1.0]; 0.0 if no items match.
    """
    if not items:
        return 0.0

    base = _base_ticker(symbol)
    pattern = re.compile(rf"\b{re.escape(base)}\b", re.IGNORECASE) if base else None

    relevant_scores: list[float] = []
    for item in items:
        matches_ticker = bool(base) and (
            base in [c.upper() for c in item.currencies]
            or (pattern is not None and pattern.search(item.title) is not None)
        )
        if matches_ticker:
            relevant_scores.append(float(item.score))

    if not relevant_scores:
        return 0.0

    mean = sum(relevant_scores) / len(relevant_scores)
    return max(-1.0, min(1.0, round(mean, 4)))


def _base_ticker(symbol: str) -> str:
    """Strip the quote currency suffix to recover the base asset."""
    s = symbol.upper()
    for quote in ("USDT", "USDC", "BUSD", "FDUSD", "TUSD", "USD"):
        if s.endswith(quote) and len(s) > len(quote):
            return s[: -len(quote)]
    return s


# ---------------------------------------------------------------------------
# LLM refinement (Groq)
# ---------------------------------------------------------------------------


def analyze_news_with_llm(
    headlines: list[str],
    symbol: str,
) -> tuple[str, float]:
    """Ask a Groq LLM to classify the aggregate sentiment of headlines.

    Args:
        headlines: Plain-text headlines relevant to the symbol (already filtered).
        symbol: Trading symbol for context (e.g. "BTCUSDT").

    Returns:
        (sentiment_str, confidence) where sentiment_str is one of
        {"positive", "negative", "neutral"} and confidence is in [0.0, 1.0].
        Falls back to ("neutral", 0.5) if Groq is unavailable or fails.
    """
    if not headlines:
        return ("neutral", 0.5)

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or not _HAS_GROQ:
        return ("neutral", 0.5)

    joined = "\n".join(f"- {h}" for h in headlines[:30])
    prompt = (
        f"You are a crypto trader analysing recent news about {symbol}.\n"
        f"Headlines:\n{joined}\n\n"
        "Respond in EXACTLY this format (one line each):\n"
        "SENTIMENT: <POSITIVE|NEGATIVE|NEUTRAL>\n"
        "CONFIDENCE: <integer 0-100>\n"
        "REASON: <one short sentence>\n"
    )

    try:
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a concise crypto sentiment analyst."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=200,
        )
        text = (completion.choices[0].message.content or "").strip()
    except Exception as exc:  # pragma: no cover - external API
        logger.warning("analyze_news_with_llm(%s): groq call failed: %s", symbol, exc)
        return ("neutral", 0.5)

    return _parse_llm_response(text)


def _parse_llm_response(text: str) -> tuple[str, float]:
    """Parse the structured Groq reply into (sentiment, confidence)."""
    upper = text.upper()
    if "POSITIVE" in upper:
        sentiment = "positive"
    elif "NEGATIVE" in upper:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    conf = 50.0
    match = re.search(r"CONFIDENCE\s*:\s*(\d+)", upper)
    if match:
        try:
            conf = float(match.group(1))
        except ValueError:
            conf = 50.0
    conf = max(0.0, min(100.0, conf)) / 100.0
    return (sentiment, round(conf, 3))
