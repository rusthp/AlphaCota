"""
core/polymarket_discovery.py — Enhanced market discovery for Polymarket.

Combines keyword search + trending endpoint, deduplicates by condition_id,
and applies quality filters before returning candidate markets.

Public API:
    discover_markets(config) -> list[Market]
    volume_weighted_probability(markets) -> float
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from core.logger import logger
from core.polymarket_types import Market

_GAMMA_BASE = "https://gamma-api.polymarket.com"

# Quality filter defaults (also used by polymarket_client.py)
MIN_VOLUME_24H: float = 5_000.0
MAX_SPREAD_PCT: float = 0.05
MIN_DAYS: float = 2.0
MAX_DAYS: float = 180.0


@dataclass
class DiscoveryConfig:
    """Configuration for market discovery filters."""

    min_volume_24h: float = MIN_VOLUME_24H
    max_spread_pct: float = MAX_SPREAD_PCT
    min_days_to_resolution: float = MIN_DAYS
    max_days_to_resolution: float = MAX_DAYS
    limit: int = 20
    trending_fetch_size: int = 100


def _fetch_trending(limit: int = 100) -> list[dict[str, Any]]:
    """Fetch trending markets from Gamma API sorted by volume."""
    url = f"{_GAMMA_BASE}/markets"
    params: dict[str, Any] = {
        "order": "volumeNum",
        "ascending": "false",
        "limit": limit,
        "active": "true",
        "closed": "false",
    }
    resp = httpx.get(url, params=params, timeout=15.0)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    if isinstance(data, list):
        return data
    return []


def _parse_market(raw: dict[str, Any]) -> Market | None:
    """Convert a raw Gamma API market dict into a Market dataclass."""
    try:
        condition_id = raw.get("conditionId") or raw.get("condition_id") or ""
        if not condition_id:
            return None

        tokens = raw.get("tokens") or []
        token_id = ""
        for tok in tokens:
            if isinstance(tok, dict) and tok.get("outcome", "").lower() in ("yes", "sim"):
                token_id = tok.get("token_id") or tok.get("tokenId") or ""
                break
        if not token_id and tokens:
            first = tokens[0]
            token_id = (
                first.get("token_id") or first.get("tokenId") or ""
                if isinstance(first, dict)
                else ""
            )

        question = raw.get("question") or raw.get("title") or ""
        end_date = raw.get("endDate") or raw.get("end_date_iso") or ""

        volume_raw = raw.get("volume24hr") or raw.get("volumeNum") or raw.get("volume_24h") or 0.0
        try:
            volume_24h = float(volume_raw)
        except (TypeError, ValueError):
            volume_24h = 0.0

        best_bid = float(raw.get("bestBid") or 0.0)
        best_ask = float(raw.get("bestAsk") or 1.0)
        spread_pct = best_ask - best_bid if best_ask > best_bid else 0.0

        outcome_prices = raw.get("outcomePrices") or []
        last_price_raw = raw.get("lastTradePrice")
        if last_price_raw is not None:
            last_price = float(last_price_raw)
        elif outcome_prices:
            last_price = float(outcome_prices[0])
        else:
            last_price = 0.5

        end_ts: float = 0.0
        if end_date:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                end_ts = dt.timestamp()
            except ValueError:
                end_ts = 0.0
        days_to_resolution = max(0.0, (end_ts - time.time()) / 86400.0) if end_ts else 0.0

        category_raw = raw.get("tags") or raw.get("category") or []
        if isinstance(category_raw, list) and category_raw:
            first_tag = category_raw[0]
            category = (
                (first_tag.get("label") or "").lower()
                if isinstance(first_tag, dict)
                else str(first_tag).lower()
            )
        elif isinstance(category_raw, str):
            category = category_raw.lower()
        else:
            category = ""

        is_active = bool(raw.get("active", True)) and not bool(raw.get("closed", False))

        return Market(
            condition_id=condition_id,
            token_id=token_id,
            question=question,
            end_date_iso=end_date,
            volume_24h=volume_24h,
            spread_pct=spread_pct,
            days_to_resolution=days_to_resolution,
            yes_price=last_price,
            category=category,
            is_active=is_active,
        )
    except Exception as exc:
        logger.debug("_parse_market failed: %s", exc)
        return None


def _apply_quality_filter(market: Market, config: DiscoveryConfig) -> bool:
    """Return True if market passes all quality filters."""
    if not market.is_active:
        return False
    if market.volume_24h < config.min_volume_24h:
        return False
    if market.spread_pct > config.max_spread_pct:
        return False
    if market.days_to_resolution < config.min_days_to_resolution:
        return False
    return not market.days_to_resolution > config.max_days_to_resolution


def discover_markets(config: DiscoveryConfig | None = None) -> list[Market]:
    """Return quality-filtered Polymarket binary markets ordered by 24 h volume.

    Fetches trending markets from the Gamma API, parses each into a Market
    dataclass, deduplicates by condition_id, and applies quality filters.

    Args:
        config: DiscoveryConfig with filter thresholds. Uses defaults if None.

    Returns:
        List of Market dataclasses, deduplicated by condition_id, sorted by
        24h volume descending, capped at config.limit.
    """
    cfg = config or DiscoveryConfig()

    try:
        raw_markets = _fetch_trending(limit=cfg.trending_fetch_size)
    except Exception as exc:
        logger.error("discover_markets: Gamma API error: %s", exc)
        return []

    seen: set[str] = set()
    results: list[Market] = []

    for raw in raw_markets:
        market = _parse_market(raw)
        if market is None:
            continue
        if market.condition_id in seen:
            continue
        seen.add(market.condition_id)
        if not _apply_quality_filter(market, cfg):
            continue
        results.append(market)
        if len(results) >= cfg.limit:
            break

    logger.info(
        "discover_markets: returned %d markets (from %d raw, %d unique)",
        len(results),
        len(raw_markets),
        len(seen),
    )
    return results


def volume_weighted_probability(markets: list[Market]) -> float:
    """Compute volume-weighted average YES probability across markets.

    Uses 24h volume as weight. Falls back to simple average when all volumes
    are zero.

    Args:
        markets: List of Market dataclasses.

    Returns:
        Volume-weighted mean YES price in [0, 1], or 0.0 for empty list.
    """
    if not markets:
        return 0.0

    total_vol = sum(m.volume_24h for m in markets)
    if total_vol == 0.0:
        return sum(m.yes_price for m in markets) / len(markets)

    weighted_sum = sum(m.yes_price * m.volume_24h for m in markets)
    return weighted_sum / total_vol
