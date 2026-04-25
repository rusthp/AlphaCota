"""tests/test_polymarket_exit_engine.py — Tests for exit engine rules."""

import time

import pytest

from core.polymarket_exit_engine import (
    ExitDecision,
    _SCORE_DROP_THRESHOLD,
    _STOP_LOSS_PCT,
    _TAKE_PROFIT_PCT,
    _TIME_STOP_DAYS,
    should_exit,
)
from core.polymarket_monitor import PositionStatus
from core.polymarket_types import Position


def _status(
    unrealized_pct: float = 0.0,
    days_to_resolution: float = 14.0,
    current_price: float = 0.55,
    entry_price: float = 0.50,
) -> PositionStatus:
    size_usd = 100.0
    unrealized_pnl = unrealized_pct * entry_price * size_usd
    return PositionStatus(
        position_id="pos-1",
        condition_id="cid1",
        direction="yes",
        size_usd=size_usd,
        entry_price=entry_price,
        current_price=current_price,
        unrealized_pnl=unrealized_pnl,
        unrealized_pct=unrealized_pct,
        should_take_profit=unrealized_pct >= _TAKE_PROFIT_PCT,
        should_stop_loss=unrealized_pct <= _STOP_LOSS_PCT,
        days_to_resolution=days_to_resolution,
    )


def _position(entry_price: float = 0.50) -> Position:
    return Position(
        position_id="pos-1",
        condition_id="cid1",
        token_id="tok1",
        direction="yes",
        size_usd=100.0,
        entry_price=entry_price,
        current_price=entry_price,
        unrealized_pnl=0.0,
        mode="paper",
        opened_at=time.time(),
    )


class _Config:
    polymarket_max_position_usd = 100.0
    polymarket_max_daily_loss_usd = 200.0


class TestTakeProfit:
    def test_fires_at_threshold(self):
        st = _status(unrealized_pct=_TAKE_PROFIT_PCT)
        ed = should_exit(_position(), st, _Config())
        assert ed.should_exit is True
        assert ed.rule == "take_profit"

    def test_fires_above_threshold(self):
        st = _status(unrealized_pct=0.80)
        ed = should_exit(_position(), st, _Config())
        assert ed.should_exit is True
        assert ed.rule == "take_profit"

    def test_does_not_fire_below_threshold(self):
        st = _status(unrealized_pct=0.40)
        ed = should_exit(_position(), st, _Config())
        assert ed.rule != "take_profit"


class TestStopLoss:
    def test_fires_at_threshold(self):
        st = _status(unrealized_pct=_STOP_LOSS_PCT)
        ed = should_exit(_position(), st, _Config())
        assert ed.should_exit is True
        assert ed.rule == "stop_loss"

    def test_fires_below_threshold(self):
        st = _status(unrealized_pct=-0.50)
        ed = should_exit(_position(), st, _Config())
        assert ed.should_exit is True
        assert ed.rule == "stop_loss"

    def test_does_not_fire_above_threshold(self):
        st = _status(unrealized_pct=-0.20)
        ed = should_exit(_position(), st, _Config())
        assert ed.rule != "stop_loss"


class TestTimeStop:
    def test_fires_near_resolution_with_stuck_price(self):
        st = _status(
            unrealized_pct=0.01,
            days_to_resolution=1.0,
            current_price=0.505,
            entry_price=0.500,
        )
        ed = should_exit(_position(entry_price=0.500), st, _Config())
        assert ed.should_exit is True
        assert ed.rule == "time_stop"

    def test_does_not_fire_with_significant_movement(self):
        st = _status(
            unrealized_pct=0.10,
            days_to_resolution=1.0,
            current_price=0.60,
            entry_price=0.50,
        )
        ed = should_exit(_position(entry_price=0.50), st, _Config())
        assert ed.rule != "time_stop"

    def test_does_not_fire_when_enough_days_remain(self):
        st = _status(
            unrealized_pct=0.01,
            days_to_resolution=5.0,
            current_price=0.501,
            entry_price=0.500,
        )
        ed = should_exit(_position(), st, _Config())
        assert ed.rule != "time_stop"


class TestScoreInversion:
    def test_fires_when_score_drops_above_threshold(self):
        st = _status(unrealized_pct=0.05)
        ed = should_exit(_position(), st, _Config(),
                         current_score=30.0, entry_score=30.0 + _SCORE_DROP_THRESHOLD + 1)
        assert ed.should_exit is True
        assert ed.rule == "score_inversion"

    def test_does_not_fire_below_threshold_drop(self):
        st = _status(unrealized_pct=0.05)
        ed = should_exit(_position(), st, _Config(),
                         current_score=50.0, entry_score=70.0)
        assert ed.rule != "score_inversion"

    def test_does_not_fire_without_scores(self):
        st = _status(unrealized_pct=0.05)
        ed = should_exit(_position(), st, _Config())
        assert ed.rule != "score_inversion"


class TestResolutionHold:
    def test_holds_when_positive_edge_remains(self):
        st = _status(unrealized_pct=0.10, days_to_resolution=14.0)
        ed = should_exit(_position(), st, _Config())
        assert ed.should_exit is False
        assert ed.rule == "resolution_hold"

    def test_no_exit_on_neutral_position(self):
        st = _status(unrealized_pct=0.0, days_to_resolution=14.0)
        ed = should_exit(_position(), st, _Config())
        assert ed.should_exit is False
