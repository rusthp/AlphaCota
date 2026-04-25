"""
core/polymarket_score.py — Market scoring for Polymarket opportunities.

Composite score (0–100) weighted across five dimensions:
    edge        (35%) — AI-estimated probability vs market price
    liquidity   (25%) — order book depth and 24 h volume
    time        (15%) — days to resolution relative to ideal window (7–30 days)
    copy        (15%) — consensus signal from top alpha wallets
    news        (10%) — AI sentiment from recent context

Public API:
    score_market(market, copy_signal, context, weights) -> MarketScore
"""

from __future__ import annotations

from dataclasses import dataclass

from core.ai_engine import estimate_market_probability
from core.logger import logger
from core.polymarket_types import CopySignal, Market, OrderBook

DEFAULT_WEIGHTS: dict[str, float] = {
    "w_edge": 0.35,
    "w_liquidity": 0.25,
    "w_time": 0.15,
    "w_copy": 0.15,
    "w_news": 0.10,
}

# At module load, try to use learned weights from the last tuning cycle.
# Falls back to DEFAULT_WEIGHTS when the file is absent or invalid.
def _load_active_weights() -> dict[str, float]:
    try:
        from core.polymarket_weight_tuner import load_learned_weights
        learned = load_learned_weights()
        if learned is not None:
            # Validate that all required keys are present
            if all(k in learned for k in DEFAULT_WEIGHTS):
                logger.info("polymarket_score: using learned weights from disk")
                return learned
            logger.warning("polymarket_score: learned weights missing keys — using defaults")
    except Exception as exc:
        logger.debug("polymarket_score: could not load learned weights: %s", exc)
    return dict(DEFAULT_WEIGHTS)


ACTIVE_WEIGHTS: dict[str, float] = _load_active_weights()


@dataclass(frozen=True)
class MarketScore:
    condition_id: str
    total: float           # 0–100 composite score
    edge: float            # 0–100
    liquidity: float       # 0–100
    time_decay: float      # 0–100
    copy_signal: float     # 0–100
    news_sentiment: float  # 0–100
    fair_prob: float | None  # AI estimate (None if unavailable)
    market_prob: float     # market YES price at scoring time
    weights: dict[str, float]


def validate_weights(weights: dict[str, float]) -> None:
    """Raise ValueError if weights do not sum to 1.0 (±0.001).

    Args:
        weights: Weight dictionary with keys matching DEFAULT_WEIGHTS.
    """
    total = sum(weights.values())
    if abs(total - 1.0) > 0.001:
        raise ValueError(f"Weights must sum to 1.0, got {total:.4f}")
    for key in DEFAULT_WEIGHTS:
        if key not in weights:
            raise ValueError(f"Missing weight key: {key}")


def _edge_score(fair_prob: float | None, market_prob: float) -> float:
    """Convert AI probability estimate to an edge score (0–100).

    If fair_prob is None (AI unavailable), returns 0 — no edge signal means
    no trade, not a blocker. Edge is symmetric: both over- and under-priced
    markets score positively; the direction is determined downstream.

    Args:
        fair_prob: AI-estimated true probability or None.
        market_prob: Current market probability (YES price).

    Returns:
        Edge score in [0, 100].
    """
    if fair_prob is None:
        return 0.0
    raw_edge = abs(fair_prob - market_prob)
    score = min(raw_edge / 0.20, 1.0) * 100.0
    return round(score, 2)


def _liquidity_score(order_book: OrderBook | None, volume_24h: float) -> float:
    """Compute liquidity score (0–100) from spread and volume.

    Penalises spreads above 5 percentage points and volumes below $5 k/day.
    A tight spread at high volume yields the maximum score.

    Args:
        order_book: Optional OrderBook (None if unavailable).
        volume_24h: 24-hour trading volume in USD.

    Returns:
        Liquidity score in [0, 100].
    """
    spread_score = 100.0
    if order_book is not None:
        spread_pct = order_book.spread_pct
        if spread_pct >= 0.10:
            spread_score = 0.0
        elif spread_pct >= 0.05:
            spread_score = (0.10 - spread_pct) / 0.05 * 50.0
        else:
            spread_score = 50.0 + (0.05 - spread_pct) / 0.05 * 50.0

    volume_score = 0.0
    if volume_24h >= 100_000:
        volume_score = 100.0
    elif volume_24h >= 5_000:
        volume_score = (volume_24h - 5_000) / 95_000 * 100.0
    else:
        volume_score = volume_24h / 5_000 * 30.0

    return round((spread_score + volume_score) / 2.0, 2)


def _time_decay_score(days_to_resolution: float) -> float:
    """Score market timing relative to ideal resolution window (7–30 days).

    Peak score (100) at 14 days. Harsh penalty for <2 days (too late to enter)
    or >180 days (too early, too much uncertainty).

    Args:
        days_to_resolution: Positive float of days remaining.

    Returns:
        Time score in [0, 100].
    """
    d = max(0.0, days_to_resolution)
    if d < 2.0:
        return 0.0
    if d > 180.0:
        return max(0.0, 100.0 - (d - 180.0) * 0.5)
    if 7.0 <= d <= 30.0:
        deviation = abs(d - 14.0) / 14.0
        return round(100.0 - deviation * 20.0, 2)
    if d < 7.0:
        return round((d - 2.0) / 5.0 * 80.0, 2)
    score = 80.0 - (d - 30.0) / 150.0 * 80.0
    return round(max(0.0, score), 2)


def _copy_signal_score(copy_signal: CopySignal | None) -> float:
    """Convert copy-trading consensus to a score (0–100).

    Uses confidence weighted by consensus_ratio. Returns 0 when direction
    is 'none' or copy_signal is None.

    Args:
        copy_signal: CopySignal dataclass or None.

    Returns:
        Copy score in [0, 100].
    """
    if copy_signal is None or copy_signal.direction == "none":
        return 0.0
    base = copy_signal.confidence * copy_signal.consensus_ratio * 100.0
    return round(min(base, 100.0), 2)


def score_market(
    market: Market,
    copy_signal: CopySignal | None = None,
    context: str = "",
    weights: dict[str, float] | None = None,
    order_book: OrderBook | None = None,
    api_key: str | None = None,
) -> MarketScore:
    """Compute composite market score.

    Calls estimate_market_probability for edge signal (returns 0 if AI is
    unavailable — no AI = no trade signal, not an error).

    Args:
        market: Polymarket Market dataclass.
        copy_signal: Optional wallet consensus signal.
        context: Optional news/macro context for AI probability estimation.
        weights: Optional weight overrides; defaults to DEFAULT_WEIGHTS.
        order_book: Optional pre-fetched OrderBook (saves an API call).
        api_key: Optional OpenRouter API key.

    Returns:
        MarketScore dataclass with all component scores and composite total.
    """
    w = weights if weights is not None else ACTIVE_WEIGHTS.copy()
    validate_weights(w)

    market_dict = {
        "question": market.question,
        "lastTradePrice": market.yes_price,
        "endDate": market.end_date_iso,
    }

    ai_result: dict | None = None
    try:
        ai_result = estimate_market_probability(market_dict, context=context, api_key=api_key)
    except Exception as exc:
        logger.warning("score_market: AI estimation failed: %s", exc)

    fair_prob = ai_result["fair_prob"] if ai_result else None
    edge = _edge_score(fair_prob, market.yes_price)
    liquidity = _liquidity_score(order_book, market.volume_24h)
    time_dec = _time_decay_score(market.days_to_resolution)
    copy_sc = _copy_signal_score(copy_signal)
    news_sc = float(ai_result.get("confidence", 0.5) * 100.0) if ai_result else 50.0

    total = (
        w["w_edge"] * edge
        + w["w_liquidity"] * liquidity
        + w["w_time"] * time_dec
        + w["w_copy"] * copy_sc
        + w["w_news"] * news_sc
    )

    return MarketScore(
        condition_id=market.condition_id,
        total=round(total, 2),
        edge=edge,
        liquidity=liquidity,
        time_decay=time_dec,
        copy_signal=copy_sc,
        news_sentiment=news_sc,
        fair_prob=fair_prob,
        market_prob=market.yes_price,
        weights=w,
    )
