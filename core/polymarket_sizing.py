"""
core/polymarket_sizing.py — Position sizing from Kelly risk decision.

Public API:
    size_position(risk_decision, bankroll_usd, max_position_usd) -> float
"""

from __future__ import annotations

from core.polymarket_risk import RiskDecision


def size_position(
    risk_decision: RiskDecision,
    bankroll_usd: float,
    max_position_usd: float = 100.0,
) -> float:
    """Compute the USD position size from a RiskDecision.

    Returns 0.0 if the trade was rejected. Otherwise applies:
        size = min(kelly_fraction * bankroll, max_position_usd)

    Args:
        risk_decision: Output of assess_risk().
        bankroll_usd: Total available USDC balance.
        max_position_usd: Hard cap per position (from config).

    Returns:
        Position size in USD, rounded to 2 decimal places.
    """
    if not risk_decision.approved or risk_decision.kelly <= 0.0:
        return 0.0
    size = min(risk_decision.kelly * bankroll_usd, max_position_usd)
    return round(max(0.0, size), 2)
