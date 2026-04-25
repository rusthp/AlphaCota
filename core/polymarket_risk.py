"""
core/polymarket_risk.py — Kelly criterion and risk gating for Polymarket trades.

Public API:
    kelly_fraction(fair_prob, market_prob) -> float
    assess_risk(score, wallet_health, open_positions, config) -> RiskDecision
"""

from __future__ import annotations

from dataclasses import dataclass

from core.polymarket_score import MarketScore
from core.polymarket_types import WalletHealth

_MAX_KELLY_CAP = 0.25
_MIN_SCORE_TO_TRADE = 40.0
_MAX_OPEN_POSITIONS = 5
_MAX_SAME_CATEGORY = 2
_MIN_USDC_BALANCE = 20.0


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    kelly: float        # Kelly fraction [0, _MAX_KELLY_CAP]
    reason: str
    category: str = ""


def kelly_fraction(fair_prob: float, market_prob: float) -> float:
    """Compute the full Kelly fraction for a binary Polymarket bet.

    Formula: f* = (p*b - q) / b  where b = (1 - market_prob) / market_prob.
    Result capped at _MAX_KELLY_CAP (0.25) and floored at 0.0.

    Args:
        fair_prob: AI-estimated true probability of YES resolution.
        market_prob: Current market price (probability) for YES.

    Returns:
        Kelly fraction in [0, 0.25]. Returns 0.0 for negative edge.
    """
    if market_prob <= 0.0 or market_prob >= 1.0:
        return 0.0
    b = (1.0 - market_prob) / market_prob
    q = 1.0 - fair_prob
    f_star = (fair_prob * b - q) / b
    return round(min(max(f_star, 0.0), _MAX_KELLY_CAP), 6)


def _count_by_category(open_positions: list[dict], category: str) -> int:
    """Count how many open positions are in the given category."""
    return sum(1 for p in open_positions if p.get("category", "").lower() == category.lower())


def assess_risk(
    score: MarketScore,
    wallet_health: WalletHealth,
    open_positions: list[dict],
    config: object,
) -> RiskDecision:
    """Gate a potential trade through risk rules and compute Kelly sizing.

    Rules checked (in order):
    1. Wallet must be healthy (USDC ≥ $20, allowance granted).
    2. Composite score must be ≥ MIN_SCORE_TO_TRADE (40).
    3. Must have an AI fair_prob estimate (edge signal required).
    4. Kelly fraction must be positive (real edge).
    5. Open position count must be < MAX_OPEN_POSITIONS (5).
    6. Category concentration must be < MAX_SAME_CATEGORY (2).
    7. Daily loss cap from config (polymarket_max_daily_loss_usd).

    Args:
        score: MarketScore from score_market().
        wallet_health: Current WalletHealth from get_wallet_health().
        open_positions: List of dicts with at minimum {"category": str}.
        config: OperationalConfig (or similar) with polymarket_max_daily_loss_usd
                and polymarket_max_position_usd attributes.

    Returns:
        RiskDecision(approved, kelly, reason).
    """
    if not wallet_health.is_healthy or wallet_health.usdc_balance < _MIN_USDC_BALANCE:
        return RiskDecision(
            approved=False,
            kelly=0.0,
            reason=f"Wallet unhealthy: USDC={wallet_health.usdc_balance:.2f}",
        )

    if score.total < _MIN_SCORE_TO_TRADE:
        return RiskDecision(
            approved=False,
            kelly=0.0,
            reason=f"Score {score.total:.1f} below threshold {_MIN_SCORE_TO_TRADE}",
        )

    if score.fair_prob is None:
        return RiskDecision(
            approved=False,
            kelly=0.0,
            reason="No AI probability estimate — cannot determine edge",
        )

    fair_prob = score.fair_prob
    market_prob = score.market_prob
    kelly = kelly_fraction(fair_prob, market_prob)

    if kelly <= 0.0:
        return RiskDecision(
            approved=False,
            kelly=0.0,
            reason=f"Negative Kelly ({kelly:.4f}) — no positive edge",
        )

    if len(open_positions) >= _MAX_OPEN_POSITIONS:
        return RiskDecision(
            approved=False,
            kelly=0.0,
            reason=f"Max open positions reached ({_MAX_OPEN_POSITIONS})",
        )

    category = getattr(score, "category", "")
    if not category:
        for pos in open_positions:
            if pos.get("condition_id") == score.condition_id:
                category = pos.get("category", "")
                break

    if category and _count_by_category(open_positions, category) >= _MAX_SAME_CATEGORY:
        return RiskDecision(
            approved=False,
            kelly=0.0,
            reason=f"Category concentration limit reached for '{category}'",
            category=category,
        )

    max_daily_loss = getattr(config, "polymarket_max_daily_loss_usd", 100.0)
    if max_daily_loss <= 0:
        return RiskDecision(
            approved=False,
            kelly=0.0,
            reason="Daily loss cap is zero — trading disabled",
        )

    return RiskDecision(
        approved=True,
        kelly=kelly,
        reason="All risk checks passed",
        category=category,
    )
