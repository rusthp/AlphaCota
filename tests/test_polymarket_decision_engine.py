"""tests/test_polymarket_decision_engine.py — Tests for decision engine."""

import time
from unittest.mock import patch

import pytest

from core.polymarket_decision_engine import generate_trade_decisions
from core.polymarket_risk import RiskDecision
from core.polymarket_score import MarketScore
from core.polymarket_types import CopySignal, Market, TradeDecision, WalletHealth


def _market(condition_id: str = "cid1", yes_price: float = 0.45) -> Market:
    return Market(
        condition_id=condition_id,
        token_id=f"tok-{condition_id}",
        question=f"Will {condition_id} happen?",
        end_date_iso="",
        volume_24h=50_000.0,
        spread_pct=0.02,
        days_to_resolution=14.0,
        yes_price=yes_price,
        category="politics",
    )


def _wallet(usdc: float = 500.0) -> WalletHealth:
    return WalletHealth(
        address="0xABC",
        matic_balance=5.0,
        usdc_balance=usdc,
        usdc_allowance=usdc,
        is_healthy=True,
        checked_at=time.time(),
    )


def _good_score(condition_id: str = "cid1", fair_prob: float = 0.70) -> MarketScore:
    return MarketScore(
        condition_id=condition_id,
        total=72.0,
        edge=80.0,
        liquidity=70.0,
        time_decay=60.0,
        copy_signal=50.0,
        news_sentiment=60.0,
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
    polymarket_max_position_usd = 100.0
    polymarket_max_daily_loss_usd = 200.0
    polymarket_mode = "paper"


class TestGenerateTradeDecisions:
    def test_returns_approved_decisions(self):
        markets = [_market("cid1"), _market("cid2")]
        good_risk = RiskDecision(approved=True, kelly=0.10, reason="ok")
        good_score = _good_score("cid1")

        with (
            patch("core.polymarket_decision_engine.score_market", return_value=good_score),
            patch("core.polymarket_decision_engine.assess_risk", return_value=good_risk),
            patch("core.polymarket_decision_engine.size_position", return_value=50.0),
        ):
            decisions = generate_trade_decisions(markets, _Config(), _wallet())

        assert len(decisions) == 2
        assert all(isinstance(d, TradeDecision) for d in decisions)
        assert all(d.size_usd == 50.0 for d in decisions)

    def test_rejected_risk_omitted(self):
        markets = [_market("cid1"), _market("cid2")]
        bad_risk = RiskDecision(approved=False, kelly=0.0, reason="low score")
        good_score = _good_score("cid1")

        with (
            patch("core.polymarket_decision_engine.score_market", return_value=good_score),
            patch("core.polymarket_decision_engine.assess_risk", return_value=bad_risk),
        ):
            decisions = generate_trade_decisions(markets, _Config(), _wallet())

        assert decisions == []

    def test_size_zero_omitted(self):
        markets = [_market("cid1")]
        good_risk = RiskDecision(approved=True, kelly=0.10, reason="ok")
        good_score = _good_score("cid1")

        with (
            patch("core.polymarket_decision_engine.score_market", return_value=good_score),
            patch("core.polymarket_decision_engine.assess_risk", return_value=good_risk),
            patch("core.polymarket_decision_engine.size_position", return_value=0.0),
        ):
            decisions = generate_trade_decisions(markets, _Config(), _wallet())

        assert decisions == []

    def test_sorted_by_score_descending(self):
        markets = [_market("cid1"), _market("cid2"), _market("cid3")]

        _w = {"w_edge": 0.35, "w_liquidity": 0.25, "w_time": 0.15, "w_copy": 0.15, "w_news": 0.10}
        scores = {
            "cid1": MarketScore(
                condition_id="cid1", total=50.0, edge=0, liquidity=0, time_decay=0,
                copy_signal=0, news_sentiment=0, fair_prob=0.70, market_prob=0.45, weights=_w,
            ),
            "cid2": MarketScore(
                condition_id="cid2", total=90.0, edge=0, liquidity=0, time_decay=0,
                copy_signal=0, news_sentiment=0, fair_prob=0.80, market_prob=0.45, weights=_w,
            ),
            "cid3": MarketScore(
                condition_id="cid3", total=70.0, edge=0, liquidity=0, time_decay=0,
                copy_signal=0, news_sentiment=0, fair_prob=0.75, market_prob=0.45, weights=_w,
            ),
        }

        def mock_score(market, **kwargs):
            return scores[market.condition_id]

        good_risk = RiskDecision(approved=True, kelly=0.10, reason="ok")

        with (
            patch("core.polymarket_decision_engine.score_market", side_effect=mock_score),
            patch("core.polymarket_decision_engine.assess_risk", return_value=good_risk),
            patch("core.polymarket_decision_engine.size_position", return_value=30.0),
        ):
            decisions = generate_trade_decisions(markets, _Config(), _wallet())

        assert [d.condition_id for d in decisions] == ["cid2", "cid3", "cid1"]

    def test_score_exception_skips_market(self):
        markets = [_market("cid1"), _market("cid2")]

        def failing_score(market, **kwargs):
            if market.condition_id == "cid1":
                raise RuntimeError("AI down")
            return _good_score("cid2")

        good_risk = RiskDecision(approved=True, kelly=0.10, reason="ok")

        with (
            patch("core.polymarket_decision_engine.score_market", side_effect=failing_score),
            patch("core.polymarket_decision_engine.assess_risk", return_value=good_risk),
            patch("core.polymarket_decision_engine.size_position", return_value=25.0),
        ):
            decisions = generate_trade_decisions(markets, _Config(), _wallet())

        assert len(decisions) == 1
        assert decisions[0].condition_id == "cid2"

    def test_empty_markets_returns_empty(self):
        decisions = generate_trade_decisions([], _Config(), _wallet())
        assert decisions == []

    def test_direction_yes_when_fair_above_market(self):
        markets = [_market("cid1", yes_price=0.40)]
        good_risk = RiskDecision(approved=True, kelly=0.10, reason="ok")
        score = _good_score("cid1", fair_prob=0.70)

        with (
            patch("core.polymarket_decision_engine.score_market", return_value=score),
            patch("core.polymarket_decision_engine.assess_risk", return_value=good_risk),
            patch("core.polymarket_decision_engine.size_position", return_value=50.0),
        ):
            decisions = generate_trade_decisions(markets, _Config(), _wallet())

        assert decisions[0].direction == "yes"

    def test_direction_no_when_fair_below_market(self):
        markets = [_market("cid1", yes_price=0.80)]
        good_risk = RiskDecision(approved=True, kelly=0.10, reason="ok")
        score = _good_score("cid1", fair_prob=0.30)

        with (
            patch("core.polymarket_decision_engine.score_market", return_value=score),
            patch("core.polymarket_decision_engine.assess_risk", return_value=good_risk),
            patch("core.polymarket_decision_engine.size_position", return_value=50.0),
        ):
            decisions = generate_trade_decisions(markets, _Config(), _wallet())

        assert decisions[0].direction == "no"
