"""
core/polymarket_backtest.py — Historical backtesting engine for the Polymarket strategy.

Fetches resolved binary markets from Gamma API, reconstructs entry prices from CLOB
price history (price ~14 days before resolution), scores each market, simulates
entries above a configurable score threshold, and computes performance metrics.

Without AI (use_ai=False, default): tests liquidity + time dimensions only —
    fast, free, shows structural alpha from market selection.
With AI (use_ai=True): calls estimate_market_probability on each market question —
    validates the full 5-dimension engine; slower and uses API credits.

Public API:
    run_backtest(lookback_days, min_volume_usd, min_score, bankroll_usd,
                 max_position_usd, max_markets, use_ai) -> BacktestResult
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

import httpx

from core.logger import logger
from core.polymarket_score import score_market, DEFAULT_WEIGHTS
from core.polymarket_types import Market

_GAMMA = "https://gamma-api.polymarket.com"
_CLOB = "https://clob.polymarket.com"

# Simulate entry this many days before resolution; if market is shorter, use midpoint
_ENTRY_DAYS_BEFORE_END = 14
_HTTP_TIMEOUT = 8.0


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class BacktestTrade:
    condition_id: str
    question: str
    category: str
    entry_price: float          # YES probability at entry point
    direction: str              # "yes" | "no"
    size_usd: float
    score: float
    resolved_yes: bool
    pnl_usd: float
    entry_days_before_end: float
    roi_pct: float
    score_components: dict      # edge, liquidity, time_decay, copy_signal, news


@dataclass
class BacktestResult:
    lookback_days: int
    min_score: float
    bankroll_usd: float
    markets_evaluated: int
    markets_traded: int
    wins: int
    win_rate: float             # fraction [0, 1]
    total_pnl_usd: float
    roi_pct: float              # total_pnl / bankroll * 100
    max_drawdown_pct: float     # max peak-to-trough drop in equity
    sharpe_ratio: float         # simplified per-trade Sharpe (annualised N/A)
    avg_score: float            # avg score of traded markets
    use_ai: bool
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[dict] = field(default_factory=list)  # [{date, equity}]
    by_category: list[dict] = field(default_factory=list)
    errors: int = 0
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_iso(s: str) -> datetime | None:
    """Parse ISO 8601 date string to aware UTC datetime, returning None on failure."""
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S+00:00", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s[:26], fmt[:len(s[:26])])
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        # fromisoformat fallback (Python 3.11+)
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _entry_price_from_history(
    token_id: str,
    end_dt: datetime,
    client: httpx.Client,
) -> tuple[float, float] | None:
    """Fetch YES token price history and return (entry_price, days_before_end).

    Entry point is the data point closest to end_dt - _ENTRY_DAYS_BEFORE_END.
    Falls back to earliest available point if the market was open < 14 days.

    Returns None if history is empty or the API call fails.
    """
    try:
        r = client.get(
            f"{_CLOB}/prices-history",
            params={"market": token_id, "interval": "max", "fidelity": "60"},
            timeout=_HTTP_TIMEOUT,
        )
        if not r.is_success:
            return None
        history = r.json().get("history", [])
        if not history:
            return None
    except Exception as exc:
        logger.debug("_entry_price_from_history(%s): %s", token_id[:12], exc)
        return None

    # history items: {t: unix_seconds, p: price_0_to_1}
    target_ts = (end_dt - timedelta(days=_ENTRY_DAYS_BEFORE_END)).timestamp()

    best = min(history, key=lambda h: abs(h["t"] - target_ts))
    entry_ts = best["t"]
    entry_price = float(best["p"])
    days_before_end = (end_dt.timestamp() - entry_ts) / 86400.0

    return entry_price, days_before_end


def _pnl(direction: str, size_usd: float, entry_price: float, resolved_yes: bool) -> float:
    """Compute PnL for a binary Polymarket bet.

    Polymarket payout model:
        Buy YES at price p  → receive (size/p) tokens → pays $1 each if YES
        Buy NO  at price q  → receive (size/q) tokens → pays $1 each if NO

    Args:
        direction: "yes" or "no".
        size_usd: Amount wagered.
        entry_price: YES probability at entry (0–1).
        resolved_yes: True if the market resolved YES.

    Returns:
        Realised PnL in USD.
    """
    if direction == "yes":
        if resolved_yes:
            return round(size_usd * (1.0 - entry_price) / max(entry_price, 1e-6), 4)
        return round(-size_usd, 4)
    else:  # direction == "no"
        no_price = 1.0 - entry_price
        if not resolved_yes:
            return round(size_usd * (1.0 - no_price) / max(no_price, 1e-6), 4)
        return round(-size_usd, 4)


def _max_drawdown(equity_curve: list[float]) -> float:
    """Compute maximum peak-to-trough drawdown as a fraction [0, 1]."""
    if len(equity_curve) < 2:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        if e > peak:
            peak = e
        dd = (peak - e) / max(peak, 1e-6)
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 6)


def _sharpe(returns: list[float]) -> float:
    """Compute simplified Sharpe ratio from per-trade return fractions.

    Uses mean/std of per-trade ROI (no annualisation since trade frequency
    is irregular). Returns 0.0 if fewer than 2 trades or zero std.
    """
    if len(returns) < 2:
        return 0.0
    n = len(returns)
    mu = sum(returns) / n
    var = sum((r - mu) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(var)
    return round(mu / std, 4) if std > 1e-9 else 0.0


def _by_category_stats(trades: list[BacktestTrade]) -> list[dict]:
    cats: dict[str, list[BacktestTrade]] = {}
    for t in trades:
        cats.setdefault(t.category or "uncategorised", []).append(t)
    result = []
    for cat, ts in sorted(cats.items(), key=lambda kv: -len(kv[1])):
        wins = sum(1 for t in ts if t.pnl_usd > 0)
        total_pnl = sum(t.pnl_usd for t in ts)
        result.append({
            "category": cat,
            "trades": len(ts),
            "wins": wins,
            "win_rate": round(wins / len(ts), 4),
            "total_pnl_usd": round(total_pnl, 2),
        })
    return result


# ---------------------------------------------------------------------------
# Gamma API helpers
# ---------------------------------------------------------------------------

def _fetch_resolved_markets(
    lookback_days: int,
    min_volume_usd: float,
    max_markets: int,
    client: httpx.Client,
) -> list[dict]:
    """Return resolved binary markets from Gamma closed in the past lookback_days."""
    since_ts = time.time() - lookback_days * 86400
    since_iso = datetime.fromtimestamp(since_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    markets: list[dict] = []
    offset = 0
    limit = min(100, max_markets * 3)  # over-fetch to account for filtering

    while len(markets) < max_markets * 3:
        try:
            r = client.get(
                f"{_GAMMA}/markets",
                params={
                    "closed": "true",
                    "active": "false",
                    "limit": limit,
                    "offset": offset,
                    "order": "endDate",
                    "ascending": "false",
                    "end_date_min": since_iso,
                },
                timeout=_HTTP_TIMEOUT,
            )
            if not r.is_success:
                logger.warning("_fetch_resolved_markets: Gamma returned %d", r.status_code)
                break
            batch = r.json()
            if not batch:
                break
            markets.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
        except Exception as exc:
            logger.warning("_fetch_resolved_markets: %s", exc)
            break

    # Filter: binary markets, sufficient volume, valid clobTokenIds
    filtered = []
    for m in markets:
        try:
            import json as _json
            outcomes = _json.loads(m.get("outcomes", "[]")) if isinstance(m.get("outcomes"), str) else (m.get("outcomes") or [])
            clob_ids = _json.loads(m.get("clobTokenIds", "[]")) if isinstance(m.get("clobTokenIds"), str) else (m.get("clobTokenIds") or [])
            outcome_prices = _json.loads(m.get("outcomePrices", "[]")) if isinstance(m.get("outcomePrices"), str) else (m.get("outcomePrices") or [])

            if len(outcomes) != 2 or len(clob_ids) < 1:
                continue  # only binary markets
            if float(m.get("volume", 0) or 0) < min_volume_usd:
                continue
            if not m.get("conditionId"):
                continue
            end_dt = _parse_iso(m.get("endDate", ""))
            if end_dt is None:
                continue

            # Determine resolution: outcomePrices[0] ≈ 1.0 means YES won
            if not outcome_prices:
                continue
            yes_final = float(outcome_prices[0])
            resolved_yes = yes_final > 0.5

            filtered.append({
                "condition_id": m["conditionId"],
                "question": m.get("question", ""),
                "category": (m.get("category") or m.get("tags") or [""])[0] if isinstance(m.get("tags"), list) else (m.get("category") or ""),
                "volume": float(m.get("volume", 0) or 0),
                "volume_24h": float(m.get("volume24hr", 0) or 0),
                "end_dt": end_dt,
                "end_date_iso": m.get("endDate", ""),
                "clob_token_id": str(clob_ids[0]),   # YES token
                "resolved_yes": resolved_yes,
            })
        except Exception as exc:
            logger.debug("_fetch_resolved_markets filter: %s — %s", m.get("conditionId", "?"), exc)

    # Deduplicate by condition_id, return at most max_markets
    seen: set[str] = set()
    deduped = []
    for m in filtered:
        if m["condition_id"] not in seen:
            seen.add(m["condition_id"])
            deduped.append(m)
        if len(deduped) >= max_markets:
            break

    return deduped


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

def run_backtest(
    lookback_days: int = 30,
    min_volume_usd: float = 10_000.0,
    min_score: float = 50.0,
    bankroll_usd: float = 1_000.0,
    max_position_usd: float = 50.0,
    max_markets: int = 50,
    use_ai: bool = False,
) -> BacktestResult:
    """Run a historical backtest on resolved Polymarket binary markets.

    For each resolved market in the lookback window:
    1. Fetch YES token price at ~14 days before resolution from CLOB history.
    2. Score the market (scoring engine, no AI edge by default).
    3. If score >= min_score: simulate an entry (fixed fraction sizing).
    4. Resolve the trade against the actual outcome.
    5. Aggregate metrics.

    Args:
        lookback_days: How many days of resolved markets to evaluate.
        min_volume_usd: Minimum lifetime volume to include a market.
        min_score: Composite score threshold to simulate an entry.
        bankroll_usd: Starting bankroll for sizing.
        max_position_usd: Hard cap per position.
        max_markets: Maximum markets to evaluate (limits API calls).
        use_ai: Whether to call estimate_market_probability per market.
                Adds ~1–3 s and API cost per market. Default False.

    Returns:
        BacktestResult with all metrics and per-trade breakdown.
    """
    t0 = time.time()
    logger.info(
        "run_backtest: lookback=%dd min_score=%.0f bankroll=$%.0f max_markets=%d use_ai=%s",
        lookback_days, min_score, bankroll_usd, max_markets, use_ai,
    )

    result = BacktestResult(
        lookback_days=lookback_days,
        min_score=min_score,
        bankroll_usd=bankroll_usd,
        markets_evaluated=0,
        markets_traded=0,
        wins=0,
        win_rate=0.0,
        total_pnl_usd=0.0,
        roi_pct=0.0,
        max_drawdown_pct=0.0,
        sharpe_ratio=0.0,
        avg_score=0.0,
        use_ai=use_ai,
    )

    with httpx.Client() as client:
        gamma_markets = _fetch_resolved_markets(lookback_days, min_volume_usd, max_markets, client)
        logger.info("run_backtest: %d resolved markets fetched from Gamma", len(gamma_markets))

        result.markets_evaluated = len(gamma_markets)
        if not gamma_markets:
            result.duration_seconds = round(time.time() - t0, 2)
            return result

        trades: list[BacktestTrade] = []
        errors = 0

        for gm in gamma_markets:
            try:
                end_dt: datetime = gm["end_dt"]
                token_id: str = gm["clob_token_id"]

                # --- Get entry price from CLOB history ---
                hist_result = _entry_price_from_history(token_id, end_dt, client)
                if hist_result is None:
                    logger.debug("run_backtest: no history for %s — skip", gm["condition_id"][:16])
                    continue

                entry_price, days_before_end = hist_result

                # Clamp to (0.02, 0.98) to avoid extreme Kelly / division by zero
                entry_price = min(max(entry_price, 0.02), 0.98)

                # --- Build Market object ---
                market = Market(
                    condition_id=gm["condition_id"],
                    token_id=token_id,
                    question=gm["question"],
                    end_date_iso=gm["end_date_iso"],
                    volume_24h=gm["volume_24h"],
                    spread_pct=0.02,  # assume 2 % spread (historical — no live book)
                    days_to_resolution=days_before_end,
                    yes_price=entry_price,
                    category=gm["category"],
                )

                # --- Score market (no copy signal, no context) ---
                api_key = None
                try:
                    ms = score_market(
                        market=market,
                        copy_signal=None,
                        context="",
                        order_book=None,
                        api_key=api_key if use_ai else None,
                    )
                    # If not use_ai, zero out edge component to avoid stale AI calls
                    if not use_ai:
                        from dataclasses import replace
                        ms = replace(ms, edge=0.0, fair_prob=None,
                                     total=round(
                                         DEFAULT_WEIGHTS["w_liquidity"] * ms.liquidity
                                         + DEFAULT_WEIGHTS["w_time"] * ms.time_decay
                                         + DEFAULT_WEIGHTS["w_news"] * ms.news_sentiment,
                                         2,
                                     ))
                except Exception as exc:
                    logger.debug("run_backtest: score_market failed for %s: %s", gm["condition_id"][:16], exc)
                    errors += 1
                    continue

                if ms.total < min_score:
                    continue

                # --- Determine direction ---
                if use_ai and ms.fair_prob is not None:
                    direction = "yes" if ms.fair_prob > entry_price else "no"
                else:
                    # Without AI: buy YES on underdog markets (entry_price < 0.35)
                    # These markets have +EV if market underestimates true probability
                    direction = "yes" if entry_price < 0.35 else ("no" if entry_price > 0.65 else None)

                if direction is None:
                    continue  # skip markets near 50% without AI

                # --- Sizing: flat fractional (5% of bankroll, capped) ---
                size_usd = min(bankroll_usd * 0.05, max_position_usd)

                # --- Compute PnL ---
                resolved_yes: bool = gm["resolved_yes"]
                trade_pnl = _pnl(direction, size_usd, entry_price, resolved_yes)
                roi_pct = round(trade_pnl / size_usd * 100.0, 2)

                trades.append(BacktestTrade(
                    condition_id=gm["condition_id"],
                    question=gm["question"][:120],
                    category=gm["category"] or "uncategorised",
                    entry_price=round(entry_price, 4),
                    direction=direction,
                    size_usd=round(size_usd, 2),
                    score=round(ms.total, 2),
                    resolved_yes=resolved_yes,
                    pnl_usd=trade_pnl,
                    entry_days_before_end=round(days_before_end, 1),
                    roi_pct=roi_pct,
                    score_components={
                        "edge": ms.edge,
                        "liquidity": ms.liquidity,
                        "time_decay": ms.time_decay,
                        "copy_signal": ms.copy_signal,
                        "news": ms.news_sentiment,
                    },
                ))

            except Exception as exc:
                logger.warning("run_backtest: error processing %s: %s", gm.get("condition_id", "?")[:16], exc)
                errors += 1

    # --- Aggregate metrics ---
    result.errors = errors
    result.markets_traded = len(trades)
    result.trades = trades

    if trades:
        wins = [t for t in trades if t.pnl_usd > 0]
        result.wins = len(wins)
        result.win_rate = round(len(wins) / len(trades), 4)
        result.total_pnl_usd = round(sum(t.pnl_usd for t in trades), 2)
        result.roi_pct = round(result.total_pnl_usd / bankroll_usd * 100.0, 2)
        result.avg_score = round(sum(t.score for t in trades) / len(trades), 2)

        # Equity curve (sequential: assume one position at a time, bankroll replenishes)
        equity = bankroll_usd
        equity_vals: list[float] = [equity]
        eq_curve: list[dict] = []
        for i, t in enumerate(trades):
            equity += t.pnl_usd
            equity_vals.append(equity)
            eq_curve.append({"trade": i + 1, "equity": round(equity, 2), "question": t.question[:60]})
        result.equity_curve = eq_curve
        result.max_drawdown_pct = round(_max_drawdown(equity_vals) * 100.0, 2)

        per_trade_returns = [t.pnl_usd / t.size_usd for t in trades]
        result.sharpe_ratio = _sharpe(per_trade_returns)

        result.by_category = _by_category_stats(trades)

    result.duration_seconds = round(time.time() - t0, 2)
    logger.info(
        "run_backtest: done — %d traded / %d evaluated — win_rate=%.1f%% pnl=$%.2f in %.1fs",
        result.markets_traded, result.markets_evaluated,
        result.win_rate * 100, result.total_pnl_usd, result.duration_seconds,
    )
    return result
