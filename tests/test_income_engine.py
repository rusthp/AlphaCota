"""Tests for core/income_engine.py — Income/yield calculations."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from core.income_engine import calculate_income_metrics


class TestCalculateIncomeMetrics:
    def test_basic_calculation(self):
        proventos = [
            {"ticker": "HGLG11", "valor": 100.0},
            {"ticker": "XPML11", "valor": 50.0},
        ]
        result = calculate_income_metrics(proventos, 10000.0)
        assert result["renda_total"] == 150.0
        assert result["yield_percentual"] == pytest.approx(1.5)

    def test_single_provento(self):
        proventos = [{"ticker": "HGLG11", "valor": 200.0}]
        result = calculate_income_metrics(proventos, 20000.0)
        assert result["renda_total"] == 200.0
        assert result["yield_percentual"] == pytest.approx(1.0)

    def test_zero_proventos(self):
        result = calculate_income_metrics([], 10000.0)
        assert result["renda_total"] == 0.0
        assert result["yield_percentual"] == 0.0

    def test_zero_value_provento(self):
        proventos = [{"ticker": "HGLG11", "valor": 0.0}]
        result = calculate_income_metrics(proventos, 10000.0)
        assert result["renda_total"] == 0.0

    def test_zero_carteira_raises(self):
        proventos = [{"ticker": "HGLG11", "valor": 100.0}]
        with pytest.raises(ValueError, match="maior que zero"):
            calculate_income_metrics(proventos, 0)

    def test_negative_carteira_raises(self):
        proventos = [{"ticker": "HGLG11", "valor": 100.0}]
        with pytest.raises(ValueError, match="maior que zero"):
            calculate_income_metrics(proventos, -5000)

    def test_negative_provento_raises(self):
        proventos = [{"ticker": "HGLG11", "valor": -50.0}]
        with pytest.raises(ValueError, match="negativo"):
            calculate_income_metrics(proventos, 10000.0)

    def test_invalid_ticker_raises(self):
        proventos = [{"ticker": "", "valor": 100.0}]
        with pytest.raises(ValueError, match="inválido"):
            calculate_income_metrics(proventos, 10000.0)

    def test_missing_ticker_raises(self):
        proventos = [{"valor": 100.0}]
        with pytest.raises(ValueError, match="inválido"):
            calculate_income_metrics(proventos, 10000.0)

    def test_multiple_tickers_yield(self):
        proventos = [
            {"ticker": "HGLG11", "valor": 80.0},
            {"ticker": "XPML11", "valor": 60.0},
            {"ticker": "VISC11", "valor": 40.0},
        ]
        result = calculate_income_metrics(proventos, 18000.0)
        assert result["renda_total"] == 180.0
        assert result["yield_percentual"] == pytest.approx(1.0)
