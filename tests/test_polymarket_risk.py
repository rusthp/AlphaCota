"""tests/test_polymarket_risk.py — Tests for polymarket_risk module."""

import time

import pytest

from core.polymarket_risk import (
    RiskDecision,
    _MAX_KELLY_CAP,
    _MAX_OPEN_POSITIONS,
    _MAX_SAME_CATEGORY,
    _MIN_SCORE_TO_TRADE,
    assess_risk,
    kelly_fraction,
)
from core.polymarket_score import MarketScore
from core.polymarket_types import WalletHealth


def _wallet(usdc: float = 500.0, healthy: bool = True) -> WalletHealth:
    return WalletHealth(
        address="0xABC",
        matic_balance=5.0,
        usdc_balance=usdc,
        usdc_allowance=usdc,
        is_healthy=healthy,
        checked_at=time.time(),
    )


def _score(
    condition_id: str = "cid1",
    total: float = 65.0,
    fair_prob: float | None = 0.70,
) -> MarketScore:
    return MarketScore(
        condition_id=condition_id,
        total=total,
        edge=80.0,
        liquidity=70.0,
        time_decay=60.0,
        copy_signal=40.0,
        news_sentiment=50.0,
        fair_prob=fair_prob,
        market_prob=0.45,
        weights={
            "w_edge": 0.35,
            "w_liquidity": 0.25,
            "w_time": 0.15,
            "w_copy": 0.15,
            "w_news": 0.10,
        },
    )


class _Config:
    polymarket_max_daily_loss_usd = 100.0
    polymarket_max_position_usd = 100.0


class TestKellyFraction:
    def test_positive_edge(self):
        f = kelly_fraction(0.70, 0.50)
        assert f > 0.0
        assert f <= _MAX_KELLY_CAP

    def test_zero_edge(self):
        f = kelly_fraction(0.50, 0.50)
        assert f == pytest.approx(0.0, abs=1e-5)

    def test_negative_edge_returns_zero(self):
        f = kelly_fraction(0.30, 0.50)
        assert f == 0.0

    def test_capped_at_max(self):
        f = kelly_fraction(0.99, 0.01)
        assert f == pytest.approx(_MAX_KELLY_CAP)

    def test_market_prob_edge_cases(self):
        assert kelly_fraction(0.7, 0.0) == 0.0
        assert kelly_fraction(0.7, 1.0) == 0.0

    def test_formula_correctness(self):
        p = 0.65
        mp = 0.50
        b = (1 - mp) / mp
        expected = min((p * b - (1 - p)) / b, _MAX_KELLY_CAP)
        assert kelly_fraction(p, mp) == pytest.approx(expected, rel=1e-4)


class TestAssessRisk:
    def test_approves_healthy_trade(self):
        rd = assess_risk(_score(), _wallet(), [], _Config())
        assert rd.approved is True
        assert rd.kelly > 0

    def test_rejects_unhealthy_wallet(self):
        rd = assess_risk(_score(), _wallet(healthy=False, usdc=0.0), [], _Config())
        assert rd.approved is False
        assert "Wallet" in rd.reason

    def test_rejects_low_usdc(self):
        rd = assess_risk(_score(), _wallet(usdc=5.0, healthy=False), [], _Config())
        assert rd.approved is False

    def test_rejects_low_score(self):
        rd = assess_risk(_score(total=25.0), _wallet(), [], _Config())
        assert rd.approved is False
        assert "Score" in rd.reason

    def test_rejects_no_fair_prob(self):
        rd = assess_risk(_score(fair_prob=None), _wallet(), [], _Config())
        assert rd.approved is False
        assert "probability" in rd.reason.lower()

    def test_rejects_max_positions_reached(self):
        open_pos = [{"category": "sports"} for _ in range(_MAX_OPEN_POSITIONS)]
        rd = assess_risk(_score(), _wallet(), open_pos, _Config())
        assert rd.approved is False
        assert "positions" in rd.reason.lower()

    def test_rejects_category_concentration(self):
        cat = "politics"
        open_pos = [{"category": cat} for _ in range(_MAX_SAME_CATEGORY)]
        score = _score()
        position_with_category = [{"condition_id": score.condition_id, "category": cat}] + open_pos
        rd = assess_risk(score, _wallet(), position_with_category, _Config())
        assert rd.approved is False
        assert "category" in rd.reason.lower()

    def test_rejects_zero_daily_loss_cap(self):
        class ZeroCap:
            polymarket_max_daily_loss_usd = 0.0
            polymarket_max_position_usd = 100.0

        rd = assess_risk(_score(), _wallet(), [], ZeroCap())
        assert rd.approved is False

    def test_kelly_is_capped(self):
        rd = assess_risk(_score(fair_prob=0.70), _wallet(), [], _Config())
        if rd.approved:
            assert rd.kelly <= _MAX_KELLY_CAP
