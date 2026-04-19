"""
core/crypto_strategy_engine.py — Named trading strategies + backtesting.

Strategies are pure functions: (candles, params) -> StrategySignal.
Backtest simulates a sequence of StrategySignals over historical candles
and returns performance metrics.

Public API:
    list_strategies() -> list[StrategyMeta]
    run_strategy(name, candles, params) -> StrategySignal
    backtest(name, candles, params, initial_balance) -> BacktestResult
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from core.crypto_indicators import calculate_ema, calculate_macd, calculate_rsi
from core.crypto_signal_engine import calculate_atr
from core.crypto_types import CryptoCandle

StrategyName = Literal[
    "trend_follow",
    "rsi_reversal",
    "macd_momentum",
    "breakout",
    "combined",
]


@dataclass
class StrategySignal:
    direction: Literal["long", "short", "flat"]
    confidence: float
    reason: str
    entry_price: float
    stop_loss: float
    take_profit: float
    indicators: dict[str, float] = field(default_factory=dict)


@dataclass
class StrategyMeta:
    name: str
    label: str
    description: str
    default_params: dict[str, Any]


@dataclass
class BacktestTrade:
    direction: Literal["long", "short"]
    entry_price: float
    exit_price: float
    entry_idx: int
    exit_idx: int
    pnl_pct: float
    pnl_usd: float
    size_usd: float
    reason: str


@dataclass
class BacktestResult:
    strategy: str
    symbol: str
    candle_count: int
    initial_balance: float
    final_balance: float
    total_return_pct: float
    trades: list[BacktestTrade]
    win_rate: float
    max_drawdown_pct: float
    sharpe_ratio: float
    profit_factor: float
    avg_trade_pct: float
    equity_curve: list[float]


_STRATEGIES: list[StrategyMeta] = [
    StrategyMeta(
        name="trend_follow",
        label="Trend Following (EMA Cross)",
        description="Enters when EMA20 crosses EMA50. Exits on reversal or ATR stop. Best in trending markets.",
        default_params={"fast_ema": 20, "slow_ema": 50, "atr_sl": 1.5, "atr_tp": 3.0},
    ),
    StrategyMeta(
        name="rsi_reversal",
        label="RSI Reversal",
        description="Buys oversold (RSI<30), sells overbought (RSI>70). Best in ranging/sideways markets.",
        default_params={"rsi_period": 14, "oversold": 30, "overbought": 70, "atr_sl": 1.2, "atr_tp": 2.4},
    ),
    StrategyMeta(
        name="macd_momentum",
        label="MACD Momentum",
        description="Signals on MACD histogram cross of zero. Catches strong momentum moves.",
        default_params={"fast": 12, "slow": 26, "signal": 9, "atr_sl": 1.5, "atr_tp": 2.5},
    ),
    StrategyMeta(
        name="breakout",
        label="ATR Breakout",
        description="Detects price breakouts above/below recent high/low by 1×ATR. Works on volatile pairs.",
        default_params={"lookback": 20, "atr_mult": 1.0, "atr_sl": 1.5, "atr_tp": 3.0},
    ),
    StrategyMeta(
        name="combined",
        label="Combined (All Signals)",
        description="Weighted combination of EMA, MACD, RSI, and volume. Most robust in live trading.",
        default_params={"w_ema": 0.35, "w_macd": 0.30, "w_rsi": 0.20, "w_vol": 0.15, "atr_sl": 1.5, "atr_tp": 3.0},
    ),
]


def list_strategies() -> list[StrategyMeta]:
    return _STRATEGIES


def _sl_tp(
    direction: str,
    entry: float,
    atr: float,
    atr_sl: float,
    atr_tp: float,
) -> tuple[float, float]:
    if direction == "long":
        return entry - atr_sl * atr, entry + atr_tp * atr
    return entry + atr_sl * atr, entry - atr_tp * atr


# ---------------------------------------------------------------------------
# Individual strategy implementations
# ---------------------------------------------------------------------------

def _trend_follow(candles: list[CryptoCandle], p: dict[str, Any]) -> StrategySignal:
    fast, slow = int(p.get("fast_ema", 20)), int(p.get("slow_ema", 50))
    if len(candles) < slow + 5:
        return StrategySignal("flat", 0.0, "warmup", candles[-1].close, 0.0, 0.0)

    closes = [c.close for c in candles]
    ema_f = calculate_ema(closes, fast)
    ema_s = calculate_ema(closes, slow)
    atr = calculate_atr(candles, 14)
    entry = closes[-1]

    ef, es = ema_f[-1], ema_s[-1]
    ef_prev, es_prev = ema_f[-2], ema_s[-2]

    if math.isnan(ef) or math.isnan(es):
        return StrategySignal("flat", 0.0, "warmup", entry, 0.0, 0.0)

    # Fresh cross only
    cross_up = ef > es and ef_prev <= es_prev
    cross_dn = ef < es and ef_prev >= es_prev
    separation = abs(ef - es) / es

    if cross_up:
        direction, conf = "long", min(0.9, 0.6 + separation * 20)
    elif cross_dn:
        direction, conf = "short", min(0.9, 0.6 + separation * 20)
    elif ef > es * 1.002:
        direction, conf = "long", min(0.75, 0.5 + separation * 15)
    elif ef < es * 0.998:
        direction, conf = "short", min(0.75, 0.5 + separation * 15)
    else:
        return StrategySignal("flat", separation, "no_clear_trend", entry, 0.0, 0.0)

    sl, tp = _sl_tp(direction, entry, atr, float(p.get("atr_sl", 1.5)), float(p.get("atr_tp", 3.0)))
    return StrategySignal(
        direction, round(conf, 4),
        f"ema{fast}/ema{slow} sep={separation:.4f}",
        round(entry, 8), round(sl, 8), round(tp, 8),
        {"ema_fast": round(ef, 4), "ema_slow": round(es, 4), "atr": round(atr, 6)},
    )


def _rsi_reversal(candles: list[CryptoCandle], p: dict[str, Any]) -> StrategySignal:
    period = int(p.get("rsi_period", 14))
    oversold = float(p.get("oversold", 30))
    overbought = float(p.get("overbought", 70))
    if len(candles) < period + 5:
        return StrategySignal("flat", 0.0, "warmup", candles[-1].close, 0.0, 0.0)

    closes = [c.close for c in candles]
    rsi_vals = calculate_rsi(closes, period)
    atr = calculate_atr(candles, 14)
    entry = closes[-1]

    last_rsi = rsi_vals[-1]
    if math.isnan(last_rsi):
        return StrategySignal("flat", 0.0, "warmup", entry, 0.0, 0.0)

    if last_rsi <= oversold:
        conf = min(0.9, 0.65 + (oversold - last_rsi) / oversold * 0.8)
        sl, tp = _sl_tp("long", entry, atr, float(p.get("atr_sl", 1.2)), float(p.get("atr_tp", 2.4)))
        return StrategySignal("long", round(conf, 4), f"rsi={last_rsi:.1f} oversold", round(entry, 8), round(sl, 8), round(tp, 8), {"rsi": round(last_rsi, 2), "atr": round(atr, 6)})

    if last_rsi >= overbought:
        conf = min(0.9, 0.65 + (last_rsi - overbought) / (100 - overbought) * 0.8)
        sl, tp = _sl_tp("short", entry, atr, float(p.get("atr_sl", 1.2)), float(p.get("atr_tp", 2.4)))
        return StrategySignal("short", round(conf, 4), f"rsi={last_rsi:.1f} overbought", round(entry, 8), round(sl, 8), round(tp, 8), {"rsi": round(last_rsi, 2), "atr": round(atr, 6)})

    return StrategySignal("flat", 0.0, f"rsi={last_rsi:.1f} neutral", entry, 0.0, 0.0, {"rsi": round(last_rsi, 2)})


def _macd_momentum(candles: list[CryptoCandle], p: dict[str, Any]) -> StrategySignal:
    fast, slow, sig = int(p.get("fast", 12)), int(p.get("slow", 26)), int(p.get("signal", 9))
    if len(candles) < slow + sig + 5:
        return StrategySignal("flat", 0.0, "warmup", candles[-1].close, 0.0, 0.0)

    closes = [c.close for c in candles]
    macd_line, signal_line, hist = calculate_macd(closes, fast, slow, sig)
    atr = calculate_atr(candles, 14)
    entry = closes[-1]

    h, h_prev = hist[-1], hist[-2]
    m, s = macd_line[-1], signal_line[-1]
    if math.isnan(h) or math.isnan(h_prev) or math.isnan(m):
        return StrategySignal("flat", 0.0, "warmup", entry, 0.0, 0.0)

    cross_up = h > 0 and h_prev <= 0
    cross_dn = h < 0 and h_prev >= 0
    strength = abs(h) / (abs(m) + 1e-9)

    if cross_up:
        conf = min(0.88, 0.62 + min(0.26, strength * 0.3))
        sl, tp = _sl_tp("long", entry, atr, float(p.get("atr_sl", 1.5)), float(p.get("atr_tp", 2.5)))
        return StrategySignal("long", round(conf, 4), f"macd_cross_up hist={h:.4f}", round(entry, 8), round(sl, 8), round(tp, 8), {"macd": round(m, 6), "signal": round(s, 6), "hist": round(h, 6)})

    if cross_dn:
        conf = min(0.88, 0.62 + min(0.26, strength * 0.3))
        sl, tp = _sl_tp("short", entry, atr, float(p.get("atr_sl", 1.5)), float(p.get("atr_tp", 2.5)))
        return StrategySignal("short", round(conf, 4), f"macd_cross_dn hist={h:.4f}", round(entry, 8), round(sl, 8), round(tp, 8), {"macd": round(m, 6), "signal": round(s, 6), "hist": round(h, 6)})

    return StrategySignal("flat", 0.0, f"macd_no_cross hist={h:.4f}", entry, 0.0, 0.0, {"macd": round(m, 6), "hist": round(h, 6)})


def _breakout(candles: list[CryptoCandle], p: dict[str, Any]) -> StrategySignal:
    lookback = int(p.get("lookback", 20))
    atr_mult = float(p.get("atr_mult", 1.0))
    if len(candles) < lookback + 5:
        return StrategySignal("flat", 0.0, "warmup", candles[-1].close, 0.0, 0.0)

    window = candles[-(lookback + 1):-1]
    current = candles[-1]
    highs = [c.high for c in window]
    lows = [c.low for c in window]
    atr = calculate_atr(candles, 14)
    entry = current.close

    resistance = max(highs)
    support = min(lows)

    if entry > resistance + atr_mult * atr:
        conf = min(0.88, 0.65 + min(0.23, (entry - resistance) / (atr + 1e-9) * 0.1))
        sl, tp = _sl_tp("long", entry, atr, float(p.get("atr_sl", 1.5)), float(p.get("atr_tp", 3.0)))
        return StrategySignal("long", round(conf, 4), f"breakout above {resistance:.4f}", round(entry, 8), round(sl, 8), round(tp, 8), {"resistance": round(resistance, 4), "support": round(support, 4), "atr": round(atr, 6)})

    if entry < support - atr_mult * atr:
        conf = min(0.88, 0.65 + min(0.23, (support - entry) / (atr + 1e-9) * 0.1))
        sl, tp = _sl_tp("short", entry, atr, float(p.get("atr_sl", 1.5)), float(p.get("atr_tp", 3.0)))
        return StrategySignal("short", round(conf, 4), f"breakout below {support:.4f}", round(entry, 8), round(sl, 8), round(tp, 8), {"resistance": round(resistance, 4), "support": round(support, 4), "atr": round(atr, 6)})

    return StrategySignal("flat", 0.0, f"inside range {support:.4f}–{resistance:.4f}", entry, 0.0, 0.0, {"resistance": round(resistance, 4), "support": round(support, 4)})


def _combined(candles: list[CryptoCandle], p: dict[str, Any]) -> StrategySignal:
    w_ema = float(p.get("w_ema", 0.35))
    w_macd = float(p.get("w_macd", 0.30))
    w_rsi = float(p.get("w_rsi", 0.20))
    w_vol = float(p.get("w_vol", 0.15))

    if len(candles) < 55:
        return StrategySignal("flat", 0.0, "warmup", candles[-1].close, 0.0, 0.0)

    closes = [c.close for c in candles]
    entry = closes[-1]

    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)
    ema_score = 0.0
    if not math.isnan(ema20[-1]) and not math.isnan(ema50[-1]):
        ema_score = 1.0 if ema20[-1] > ema50[-1] else -1.0

    _, _, hist = calculate_macd(closes, 12, 26, 9)
    macd_score = 0.0
    if hist and not math.isnan(hist[-1]):
        macd_score = 1.0 if hist[-1] > 0 else -1.0

    rsi_vals = calculate_rsi(closes, 14)
    rsi_score = 0.0
    rsi_val = rsi_vals[-1] if rsi_vals and not math.isnan(rsi_vals[-1]) else 50.0
    if rsi_val <= 30:
        rsi_score = 0.8
    elif rsi_val >= 70:
        rsi_score = -0.8

    # Volume score: relative volume vs 20-bar avg
    volumes = [c.volume for c in candles]
    avg_vol = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 1.0
    rel_vol = volumes[-1] / (avg_vol + 1e-9)
    vol_score = min(1.0, max(-1.0, (rel_vol - 1.0)))

    composite = (
        w_ema * ema_score
        + w_macd * macd_score
        + w_rsi * rsi_score
        + w_vol * vol_score * (1 if ema_score > 0 else -1)
    )
    composite = max(-1.0, min(1.0, composite))

    atr = calculate_atr(candles, 14)
    conf = round(abs(composite), 4)

    if composite > 0.5:
        sl, tp = _sl_tp("long", entry, atr, float(p.get("atr_sl", 1.5)), float(p.get("atr_tp", 3.0)))
        return StrategySignal("long", conf, f"combined={composite:.3f} rsi={rsi_val:.1f}", round(entry, 8), round(sl, 8), round(tp, 8), {"ema_score": ema_score, "macd_score": macd_score, "rsi": round(rsi_val, 2), "composite": round(composite, 4)})
    if composite < -0.5:
        sl, tp = _sl_tp("short", entry, atr, float(p.get("atr_sl", 1.5)), float(p.get("atr_tp", 3.0)))
        return StrategySignal("short", conf, f"combined={composite:.3f} rsi={rsi_val:.1f}", round(entry, 8), round(sl, 8), round(tp, 8), {"ema_score": ema_score, "macd_score": macd_score, "rsi": round(rsi_val, 2), "composite": round(composite, 4)})

    return StrategySignal("flat", conf, f"combined={composite:.3f} below threshold", entry, 0.0, 0.0, {"ema_score": ema_score, "rsi": round(rsi_val, 2), "composite": round(composite, 4)})


_DISPATCH: dict[str, Any] = {
    "trend_follow": _trend_follow,
    "rsi_reversal": _rsi_reversal,
    "macd_momentum": _macd_momentum,
    "breakout": _breakout,
    "combined": _combined,
}


def run_strategy(
    name: str,
    candles: list[CryptoCandle],
    params: dict[str, Any] | None = None,
) -> StrategySignal:
    """Run a named strategy on the given candles and return a signal.

    Args:
        name: Strategy identifier (one of list_strategies() names).
        candles: OHLCV candles ordered oldest → newest.
        params: Optional parameter overrides (merged with defaults).

    Returns:
        StrategySignal.
    """
    fn = _DISPATCH.get(name)
    if fn is None:
        raise ValueError(f"Unknown strategy: {name!r}. Available: {list(_DISPATCH)}")

    meta = next((s for s in _STRATEGIES if s.name == name), None)
    merged = dict(meta.default_params) if meta else {}
    if params:
        merged.update(params)

    return fn(candles, merged)


# ---------------------------------------------------------------------------
# Backtesting
# ---------------------------------------------------------------------------

def backtest(
    name: str,
    candles: list[CryptoCandle],
    params: dict[str, Any] | None = None,
    initial_balance: float = 1000.0,
    position_pct: float = 0.95,
    min_confidence: float = 0.60,
) -> BacktestResult:
    """Walk-forward backtest of a strategy over `candles`.

    Rules:
        - Only one position at a time.
        - Entry when signal confidence >= min_confidence.
        - Exit on SL hit, TP hit, or opposing signal.
        - No slippage or fees modelled (conservative — real results will be lower).
        - Position size = position_pct × balance (e.g. 95% of equity).

    Args:
        name: Strategy name.
        candles: Full OHLCV history, oldest first.
        params: Strategy parameters.
        initial_balance: Starting balance in USD.
        position_pct: Fraction of balance used per trade (default 0.95).
        min_confidence: Minimum signal confidence to enter (default 0.60).

    Returns:
        BacktestResult with full metrics and equity curve.
    """
    meta = next((s for s in _STRATEGIES if s.name == name), None)
    merged = dict(meta.default_params) if meta else {}
    if params:
        merged.update(params)

    fn = _DISPATCH.get(name)
    if fn is None:
        raise ValueError(f"Unknown strategy: {name!r}")

    balance = initial_balance
    equity_curve: list[float] = [balance]
    trades: list[BacktestTrade] = []

    # Need at least 60 candles to warm up indicators
    warmup = 60
    if len(candles) < warmup + 10:
        return BacktestResult(
            strategy=name, symbol="unknown", candle_count=len(candles),
            initial_balance=initial_balance, final_balance=initial_balance,
            total_return_pct=0.0, trades=[], win_rate=0.0, max_drawdown_pct=0.0,
            sharpe_ratio=0.0, profit_factor=0.0, avg_trade_pct=0.0, equity_curve=[initial_balance],
        )

    position: dict | None = None

    for i in range(warmup, len(candles)):
        window = candles[: i + 1]
        current = candles[i]
        price = current.close

        # --- Check if existing position should be exited ---
        if position is not None:
            hit_sl = (
                (position["direction"] == "long" and price <= position["sl"]) or
                (position["direction"] == "short" and price >= position["sl"])
            )
            hit_tp = (
                (position["direction"] == "long" and price >= position["tp"]) or
                (position["direction"] == "short" and price <= position["tp"])
            )
            exit_reason = None
            if hit_sl:
                exit_reason = "sl_hit"
            elif hit_tp:
                exit_reason = "tp_hit"

            if exit_reason:
                entry_p = position["entry"]
                size = position["size"]
                if position["direction"] == "long":
                    pnl_pct = (price - entry_p) / entry_p
                else:
                    pnl_pct = (entry_p - price) / entry_p
                pnl_usd = size * pnl_pct
                balance += pnl_usd
                trades.append(BacktestTrade(
                    direction=position["direction"],
                    entry_price=entry_p,
                    exit_price=price,
                    entry_idx=position["idx"],
                    exit_idx=i,
                    pnl_pct=round(pnl_pct * 100, 4),
                    pnl_usd=round(pnl_usd, 4),
                    size_usd=round(size, 4),
                    reason=exit_reason,
                ))
                position = None
                equity_curve.append(round(balance, 4))
                continue

        # --- Try to enter new position ---
        if position is None and balance > 10:
            sig = fn(window, merged)
            if sig.direction != "flat" and sig.confidence >= min_confidence and sig.stop_loss > 0 and sig.take_profit > 0:
                # Validate SL/TP sanity
                valid = True
                if sig.direction == "long" and (sig.stop_loss >= price or sig.take_profit <= price):
                    valid = False
                if sig.direction == "short" and (sig.stop_loss <= price or sig.take_profit >= price):
                    valid = False
                if valid:
                    size = balance * position_pct
                    position = {
                        "direction": sig.direction,
                        "entry": price,
                        "sl": sig.stop_loss,
                        "tp": sig.take_profit,
                        "size": size,
                        "idx": i,
                    }

        equity_curve.append(round(balance, 4))

    # Close any open position at last price
    if position is not None:
        price = candles[-1].close
        entry_p = position["entry"]
        size = position["size"]
        if position["direction"] == "long":
            pnl_pct = (price - entry_p) / entry_p
        else:
            pnl_pct = (entry_p - price) / entry_p
        pnl_usd = size * pnl_pct
        balance += pnl_usd
        trades.append(BacktestTrade(
            direction=position["direction"],
            entry_price=entry_p,
            exit_price=price,
            entry_idx=position["idx"],
            exit_idx=len(candles) - 1,
            pnl_pct=round(pnl_pct * 100, 4),
            pnl_usd=round(pnl_usd, 4),
            size_usd=round(size, 4),
            reason="end_of_data",
        ))
        equity_curve.append(round(balance, 4))

    # --- Metrics ---
    total_return_pct = (balance - initial_balance) / initial_balance * 100
    wins = [t for t in trades if t.pnl_usd > 0]
    losses = [t for t in trades if t.pnl_usd <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0

    # Max drawdown
    peak = equity_curve[0]
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Sharpe (daily returns approximation)
    if len(equity_curve) > 1:
        rets = [(equity_curve[i] - equity_curve[i - 1]) / (equity_curve[i - 1] + 1e-9)
                for i in range(1, len(equity_curve))]
        avg_ret = sum(rets) / len(rets)
        std_ret = math.sqrt(sum((r - avg_ret) ** 2 for r in rets) / len(rets)) if len(rets) > 1 else 1e-9
        sharpe = (avg_ret / (std_ret + 1e-9)) * math.sqrt(252) if std_ret > 0 else 0.0
    else:
        sharpe = 0.0

    gross_profit = sum(t.pnl_usd for t in wins)
    gross_loss = abs(sum(t.pnl_usd for t in losses))
    profit_factor = gross_profit / (gross_loss + 1e-9)

    avg_trade_pct = sum(t.pnl_pct for t in trades) / len(trades) if trades else 0.0

    return BacktestResult(
        strategy=name,
        symbol=candles[0].symbol if candles else "unknown",
        candle_count=len(candles),
        initial_balance=initial_balance,
        final_balance=round(balance, 4),
        total_return_pct=round(total_return_pct, 4),
        trades=trades,
        win_rate=round(win_rate, 2),
        max_drawdown_pct=round(max_dd, 4),
        sharpe_ratio=round(sharpe, 4),
        profit_factor=round(profit_factor, 4),
        avg_trade_pct=round(avg_trade_pct, 4),
        equity_curve=equity_curve,
    )
