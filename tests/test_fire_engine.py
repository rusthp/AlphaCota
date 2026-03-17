"""Tests for core/fire_engine.py — FIRE projection calculations."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from core.fire_engine import calculate_years_to_fire, calculate_required_capital


class TestCalculateRequiredCapital:
    def test_standard_calculation(self):
        result = calculate_required_capital(60000, 0.10)
        assert result == 600000.0

    def test_high_yield(self):
        result = calculate_required_capital(120000, 0.12)
        assert result == 1000000.0

    def test_zero_rate_returns_zero(self):
        result = calculate_required_capital(60000, 0.0)
        assert result == 0.0

    def test_negative_rate_returns_zero(self):
        result = calculate_required_capital(60000, -0.05)
        assert result == 0.0

    def test_zero_income_target(self):
        result = calculate_required_capital(0, 0.10)
        assert result == 0.0

    def test_small_values(self):
        result = calculate_required_capital(1200, 0.06)
        assert result == pytest.approx(20000.0)


class TestCalculateYearsToFire:
    def test_already_reached(self):
        result = calculate_years_to_fire(
            patrimonio_atual=700000,
            aporte_mensal=1000,
            taxa_anual=0.10,
            renda_alvo_anual=60000,
        )
        assert result == 0.0

    def test_typical_scenario(self):
        result = calculate_years_to_fire(
            patrimonio_atual=100000,
            aporte_mensal=5000,
            taxa_anual=0.10,
            renda_alvo_anual=60000,
        )
        assert 0 < result < 50
        assert isinstance(result, float)

    def test_zero_patrimonio(self):
        result = calculate_years_to_fire(
            patrimonio_atual=0,
            aporte_mensal=5000,
            taxa_anual=0.10,
            renda_alvo_anual=60000,
        )
        assert result > 0

    def test_higher_aporte_reduces_time(self):
        years_low = calculate_years_to_fire(0, 1000, 0.10, 60000)
        years_high = calculate_years_to_fire(0, 5000, 0.10, 60000)
        assert years_high < years_low

    def test_higher_rate_reduces_time(self):
        years_low = calculate_years_to_fire(0, 3000, 0.06, 60000)
        years_high = calculate_years_to_fire(0, 3000, 0.12, 60000)
        assert years_high < years_low

    def test_negative_taxa_raises(self):
        with pytest.raises(ValueError, match="Parâmetros inválidos"):
            calculate_years_to_fire(100000, 5000, -0.05, 60000)

    def test_zero_taxa_raises(self):
        with pytest.raises(ValueError, match="Parâmetros inválidos"):
            calculate_years_to_fire(100000, 5000, 0.0, 60000)

    def test_negative_aporte_raises(self):
        with pytest.raises(ValueError, match="Parâmetros inválidos"):
            calculate_years_to_fire(100000, -1000, 0.10, 60000)

    def test_negative_patrimonio_raises(self):
        with pytest.raises(ValueError, match="Parâmetros inválidos"):
            calculate_years_to_fire(-50000, 5000, 0.10, 60000)

    def test_unreachable_goal_raises(self):
        with pytest.raises(ValueError, match="inalcançável"):
            calculate_years_to_fire(0, 1, 0.001, 10000000)
