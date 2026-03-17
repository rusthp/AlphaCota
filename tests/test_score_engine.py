"""Tests for core/score_engine.py — Alpha Score model for FIIs."""

import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from core.score_engine import (
    DEFAULT_WEIGHTS,
    validate_weights,
    calculate_income_score,
    calculate_valuation_score,
    calculate_risk_score,
    calculate_growth_score,
    calculate_alpha_score,
    rank_fiis,
)


class TestValidateWeights:
    def test_default_weights_valid(self):
        validate_weights(DEFAULT_WEIGHTS)  # Should not raise

    def test_missing_key_raises(self):
        bad = {"w_income": 0.5, "w_valuation": 0.5}
        with pytest.raises(ValueError, match="ausentes"):
            validate_weights(bad)

    def test_negative_weight_raises(self):
        bad = {**DEFAULT_WEIGHTS, "w_income": -0.1}
        with pytest.raises(ValueError, match="negativo"):
            validate_weights(bad)

    def test_sum_not_one_raises(self):
        bad = {"w_income": 0.5, "w_valuation": 0.5, "w_risk": 0.5, "w_growth": 0.5}
        with pytest.raises(ValueError, match="somar"):
            validate_weights(bad)

    def test_sum_within_tolerance(self):
        w = {"w_income": 0.40, "w_valuation": 0.25, "w_risk": 0.20, "w_growth": 0.15}
        validate_weights(w)  # Should not raise


class TestCalculateIncomeScore:
    def test_high_yield_high_consistency(self):
        score = calculate_income_score(0.12, 10.0)
        assert 8.0 <= score <= 10.0

    def test_low_yield_low_consistency(self):
        score = calculate_income_score(0.04, 0.0)
        assert score == pytest.approx(0.0)

    def test_mid_range(self):
        score = calculate_income_score(0.08, 5.0)
        assert 2.0 <= score <= 6.0

    def test_nan_yield_treated_as_zero(self):
        score = calculate_income_score(float("nan"), 5.0)
        assert 0.0 <= score <= 10.0

    def test_nan_consistency_treated_as_zero(self):
        score = calculate_income_score(0.10, float("nan"))
        assert 0.0 <= score <= 10.0


class TestCalculateValuationScore:
    def test_cheap_pvp(self):
        score = calculate_valuation_score(0.7)
        assert score == pytest.approx(10.0)

    def test_expensive_pvp(self):
        score = calculate_valuation_score(1.5)
        assert score == pytest.approx(0.0)

    def test_fair_pvp(self):
        score = calculate_valuation_score(1.0)
        assert 4.0 <= score <= 8.0

    def test_zero_pvp_uses_neutral(self):
        score = calculate_valuation_score(0.0)
        assert 0.0 <= score <= 10.0

    def test_nan_pvp_uses_neutral(self):
        score = calculate_valuation_score(float("nan"))
        assert 0.0 <= score <= 10.0


class TestCalculateRiskScore:
    def test_low_debt_low_vacancy(self):
        score = calculate_risk_score(0.0, 0.0)
        assert score == pytest.approx(10.0)

    def test_high_debt_high_vacancy(self):
        score = calculate_risk_score(1.0, 0.30)
        assert score == pytest.approx(0.0)

    def test_mid_range(self):
        score = calculate_risk_score(0.5, 0.10)
        assert 2.0 <= score <= 8.0

    def test_nan_debt_uses_default(self):
        score = calculate_risk_score(float("nan"), 0.05)
        assert 0.0 <= score <= 10.0


class TestCalculateGrowthScore:
    def test_high_growth(self):
        score = calculate_growth_score(0.20, 0.20)
        assert score == pytest.approx(10.0)

    def test_zero_growth(self):
        score = calculate_growth_score(0.0, 0.0)
        assert score == pytest.approx(0.0)

    def test_negative_growth_clamps(self):
        score = calculate_growth_score(-0.10, -0.05)
        assert score == pytest.approx(0.0)


class TestCalculateAlphaScore:
    def test_returns_all_keys(self):
        result = calculate_alpha_score(
            dividend_yield=0.10, dividend_consistency=8.0,
            pvp=0.9, debt_ratio=0.2, vacancy_rate=0.05,
            revenue_growth_12m=0.10, earnings_growth_12m=0.12,
        )
        assert "alpha_score" in result
        assert "income_score" in result
        assert "valuation_score" in result
        assert "risk_score" in result
        assert "growth_score" in result
        assert "weights_used" in result

    def test_score_between_0_and_10(self):
        result = calculate_alpha_score(0.08, 5.0, 1.0, 0.5, 0.10, 0.05, 0.05)
        assert 0.0 <= result["alpha_score"] <= 10.0

    def test_excellent_fii(self):
        result = calculate_alpha_score(0.12, 10.0, 0.7, 0.0, 0.0, 0.20, 0.20)
        assert result["alpha_score"] > 8.0

    def test_poor_fii(self):
        result = calculate_alpha_score(0.04, 0.0, 1.5, 1.0, 0.30, 0.0, 0.0)
        assert result["alpha_score"] < 2.0

    def test_custom_weights(self):
        custom = {"w_income": 1.0, "w_valuation": 0.0, "w_risk": 0.0, "w_growth": 0.0}
        result = calculate_alpha_score(0.12, 10.0, 1.5, 1.0, 0.30, 0.0, 0.0, weights=custom)
        # Score should be driven entirely by income
        assert result["alpha_score"] > 7.0

    def test_invalid_weights_raises(self):
        bad = {"w_income": 0.5, "w_valuation": 0.5, "w_risk": 0.5, "w_growth": 0.5}
        with pytest.raises(ValueError):
            calculate_alpha_score(0.10, 5.0, 1.0, 0.5, 0.1, 0.05, 0.05, weights=bad)


class TestRankFiis:
    def test_sorted_by_score_desc(self):
        fiis = [
            {"ticker": "BAD11", "dividend_yield": 0.04, "pvp": 1.5, "debt_ratio": 1.0,
             "vacancy_rate": 0.3, "revenue_growth_12m": 0.0, "earnings_growth_12m": 0.0},
            {"ticker": "GOOD11", "dividend_yield": 0.12, "pvp": 0.7, "debt_ratio": 0.0,
             "vacancy_rate": 0.0, "revenue_growth_12m": 0.20, "earnings_growth_12m": 0.20},
        ]
        ranked = rank_fiis(fiis)
        assert ranked[0]["ticker"] == "GOOD11"
        assert ranked[1]["ticker"] == "BAD11"
        assert ranked[0]["alpha_score"] > ranked[1]["alpha_score"]

    def test_preserves_original_fields(self):
        fiis = [{"ticker": "TEST11", "extra_field": 42}]
        ranked = rank_fiis(fiis)
        assert ranked[0]["extra_field"] == 42
        assert "alpha_score" in ranked[0]

    def test_empty_list(self):
        assert rank_fiis([]) == []
