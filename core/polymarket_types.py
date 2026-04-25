"""
core/polymarket_types.py — Shared dataclasses for the Polymarket trading system.

All types are frozen dataclasses (immutable). No business logic here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Market:
    condition_id: str
    token_id: str          # YES token_id used for CLOB orders
    question: str
    end_date_iso: str      # ISO 8601
    volume_24h: float      # USD
    spread_pct: float      # bid/ask spread as fraction (0.03 = 3%)
    days_to_resolution: float
    yes_price: float       # current YES probability / price (0–1)
    category: str = ""
    is_active: bool = True


@dataclass(frozen=True)
class OrderBookLevel:
    price: float           # 0–1
    size: float            # USDC


@dataclass(frozen=True)
class OrderBook:
    token_id: str
    bids: tuple[OrderBookLevel, ...]   # highest bid first
    asks: tuple[OrderBookLevel, ...]   # lowest ask first
    mid_price: float
    spread_pct: float


@dataclass(frozen=True)
class OrderIntent:
    condition_id: str
    token_id: str
    direction: str          # "yes" | "no"
    size_usd: float
    limit_price: float      # 0–1; use mid_price + half_spread for paper
    mode: str               # "paper" | "live"


@dataclass(frozen=True)
class Order:
    client_order_id: str
    condition_id: str
    token_id: str
    direction: str
    size_usd: float
    fill_price: float
    status: str             # "pending" | "filled" | "cancelled" | "rejected"
    mode: str               # "paper" | "live"
    created_at: float       # unix timestamp


@dataclass(frozen=True)
class Position:
    position_id: str
    condition_id: str
    token_id: str
    direction: str
    size_usd: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    mode: str
    opened_at: float        # unix timestamp


@dataclass(frozen=True)
class Trade:
    trade_id: str
    condition_id: str
    direction: str
    size_usd: float
    entry_price: float
    exit_price: float
    realized_pnl: float
    mode: str
    opened_at: float
    closed_at: float


@dataclass(frozen=True)
class TradeDecision:
    condition_id: str
    token_id: str
    direction: str          # "yes" | "no"
    size_usd: float         # 0.0 = do not trade
    score: float            # 0–100 composite market score
    kelly_fraction: float   # 0–0.25 capped Kelly
    reasoning: str


@dataclass(frozen=True)
class WalletHealth:
    address: str
    matic_balance: float    # MATIC (gas)
    usdc_balance: float     # USDC available to trade
    usdc_allowance: float   # USDC approved for CTF Exchange contract
    is_healthy: bool        # True if balance ≥ $20 and allowance granted
    checked_at: float       # unix timestamp


@dataclass(frozen=True)
class CopySignal:
    direction: str          # "yes" | "no" | "none"
    confidence: float       # 0–1
    wallet_count: int
    consensus_ratio: float  # fraction of wallets on majority side
