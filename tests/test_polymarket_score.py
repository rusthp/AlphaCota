"""tests/test_polymarket_score.py — Tests for polymarket_score module."""

import time
from unittest.mock import patch

import pytest

from core.polymarket_score import (
    DEFAULT_WEIGHTS,
    MarketScore,
    _copy_signal_score,
    _edge_score,
    _liquidity_score,
    _time_decay_score,
    score_market,
    validate_weights,
)
from core.polymarket_types import CopySignal, Market, OrderBook, OrderBookLevel


def _market(
    condition_id: str = "cid1",
    yes_price: float = 0.45,
    volume_24h: float = 50_000.0,
    days_to_resolution: float = 14.0,
    category: str = "politics",
) -> Market:
    return Market(
        condition_id=condition_id,
        token_id="tok1",
        question="Will X happen?",
        end_date_iso="",
        volume_24h=volume_24h,
        spread_pct=0.02,
        days_to_resolution=days_to_resolution,
        yes_price=yes_price,
        category=category,
    )


def _book(bid: float = 0.44, ask: float = 0.46) -> OrderBook:
    return OrderBook(
        token_id="tok1",
        bids=(OrderBookLevel(bid, 500.0),),
        asks=(OrderBookLevel(ask, 400.0),),
        mid_price=(bid + ask) / 2,
        spread_pct=ask - bid,
    )


class TestValidateWeights:
    def test_valid_default_weights(self):
        validate_weights(DEFAULT_WEIGHTS)

    def test_fails_when_sum_not_one(self):
        bad = dict(DEFAULT_WEIGHTS)
        bad["w_edge"] = 0.50
        with pytest.raises(ValueError, match="sum to 1.0"):
            validate_weights(bad)

    def test_fails_missing_key(self):
        bad = {k: v for k, v in DEFAULT_WEIGHTS.items() if k != "w_news"}
        bad["w_edge"] += 0.10
        with pytest.raises(ValueError):
            validate_weights(bad)


class TestEdgeScore:
    def test_zero_when_fair_prob_none(self):
        assert _edge_score(None, 0.5) == 0.0

    def test_max_at_twenty_pct_edge(self):
        score = _edge_score(0.70, 0.50)
        assert score == pytest.approx(100.0)

    def test_partial_edge(self):
        score = _edge_score(0.60, 0.50)
        assert 0 < score < 100

    def test_symmetric_direction(self):
        assert _edge_score(0.70, 0.50) == _edge_score(0.30, 0.50)

    def test_zero_edge(self):
        assert _edge_score(0.50, 0.50) == 0.0


class TestLiquidityScore:
    def test_high_volume_tight_spread_max(self):
        book = _book(0.495, 0.505)
        score = _liquidity_score(book, 200_000.0)
        assert score > 90

    def test_spread_above_10pct_penalised(self):
        book = _book(0.40, 0.60)
        score = _liquidity_score(book, 100_000.0)
        assert score < 60

    def test_low_volume_penalised(self):
        book = _book()
        score = _liquidity_score(book, 100.0)
        assert score < 50

    def test_no_order_book(self):
        score = _liquidity_score(None, 50_000.0)
        assert 0 <= score <= 100


class TestTimeDecayScore:
    def test_peak_near_14_days(self):
        score = _time_decay_score(14.0)
        assert score == pytest.approx(100.0)

    def test_within_ideal_window(self):
        assert _time_decay_score(7.0) > 70
        assert _time_decay_score(30.0) > 70

    def test_too_close_to_zero(self):
        assert _time_decay_score(1.0) == 0.0
        assert _time_decay_score(0.0) == 0.0

    def test_very_far_future_penalised(self):
        score = _time_decay_score(365.0)
        assert score < 40

    def test_between_2_and_7_days(self):
        score = _time_decay_score(5.0)
        assert 0 < score < 80


class TestCopySignalScore:
    def test_none_signal_returns_zero(self):
        assert _copy_signal_score(None) == 0.0

    def test_no_direction_returns_zero(self):
        cs = CopySignal(direction="none", confidence=0.8, wallet_count=3, consensus_ratio=0.9)
        assert _copy_signal_score(cs) == 0.0

    def test_strong_signal_high_score(self):
        cs = CopySignal(direction="yes", confidence=1.0, wallet_count=5, consensus_ratio=1.0)
        assert _copy_signal_score(cs) == pytest.approx(100.0)

    def test_weak_signal_low_score(self):
        cs = CopySignal(direction="yes", confidence=0.3, wallet_count=1, consensus_ratio=0.55)
        score = _copy_signal_score(cs)
        assert score < 20


class TestScoreMarket:
    def test_ai_none_fallback_returns_score(self):
        with patch("core.polymarket_score.estimate_market_probability", return_value=None):
            ms = score_market(_market())
        assert isinstance(ms, MarketScore)
        assert ms.edge == 0.0
        assert 0 <= ms.total <= 100

    def test_ai_result_populates_edge(self):
        ai_result = {
            "fair_prob": 0.70,
            "market_prob": 0.45,
            "edge": 0.25,
            "confidence": 0.8,
            "reasoning": "test",
        }
        with patch("core.polymarket_score.estimate_market_probability", return_value=ai_result):
            ms = score_market(_market(yes_price=0.45))
        assert ms.edge > 0
        assert ms.fair_prob == pytest.approx(0.70)

    def test_custom_weights_accepted(self):
        custom = {
            "w_edge": 0.40,
            "w_liquidity": 0.20,
            "w_time": 0.15,
            "w_copy": 0.15,
            "w_news": 0.10,
        }
        with patch("core.polymarket_score.estimate_market_probability", return_value=None):
            ms = score_market(_market(), weights=custom)
        assert ms.weights == custom

    def test_invalid_weights_raises(self):
        bad = dict(DEFAULT_WEIGHTS)
        bad["w_edge"] = 0.99
        with pytest.raises(ValueError):
            score_market(_market(), weights=bad)

    def test_condition_id_preserved(self):
        with patch("core.polymarket_score.estimate_market_probability", return_value=None):
            ms = score_market(_market(condition_id="test-cid"))
        assert ms.condition_id == "test-cid"
