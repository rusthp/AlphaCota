"""Tests for core/score_engine.py — Alpha Score model for FIIs."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from core.score_engine import (
    DEFAULT_WEIGHTS,
    calculate_alpha_score,
    calculate_growth_score,
    calculate_income_score,
    calculate_risk_score,
    calculate_valuation_score,
    rank_fiis,
    validate_weights,
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
        # All required keys present but sum != 1.0
        bad = {
            "w_income": 0.5,
            "w_valuation": 0.5,
            "w_risk": 0.5,
            "w_growth": 0.5,
            "w_news": 0.5,
        }
        with pytest.raises(ValueError, match="somar"):
            validate_weights(bad)

    def test_sum_within_tolerance(self):
        # All required keys, sum = 1.0
        w = {
            "w_income": 0.40,
            "w_valuation": 0.25,
            "w_risk": 0.20,
            "w_growth": 0.05,
            "w_news": 0.10,
        }
        validate_weights(w)  # Should not raise


class TestCalculateIncomeScore:
    # Score is 0-100

    def test_high_yield_high_consistency(self):
        # DY=12%, consistency=100 → dy_score=100, result=100
        score = calculate_income_score(0.12, 100.0)
        assert 80.0 <= score <= 100.0

    def test_low_yield_low_consistency(self):
        score = calculate_income_score(0.04, 0.0)
        assert score == pytest.approx(0.0)

    def test_mid_range(self):
        # DY=8% → dy_score=50, consistency=50 → result = 0.6*50 + 0.4*50 = 50
        score = calculate_income_score(0.08, 50.0)
        assert 20.0 <= score <= 60.0

    def test_nan_yield_treated_as_zero(self):
        score = calculate_income_score(float("nan"), 50.0)
        assert 0.0 <= score <= 100.0

    def test_nan_consistency_treated_as_zero(self):
        score = calculate_income_score(0.10, float("nan"))
        assert 0.0 <= score <= 100.0


class TestCalculateValuationScore:
    # Score is 0-100

    def test_cheap_pvp(self):
        # pvp=0.7 → score=100
        score = calculate_valuation_score(0.7)
        assert score == pytest.approx(100.0)

    def test_expensive_pvp(self):
        score = calculate_valuation_score(1.5)
        assert score == pytest.approx(0.0)

    def test_fair_pvp(self):
        # pvp=1.0 → score = (1.5-1.0)/(1.5-0.7)*100 = 62.5
        score = calculate_valuation_score(1.0)
        assert 40.0 <= score <= 80.0

    def test_zero_pvp_uses_neutral(self):
        score = calculate_valuation_score(0.0)
        assert 0.0 <= score <= 100.0

    def test_nan_pvp_uses_neutral(self):
        score = calculate_valuation_score(float("nan"))
        assert 0.0 <= score <= 100.0


class TestCalculateRiskScore:
    # Score is 0-100 (100 = low risk)

    def test_low_debt_low_vacancy(self):
        score = calculate_risk_score(0.0, 0.0)
        assert score == pytest.approx(100.0)

    def test_high_debt_high_vacancy(self):
        score = calculate_risk_score(1.0, 0.30)
        assert score == pytest.approx(0.0)

    def test_mid_range(self):
        score = calculate_risk_score(0.5, 0.10)
        assert 20.0 <= score <= 80.0

    def test_nan_debt_uses_default(self):
        score = calculate_risk_score(float("nan"), 0.05)
        assert 0.0 <= score <= 100.0

    def test_nan_vacancy_uses_default(self):
        score = calculate_risk_score(0.3, float("nan"))
        assert 0.0 <= score <= 100.0

    def test_inf_vacancy_uses_default(self):
        score = calculate_risk_score(0.2, float("inf"))
        assert 0.0 <= score <= 100.0


class TestCalculateGrowthScore:
    # Score is 0-100

    def test_high_growth(self):
        # both at 20% → 100
        score = calculate_growth_score(0.20, 0.20)
        assert score == pytest.approx(100.0)

    def test_zero_growth(self):
        score = calculate_growth_score(0.0, 0.0)
        assert score == pytest.approx(0.0)

    def test_negative_growth_clamps(self):
        score = calculate_growth_score(-0.10, -0.05)
        assert score == pytest.approx(0.0)

    def test_nan_revenue_growth_treated_as_zero(self):
        score = calculate_growth_score(float("nan"), 0.10)
        assert 0.0 <= score <= 100.0

    def test_nan_earnings_growth_treated_as_zero(self):
        score = calculate_growth_score(0.10, float("nan"))
        assert 0.0 <= score <= 100.0

    def test_inf_revenue_growth_treated_as_zero(self):
        score = calculate_growth_score(float("inf"), 0.0)
        assert score == pytest.approx(0.0)


class TestCalculateAlphaScore:
    # alpha_score is 0-100

    def test_returns_all_keys(self):
        result = calculate_alpha_score(
            dividend_yield=0.10,
            dividend_consistency=80.0,
            pvp=0.9,
            debt_ratio=0.2,
            vacancy_rate=0.05,
            revenue_growth_12m=0.10,
            earnings_growth_12m=0.12,
        )
        assert "alpha_score" in result
        assert "income_score" in result
        assert "valuation_score" in result
        assert "risk_score" in result
        assert "growth_score" in result
        assert "weights_used" in result

    def test_score_between_0_and_100(self):
        result = calculate_alpha_score(0.08, 50.0, 1.0, 0.5, 0.10, 0.05, 0.05)
        assert 0.0 <= result["alpha_score"] <= 100.0

    def test_excellent_fii(self):
        result = calculate_alpha_score(0.12, 100.0, 0.7, 0.0, 0.0, 0.20, 0.20)
        assert result["alpha_score"] > 80.0

    def test_poor_fii(self):
        result = calculate_alpha_score(0.04, 0.0, 1.5, 1.0, 0.30, 0.0, 0.0)
        assert result["alpha_score"] < 20.0

    def test_custom_weights(self):
        # All weight on income, excellent income → high score
        custom = {
            "w_income": 1.0,
            "w_valuation": 0.0,
            "w_risk": 0.0,
            "w_growth": 0.0,
            "w_news": 0.0,
        }
        result = calculate_alpha_score(0.12, 100.0, 1.5, 1.0, 0.30, 0.0, 0.0, weights=custom)
        assert result["alpha_score"] > 70.0

    def test_invalid_weights_raises(self):
        bad = {"w_income": 0.5, "w_valuation": 0.5, "w_risk": 0.5, "w_growth": 0.5}
        with pytest.raises(ValueError):
            calculate_alpha_score(0.10, 50.0, 1.0, 0.5, 0.1, 0.05, 0.05, weights=bad)


class TestRankFiis:
    def test_sorted_by_score_desc(self):
        fiis = [
            {
                "ticker": "BAD11",
                "dividend_yield": 0.04,
                "pvp": 1.5,
                "debt_ratio": 1.0,
                "vacancy_rate": 0.3,
                "revenue_growth_12m": 0.0,
                "earnings_growth_12m": 0.0,
            },
            {
                "ticker": "GOOD11",
                "dividend_yield": 0.12,
                "pvp": 0.7,
                "debt_ratio": 0.0,
                "vacancy_rate": 0.0,
                "revenue_growth_12m": 0.20,
                "earnings_growth_12m": 0.20,
            },
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
