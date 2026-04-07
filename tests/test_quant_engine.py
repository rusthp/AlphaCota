"""Tests for core/quant_engine.py — Quality scoring, Altman Z, momentum."""

import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from core.quant_engine import (
    normalize_positive,
    normalize_inverse,
    calculate_quality_score,
    calculate_fii_score,
    calculate_altman_z,
    classify_bankruptcy_risk,
    calculate_moving_average,
    calculate_momentum_score,
    calculate_final_score,
    evaluate_company,
)


class TestNormalizePositive:
    def test_midpoint(self):
        assert normalize_positive(15.0, 10.0, 20.0) == pytest.approx(0.5)

    def test_minimum(self):
        assert normalize_positive(10.0, 10.0, 20.0) == pytest.approx(0.0)

    def test_maximum(self):
        assert normalize_positive(20.0, 10.0, 20.0) == pytest.approx(1.0)

    def test_below_min_clamps(self):
        assert normalize_positive(5.0, 10.0, 20.0) == 0.0

    def test_above_max_clamps(self):
        assert normalize_positive(25.0, 10.0, 20.0) == 1.0

    def test_equal_min_max_returns_zero(self):
        assert normalize_positive(10.0, 10.0, 10.0) == 0.0

    def test_nan_returns_zero(self):
        assert normalize_positive(float("nan"), 0.0, 10.0) == 0.0

    def test_inf_returns_zero(self):
        assert normalize_positive(float("inf"), 0.0, 10.0) == 0.0


class TestNormalizeInverse:
    def test_midpoint(self):
        assert normalize_inverse(15.0, 10.0, 20.0) == pytest.approx(0.5)

    def test_minimum_is_best(self):
        assert normalize_inverse(10.0, 10.0, 20.0) == pytest.approx(1.0)

    def test_maximum_is_worst(self):
        assert normalize_inverse(20.0, 10.0, 20.0) == pytest.approx(0.0)


class TestCalculateQualityScore:
    def test_returns_between_0_and_100(self):
        data = {"pl": 15.0, "pvp": 2.0, "roe": 15.0, "roa": 10.0}
        score = calculate_quality_score(data)
        assert 0.0 <= score <= 100.0

    def test_excellent_company(self):
        data = {
            "pl": 5.0,
            "pvp": 0.5,
            "roe": 30.0,
            "roa": 20.0,
            "revenue_growth": 20.0,
            "earnings_growth": 25.0,
            "debt_to_equity": 0.0,
            "current_ratio": 3.0,
        }
        score = calculate_quality_score(data)
        assert score > 80.0

    def test_poor_company(self):
        data = {
            "pl": 30.0,
            "pvp": 5.0,
            "roe": 5.0,
            "roa": 2.0,
            "revenue_growth": 0.0,
            "earnings_growth": 0.0,
            "debt_to_equity": 2.0,
            "current_ratio": 1.0,
        }
        score = calculate_quality_score(data)
        assert score < 20.0

    def test_defaults_for_missing_keys(self):
        score = calculate_quality_score({})
        assert 0.0 <= score <= 100.0


class TestCalculateAltmanZ:
    def test_healthy_company(self):
        data = {
            "total_assets": 1000,
            "total_liabilities": 300,
            "working_capital": 200,
            "retained_earnings": 400,
            "ebit": 150,
            "market_value_equity": 800,
            "revenue": 1200,
        }
        z = calculate_altman_z(data)
        assert z > 2.99

    def test_zero_assets_returns_zero(self):
        assert calculate_altman_z({"total_assets": 0, "total_liabilities": 100}) == 0.0

    def test_zero_liabilities_returns_zero(self):
        assert calculate_altman_z({"total_assets": 100, "total_liabilities": 0}) == 0.0

    def test_nan_field_returns_zero(self):
        data = {
            "total_assets": 1000,
            "total_liabilities": 300,
            "working_capital": float("nan"),
        }
        assert calculate_altman_z(data) == 0.0


class TestClassifyBankruptcyRisk:
    def test_safe_zone(self):
        assert classify_bankruptcy_risk(3.5) == "Zona Segura"

    def test_gray_zone(self):
        assert classify_bankruptcy_risk(2.5) == "Zona Cinzenta"

    def test_high_risk(self):
        assert classify_bankruptcy_risk(1.5) == "Alto Risco de Falência"

    def test_boundary_safe(self):
        assert classify_bankruptcy_risk(3.0) == "Zona Segura"

    def test_boundary_gray(self):
        assert classify_bankruptcy_risk(1.82) == "Zona Cinzenta"

    def test_boundary_high_risk(self):
        assert classify_bankruptcy_risk(1.81) == "Alto Risco de Falência"

    def test_zero(self):
        assert classify_bankruptcy_risk(0.0) == "Alto Risco de Falência"

    def test_negative(self):
        assert classify_bankruptcy_risk(-1.0) == "Alto Risco de Falência"


class TestCalculateMovingAverage:
    def test_simple_average(self):
        prices = [10.0, 20.0, 30.0]
        assert calculate_moving_average(prices, 3) == pytest.approx(20.0)

    def test_window_smaller_than_data(self):
        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        assert calculate_moving_average(prices, 3) == pytest.approx(40.0)

    def test_insufficient_data_raises(self):
        with pytest.raises(ValueError, match="insuficientes"):
            calculate_moving_average([10.0, 20.0], 5)


class TestCalculateMomentumScore:
    def test_uptrend_high_score(self):
        prices = [100 + i * 2 for i in range(12)]
        score = calculate_momentum_score(prices)
        assert score > 50.0

    def test_downtrend_low_score(self):
        prices = [100 - i * 2 for i in range(12)]
        score = calculate_momentum_score(prices)
        assert score < 50.0

    def test_flat_around_50(self):
        prices = [100.0] * 12
        score = calculate_momentum_score(prices)
        assert 45.0 <= score <= 55.0

    def test_insufficient_data_raises(self):
        with pytest.raises(ValueError, match="12 meses"):
            calculate_momentum_score([100.0] * 5)

    def test_returns_between_0_and_100(self):
        prices = [100 + i * 5 for i in range(12)]
        score = calculate_momentum_score(prices)
        assert 0.0 <= score <= 100.0


class TestCalculateFinalScore:
    def test_basic_composition(self):
        score = calculate_final_score(80.0, 60.0)
        expected = (0.8 * 80.0) + (0.2 * 60.0)
        assert score == pytest.approx(expected)

    def test_falling_knife_penalty(self):
        score_normal = calculate_final_score(80.0, 50.0)
        score_penalty = calculate_final_score(80.0, 20.0)
        assert score_penalty < score_normal

    def test_penalty_threshold_at_30(self):
        score_at_30 = calculate_final_score(80.0, 30.0)
        score_below_30 = calculate_final_score(80.0, 29.0)
        assert score_at_30 > score_below_30


class TestEvaluateCompany:
    def test_returns_all_fields(self):
        data = {"pl": 10.0, "pvp": 1.0, "roe": 20.0, "roa": 10.0, "total_assets": 1000, "total_liabilities": 300}
        result = evaluate_company("WEGE3", data)
        assert result["ticker"] == "WEGE3"
        assert "quality_score" in result
        assert "altman_z_score" in result
        assert "risk_classification" in result
        assert "final_score" in result

    def test_with_prices(self):
        data = {"pl": 10.0, "total_assets": 1000, "total_liabilities": 300}
        prices = [100 + i for i in range(12)]
        result = evaluate_company("WEGE3", data, prices)
        assert result["momentum_score"] > 0

    def test_without_prices(self):
        data = {"pl": 10.0, "total_assets": 1000, "total_liabilities": 300}
        result = evaluate_company("WEGE3", data)
        assert result["momentum_score"] == 0.0


# ---------------------------------------------------------------------------
# calculate_fii_score
# ---------------------------------------------------------------------------


class TestCalculateFiiScore:
    def test_returns_all_keys(self):
        result = calculate_fii_score({})
        assert set(result.keys()) == {"fundamentos", "rendimento", "risco", "liquidez", "total"}

    def test_sub_scores_between_0_and_25(self):
        for data in [
            {},
            {"pvp": 0.5, "dividend_yield": 0.15, "vacancy_rate": 0.0, "daily_liquidity": 10_000_000},
            {"pvp": 5.0, "dividend_yield": 0.0, "vacancy_rate": 1.0, "daily_liquidity": 0},
        ]:
            result = calculate_fii_score(data)
            for key in ("fundamentos", "rendimento", "risco", "liquidez"):
                assert 0.0 <= result[key] <= 25.0, f"{key}={result[key]} out of range for data={data}"

    def test_total_is_sum_of_sub_scores(self):
        data = {"pvp": 0.9, "dividend_yield": 0.10, "vacancy_rate": 0.05, "daily_liquidity": 3_000_000}
        result = calculate_fii_score(data)
        expected = round(result["fundamentos"] + result["rendimento"] + result["risco"] + result["liquidez"], 2)
        assert result["total"] == pytest.approx(expected, abs=0.01)

    def test_total_bounded_0_to_100(self):
        # Worst case
        worst = calculate_fii_score({"pvp": 10.0, "dividend_yield": 0.0, "vacancy_rate": 1.0, "daily_liquidity": 0})
        assert worst["total"] >= 0.0
        # Best case
        best = calculate_fii_score(
            {
                "pvp": 0.3,
                "dividend_yield": 0.20,
                "vacancy_rate": 0.0,
                "daily_liquidity": 10_000_000,
                "dividend_consistency": 1.0,
                "debt_ratio": 0.0,
            }
        )
        assert best["total"] <= 100.0

    def test_good_fii_scores_above_75(self):
        """Spec scenario: FII with good fundamentals scores high."""
        data = {
            "pvp": 0.95,
            "dividend_yield": 0.10,
            "vacancy_rate": 0.03,
            "daily_liquidity": 10_000_000,
        }
        result = calculate_fii_score(data)
        assert result["total"] > 75, f"Expected >75, got {result['total']}"

    def test_poor_fii_scores_below_40(self):
        """Spec scenario: FII with poor fundamentals scores low."""
        data = {
            "pvp": 2.5,
            "dividend_yield": 0.03,
            "vacancy_rate": 0.30,
            "daily_liquidity": 100_000,
        }
        result = calculate_fii_score(data)
        assert result["total"] < 40, f"Expected <40, got {result['total']}"

    def test_high_pvp_lowers_fundamentos(self):
        low_pvp = calculate_fii_score({"pvp": 0.7})
        high_pvp = calculate_fii_score({"pvp": 1.8})
        assert low_pvp["fundamentos"] > high_pvp["fundamentos"]

    def test_high_dy_raises_rendimento(self):
        low_dy = calculate_fii_score({"dividend_yield": 0.04})
        high_dy = calculate_fii_score({"dividend_yield": 0.14})
        assert high_dy["rendimento"] > low_dy["rendimento"]

    def test_high_vacancy_lowers_risco(self):
        low_vac = calculate_fii_score({"vacancy_rate": 0.02})
        high_vac = calculate_fii_score({"vacancy_rate": 0.25})
        assert low_vac["risco"] > high_vac["risco"]

    def test_high_liquidity_raises_liquidez(self):
        low_liq = calculate_fii_score({"daily_liquidity": 50_000})
        high_liq = calculate_fii_score({"daily_liquidity": 8_000_000})
        assert high_liq["liquidez"] > low_liq["liquidez"]

    def test_accepts_vacancia_key_alias(self):
        """Both 'vacancy_rate' and 'vacancia' keys should work."""
        r1 = calculate_fii_score({"vacancy_rate": 0.05})
        r2 = calculate_fii_score({"vacancia": 0.05})
        assert r1["risco"] == r2["risco"]

    def test_accepts_liquidez_diaria_key_alias(self):
        """Both 'daily_liquidity' and 'liquidez_diaria' keys should work."""
        r1 = calculate_fii_score({"daily_liquidity": 2_000_000})
        r2 = calculate_fii_score({"liquidez_diaria": 2_000_000})
        assert r1["liquidez"] == r2["liquidez"]

    def test_dividend_consistency_increases_rendimento(self):
        low_cons = calculate_fii_score({"dividend_yield": 0.09, "dividend_consistency": 0.0})
        high_cons = calculate_fii_score({"dividend_yield": 0.09, "dividend_consistency": 1.0})
        assert high_cons["rendimento"] > low_cons["rendimento"]

    def test_consistency_clamped_above_1(self):
        """Values >1 should not exceed max."""
        result = calculate_fii_score({"dividend_consistency": 999})
        assert result["rendimento"] <= 25.0

    def test_empty_dict_returns_mid_range_scores(self):
        """Defaults should produce valid non-zero scores."""
        result = calculate_fii_score({})
        assert result["total"] > 0
