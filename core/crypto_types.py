"""
core/crypto_types.py — Shared dataclasses for the autonomous crypto trading system.

All types are frozen dataclasses (immutable). No business logic here — pure data
containers used by data, signal, risk, sizing, executor, and loop layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class CryptoCandle:
    """A single OHLCV candle from the exchange."""

    symbol: str            # e.g. "BTCUSDT"
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: float       # unix seconds (open time of the candle)


@dataclass(frozen=True)
class CryptoSignal:
    """A trading signal emitted by the signal engine."""

    symbol: str
    direction: Literal["long", "short", "flat"]
    confidence: float      # 0.0 – 1.0
    reason: str
    entry_price: float
    stop_loss: float
    take_profit: float
    timestamp: float       # unix seconds


@dataclass(frozen=True)
class CryptoOrder:
    """An order record persisted to the ledger."""

    id: str
    symbol: str
    side: Literal["buy", "sell"]
    qty: float             # position size in USD (quote) — kept as float for portability
    price: float           # fill price
    status: Literal["pending", "filled", "cancelled", "rejected"]
    mode: Literal["paper", "live"]
    created_at: float      # unix seconds


@dataclass(frozen=True)
class CryptoTrade:
    """A closed round-trip trade with realised PnL."""

    id: str
    symbol: str
    side: Literal["long", "short"]
    entry_price: float
    exit_price: float
    qty: float             # USD notional
    pnl: float             # USD realised PnL
    pnl_pct: float         # realised PnL as fraction of entry notional
    opened_at: float       # unix seconds
    closed_at: float       # unix seconds
    reason: str            # exit reason (sl_hit, tp_hit, signal_flip, manual)


@dataclass(frozen=True)
class CryptoPosition:
    """An open position currently managed by the loop."""

    id: str
    symbol: str
    side: Literal["long", "short"]
    entry_price: float
    qty: float             # USD notional at entry
    stop_loss: float
    take_profit: float
    opened_at: float       # unix seconds
    mode: Literal["paper", "live"]


@dataclass(frozen=True)
class NewsItem:
    """A single news headline with sentiment metadata."""

    title: str
    url: str
    sentiment: Literal["positive", "negative", "neutral"]
    score: float           # -1.0 (bearish) .. 1.0 (bullish)
    published_at: float    # unix seconds
    currencies: list[str]  # tickers/symbols mentioned (e.g. ["BTC", "ETH"])
