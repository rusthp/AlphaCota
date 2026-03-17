"""Tests for core/risk_engine.py — Volatility calculations."""

import sys
import math
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.risk_engine import calculate_volatility


class TestCalculateVolatility:
    def test_constant_returns_zero_volatility(self):
        returns = [0.01] * 30
        result = calculate_volatility(returns)
        assert result == 0.0

    def test_varying_returns_positive_volatility(self):
        returns = [0.01, -0.02, 0.03, -0.01, 0.02, 0.005, -0.015, 0.025, -0.005, 0.01]
        result = calculate_volatility(returns)
        assert result > 0

    def test_annualization_factor(self):
        """Volatility should be daily stdev * sqrt(252)."""
        import statistics

        returns = [0.01, -0.02, 0.03, -0.01, 0.02, 0.005, -0.015, 0.025, -0.005, 0.01]
        daily_stdev = statistics.stdev(returns)
        expected = daily_stdev * math.sqrt(252)
        result = calculate_volatility(returns)
        assert result == expected

    def test_empty_list_returns_zero(self):
        result = calculate_volatility([])
        assert result == 0.0

    def test_single_value_returns_zero(self):
        result = calculate_volatility([0.05])
        assert result == 0.0

    def test_two_values(self):
        returns = [0.01, -0.01]
        result = calculate_volatility(returns)
        assert result > 0

    def test_high_volatility(self):
        returns = [0.10, -0.10, 0.15, -0.12, 0.08, -0.09]
        result = calculate_volatility(returns)
        assert result > 1.0  # Annualized vol should be very high

    def test_low_volatility(self):
        returns = [0.001, 0.0015, 0.001, 0.0012, 0.0011]
        result = calculate_volatility(returns)
        assert result < 0.1
