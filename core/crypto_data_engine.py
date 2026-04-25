"""
core/crypto_data_engine.py — Binance public-REST data layer for crypto trading.

Uses raw httpx calls against Binance's public market-data endpoints (no API key
required, no python-binance / ccxt dependency). All network I/O lives here;
downstream engines (signal, chart) consume the returned dataclasses and work
as pure functions.

Public API:
    fetch_candles(symbol, interval, limit) -> list[CryptoCandle]
    fetch_ticker_price(symbol) -> float
    get_top_pairs(quote, min_volume_usd) -> list[str]
    fetch_order_book_imbalance(symbol) -> float
"""

from __future__ import annotations

import time
import httpx

from core.crypto_types import CryptoCandle
from core.logger import logger

_BINANCE_BASE = "https://api.binance.com"
_DEFAULT_TIMEOUT = 10.0

# In-memory candle cache keyed by (symbol, interval, limit).
# TTL matches the candle interval so we never serve data older than one candle.
_INTERVAL_SECONDS: dict[str, int] = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "1d": 86400,
}
_candle_cache: dict[tuple[str, str, int], tuple[float, list[CryptoCandle]]] = {}


def _get_json(path: str, params: dict[str, object] | None = None) -> object:
    """Issue a GET to Binance's public REST API and return decoded JSON.

    Args:
        path: API path (e.g. "/api/v3/klines").
        params: Query string parameters.

    Returns:
        Parsed JSON payload (list or dict depending on the endpoint).

    Raises:
        httpx.HTTPError: On network or non-2xx response (bubbled up by raise_for_status).
    """
    url = f"{_BINANCE_BASE}{path}"
    with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def fetch_candles(
    symbol: str,
    interval: str = "15m",
    limit: int = 100,
) -> list[CryptoCandle]:
    """Fetch recent OHLCV candles for a symbol via Binance klines endpoint.

    Binance kline payload (per row):
        [open_time_ms, open, high, low, close, volume, close_time_ms, ...]

    Args:
        symbol: Trading pair, e.g. "BTCUSDT". Must be a Binance-listed symbol.
        interval: Kline interval ("1m", "5m", "15m", "1h", "4h", "1d", ...).
        limit: Number of candles (1..1000). Binance hard-limits this.

    Returns:
        List of CryptoCandle ordered oldest → newest. Empty list on error.
    """
    if limit < 1:
        return []
    capped_limit = min(int(limit), 1000)

    cache_key = (symbol.upper(), interval, capped_limit)
    ttl = _INTERVAL_SECONDS.get(interval, 60)
    cached = _candle_cache.get(cache_key)
    if cached and (time.time() - cached[0]) < ttl:
        return cached[1]

    try:
        raw = _get_json(
            "/api/v3/klines",
            {"symbol": symbol.upper(), "interval": interval, "limit": capped_limit},
        )
    except httpx.HTTPError as exc:
        logger.warning("fetch_candles(%s, %s): %s", symbol, interval, exc)
        return []

    if not isinstance(raw, list):
        logger.warning("fetch_candles(%s): unexpected payload type %s", symbol, type(raw))
        return []

    out: list[CryptoCandle] = []
    for row in raw:
        try:
            out.append(
                CryptoCandle(
                    symbol=symbol.upper(),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                    timestamp=float(row[0]) / 1000.0,
                )
            )
        except (ValueError, IndexError, TypeError) as exc:
            logger.debug("fetch_candles: skipping bad row %s: %s", row, exc)
            continue
    if out:
        _candle_cache[cache_key] = (time.time(), out)
    return out


def fetch_ticker_price(symbol: str) -> float:
    """Fetch the latest trade price for a symbol.

    Args:
        symbol: Trading pair (e.g. "BTCUSDT").

    Returns:
        Last trade price as float. Raises on network error.

    Raises:
        httpx.HTTPError: On transport failure or non-2xx response.
        ValueError: If the payload cannot be parsed as a price.
    """
    raw = _get_json("/api/v3/ticker/price", {"symbol": symbol.upper()})
    if not isinstance(raw, dict) or "price" not in raw:
        raise ValueError(f"fetch_ticker_price: unexpected payload {raw!r}")
    return float(raw["price"])


def get_top_pairs(
    quote: str = "USDT",
    min_volume_usd: float = 5_000_000.0,
) -> list[str]:
    """Return the top-20 pairs by 24h quote volume against the given quote asset.

    Filters out:
        - Pairs whose symbol does not end with the quote currency
        - Pairs with quoteVolume < min_volume_usd
        - Leveraged tokens (UP/DOWN/BULL/BEAR suffixes) to avoid toxic spreads

    Args:
        quote: Quote currency (e.g. "USDT", "BUSD", "USDC").
        min_volume_usd: Minimum 24h quote volume required for inclusion.

    Returns:
        List of up to 20 symbols, ordered by descending 24h volume.
    """
    try:
        raw = _get_json("/api/v3/ticker/24hr")
    except httpx.HTTPError as exc:
        logger.warning("get_top_pairs: %s", exc)
        return []

    if not isinstance(raw, list):
        return []

    quote_upper = quote.upper()
    _blacklist_suffixes = ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT")

    candidates: list[tuple[str, float]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        sym = str(item.get("symbol", "")).upper()
        if not sym.endswith(quote_upper):
            continue
        if any(sym.endswith(sfx) for sfx in _blacklist_suffixes):
            continue
        try:
            vol = float(item.get("quoteVolume", 0.0))
        except (TypeError, ValueError):
            continue
        if vol < min_volume_usd:
            continue
        candidates.append((sym, vol))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return [sym for sym, _ in candidates[:20]]


def fetch_order_book_imbalance(symbol: str) -> float:
    """Compute bid/ask imbalance from the top 20 levels of the order book.

    Imbalance = (sum_bid_qty - sum_ask_qty) / (sum_bid_qty + sum_ask_qty).
    Positive values indicate buying pressure; negative values indicate selling
    pressure. Range: [-1.0, 1.0]. Returns 0.0 if the book is empty or unreachable.

    Args:
        symbol: Trading pair (e.g. "BTCUSDT").

    Returns:
        Imbalance in [-1.0, 1.0], or 0.0 on error.
    """
    try:
        raw = _get_json("/api/v3/depth", {"symbol": symbol.upper(), "limit": 20})
    except httpx.HTTPError as exc:
        logger.warning("fetch_order_book_imbalance(%s): %s", symbol, exc)
        return 0.0

    if not isinstance(raw, dict):
        return 0.0

    bids = raw.get("bids", [])
    asks = raw.get("asks", [])
    if not bids or not asks:
        return 0.0

    try:
        bid_vol = sum(float(level[1]) for level in bids)
        ask_vol = sum(float(level[1]) for level in asks)
    except (TypeError, ValueError, IndexError) as exc:
        logger.warning("fetch_order_book_imbalance(%s): parse error %s", symbol, exc)
        return 0.0

    total = bid_vol + ask_vol
    if total <= 0.0:
        return 0.0
    imbalance = (bid_vol - ask_vol) / total
    # Clamp defensively to protect downstream consumers.
    return max(-1.0, min(1.0, imbalance))
