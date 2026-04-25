"""
core/polymarket_decision_engine.py — Pure trade decision orchestrator.

No I/O, no side effects. Receives markets and config; calls score → risk →
sizing per market and returns a ranked list of TradeDecisions.

Public API:
    generate_trade_decisions(markets, config, wallet_health, open_positions,
                             copy_signals, weights) -> list[TradeDecision]
"""

from __future__ import annotations

from core.logger import logger
from core.polymarket_risk import assess_risk
from core.polymarket_score import MarketScore, score_market
from core.polymarket_sizing import size_position
from core.polymarket_types import CopySignal, Market, TradeDecision, WalletHealth


def generate_trade_decisions(
    markets: list[Market],
    config: object,
    wallet_health: WalletHealth,
    open_positions: list[dict] | None = None,
    copy_signals: dict[str, CopySignal] | None = None,
    weights: dict[str, float] | None = None,
    api_key: str | None = None,
) -> list[TradeDecision]:
    """Score, risk-gate, and size each market into a ranked TradeDecision list.

    Markets that fail risk checks receive size_usd=0.0 and are excluded from
    the approved output. All markets are scored; only approved ones are returned
    sorted by composite score descending.

    Args:
        markets: Markets to evaluate (from discover_markets()).
        config: OperationalConfig with polymarket_max_position_usd,
                polymarket_max_daily_loss_usd, polymarket_mode.
        wallet_health: Current WalletHealth.
        open_positions: Existing open positions for concentration checks.
        copy_signals: Optional map of condition_id → CopySignal.
        weights: Optional scorer weight overrides.
        api_key: Optional OpenRouter API key for AI probability estimation.

    Returns:
        List of TradeDecision sorted by score descending. Rejected markets
        are omitted (size_usd would be 0).
    """
    positions = open_positions or []
    signals = copy_signals or {}
    max_pos_usd = float(getattr(config, "polymarket_max_position_usd", 100.0))
    bankroll = wallet_health.usdc_balance

    decisions: list[TradeDecision] = []

    for market in markets:
        copy_signal = signals.get(market.condition_id)
        try:
            market_score: MarketScore = score_market(
                market=market,
                copy_signal=copy_signal,
                weights=weights,
                api_key=api_key,
            )
        except Exception as exc:
            logger.warning("generate_trade_decisions: score failed for %s: %s", market.condition_id, exc)
            continue

        risk = assess_risk(
            score=market_score,
            wallet_health=wallet_health,
            open_positions=positions,
            config=config,
        )

        size = size_position(risk, bankroll, max_pos_usd)

        if not risk.approved or size <= 0.0:
            continue

        fair_prob = market_score.fair_prob or market.yes_price
        direction = "yes" if fair_prob > market.yes_price else "no"

        decisions.append(
            TradeDecision(
                condition_id=market.condition_id,
                token_id=market.token_id,
                direction=direction,
                size_usd=size,
                score=market_score.total,
                kelly_fraction=risk.kelly,
                reasoning=risk.reason,
            )
        )

    decisions.sort(key=lambda d: d.score, reverse=True)
    return decisions
