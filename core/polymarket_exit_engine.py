"""
core/polymarket_exit_engine.py — Five-rule exit decision engine.

Rules (evaluated in priority order):
    1. Take-profit   — unrealized PnL ≥ +50%
    2. Stop-loss     — unrealized PnL ≤ -30%
    3. Time-stop     — <2 days to resolution AND no meaningful movement
    4. Score-inversion — AI score dropped >30 points since entry
    5. Resolution-hold — let position settle if still positive edge

Public API:
    should_exit(position, monitor_status, config, current_score) -> ExitDecision
"""

from __future__ import annotations

from dataclasses import dataclass

from core.polymarket_monitor import PositionStatus
from core.polymarket_types import Position

_TAKE_PROFIT_PCT = 0.50
_STOP_LOSS_PCT = -0.30
_TIME_STOP_DAYS = 2.0
_TIME_STOP_MOVEMENT_THRESHOLD = 0.02
_SCORE_DROP_THRESHOLD = 30.0


@dataclass(frozen=True)
class ExitDecision:
    should_exit: bool
    rule: str          # which rule triggered (or "none")
    reason: str


def should_exit(
    position: Position,
    status: PositionStatus,
    config: object,
    current_score: float | None = None,
    entry_score: float | None = None,
) -> ExitDecision:
    """Evaluate whether to exit a position using five ordered rules.

    Rule priority:
    1. Take-profit: unrealized_pct ≥ +50% → exit
    2. Stop-loss: unrealized_pct ≤ -30% → exit
    3. Time-stop: days_to_resolution < 2 AND |current_price - entry_price| < 2% → exit
    4. Score-inversion: AI score dropped > 30 points since entry → exit
    5. Resolution-hold: if still positive edge → hold (do NOT exit early)

    Args:
        position: Current Position dataclass.
        status: PositionStatus from monitor_positions().
        config: OperationalConfig with polymarket_ settings.
        current_score: Optional current composite score (0–100).
        entry_score: Optional score at position entry.

    Returns:
        ExitDecision(should_exit, rule, reason).
    """
    if status.unrealized_pct >= _TAKE_PROFIT_PCT:
        return ExitDecision(
            should_exit=True,
            rule="take_profit",
            reason=f"Take-profit triggered: {status.unrealized_pct:.1%} gain",
        )

    if status.unrealized_pct <= _STOP_LOSS_PCT:
        return ExitDecision(
            should_exit=True,
            rule="stop_loss",
            reason=f"Stop-loss triggered: {status.unrealized_pct:.1%} loss",
        )

    if status.days_to_resolution < _TIME_STOP_DAYS:
        _entry = position.entry_price if position is not None else status.entry_price
        movement = abs(status.current_price - _entry)
        if movement < _TIME_STOP_MOVEMENT_THRESHOLD:
            return ExitDecision(
                should_exit=True,
                rule="time_stop",
                reason=f"Time-stop: {status.days_to_resolution:.1f} days left, price stuck",
            )

    if current_score is not None and entry_score is not None:
        drop = entry_score - current_score
        if drop > _SCORE_DROP_THRESHOLD:
            return ExitDecision(
                should_exit=True,
                rule="score_inversion",
                reason=f"Score dropped {drop:.0f} points (entry={entry_score:.0f}, now={current_score:.0f})",
            )

    if status.unrealized_pct > 0.0:
        return ExitDecision(
            should_exit=False,
            rule="resolution_hold",
            reason="Positive edge remains — holding to resolution",
        )

    return ExitDecision(
        should_exit=False,
        rule="none",
        reason="No exit rule triggered",
    )
