"""
core/crypto_data_collector.py — Bulk historical OHLCV downloader from Binance REST.

Downloads up to 2 years of 15m candles for all 12 trading pairs and saves
them as Parquet files in `.data/` for ML feature engineering.

Public API:
    download_pair(symbol, interval, days) -> pd.DataFrame
    download_all(symbols, interval, days, out_dir) -> dict[str, Path]
    load_pair(symbol, out_dir) -> pd.DataFrame
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import pandas as pd

from core.logger import logger

_BASE = "https://api.binance.com"
_KLINE_LIMIT = 1000  # max per Binance request

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT", "UNIUSDT",
]

_INTERVAL_MS: dict[str, int] = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000,
    "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
}


def download_pair(
    symbol: str,
    interval: str = "15m",
    days: int = 730,
    out_dir: Path | None = None,
) -> pd.DataFrame:
    """Download historical klines for one symbol and optionally persist to Parquet.

    Args:
        symbol: e.g. "BTCUSDT"
        interval: Binance kline interval string (default "15m")
        days: How many calendar days of history to fetch (default 730 = ~2 years)
        out_dir: If set, saves DataFrame as <symbol>_<interval>.parquet here.

    Returns:
        DataFrame with columns: open_time, open, high, low, close, volume,
        close_time, quote_volume, trades, taker_buy_base, taker_buy_quote.
    """
    ms_per_candle = _INTERVAL_MS.get(interval, 900_000)
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - days * 86_400_000

    rows: list[list] = []
    current_start = start_ms

    logger.info("download_pair: %s %s from %s (%d days)", symbol, interval,
                pd.to_datetime(start_ms, unit="ms").date(), days)

    with httpx.Client(timeout=30.0) as client:
        while current_start < end_ms:
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": current_start,
                "endTime": end_ms,
                "limit": _KLINE_LIMIT,
            }
            try:
                resp = client.get(f"{_BASE}/api/v3/klines", params=params)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as exc:
                logger.warning("download_pair: HTTP error for %s: %s", symbol, exc)
                break

            if not data:
                break

            rows.extend(data)
            last_open_time = data[-1][0]
            current_start = last_open_time + ms_per_candle

            if len(data) < _KLINE_LIMIT:
                break

            time.sleep(0.12)  # ~8 req/s — well within Binance 1200 weight/min

    if not rows:
        logger.warning("download_pair: no data returned for %s", symbol)
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "_ignore",
    ])
    df = df.drop(columns=["_ignore"])
    for col in ("open", "high", "low", "close", "volume", "quote_volume",
                "taker_buy_base", "taker_buy_quote"):
        df[col] = df[col].astype(float)
    df["trades"] = df["trades"].astype(int)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    df = df.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    df["symbol"] = symbol

    logger.info("download_pair: %s — %d candles downloaded", symbol, len(df))

    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{symbol}_{interval}.parquet"
        df.to_parquet(path, index=False)
        logger.info("download_pair: saved to %s", path)

    return df


def download_all(
    symbols: list[str] | None = None,
    interval: str = "15m",
    days: int = 730,
    out_dir: str | Path = ".data",
) -> dict[str, Path]:
    """Download all 12 pairs and save as Parquet files.

    Args:
        symbols: List of Binance symbols. Defaults to all 12 AlphaCota pairs.
        interval: Kline interval (default "15m").
        days: Days of history (default 730).
        out_dir: Output directory for Parquet files.

    Returns:
        Dict mapping symbol -> saved Parquet path.
    """
    symbols = symbols or SYMBOLS
    out_dir = Path(out_dir)
    saved: dict[str, Path] = {}

    for sym in symbols:
        try:
            df = download_pair(sym, interval, days, out_dir)
            if not df.empty:
                saved[sym] = out_dir / f"{sym}_{interval}.parquet"
        except Exception as exc:
            logger.error("download_all: failed %s — %s", sym, exc)

    logger.info("download_all: done — %d/%d pairs saved", len(saved), len(symbols))
    return saved


def load_pair(symbol: str, interval: str = "15m", out_dir: str | Path = ".data") -> pd.DataFrame:
    """Load a previously downloaded Parquet file for one pair.

    Args:
        symbol: e.g. "BTCUSDT"
        interval: Kline interval used when downloading.
        out_dir: Directory where Parquet files are stored.

    Returns:
        DataFrame or empty DataFrame if file not found.
    """
    path = Path(out_dir) / f"{symbol}_{interval}.parquet"
    if not path.exists():
        logger.warning("load_pair: %s not found — run download_pair() first", path)
        return pd.DataFrame()
    return pd.read_parquet(path)
