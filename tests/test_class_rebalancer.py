"""Tests for core/class_rebalancer.py — Asset class rebalancing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from core.class_rebalancer import calculateRebalanceSuggestion


class TestCalculateRebalanceSuggestion:
    def test_identifies_underweight_class(self):
        portfolio = [
            {"classe": "ETF", "quantidade": 10, "preco_atual": 100},
            {"classe": "FII", "quantidade": 2, "preco_atual": 100},
            {"classe": "ACAO", "quantidade": 5, "preco_atual": 100},
        ]
        target = {"ETF": 0.50, "FII": 0.30, "ACAO": 0.20}
        result = calculateRebalanceSuggestion(portfolio, target)

        assert result["classe_prioritaria_para_aporte"] == "FII"

    def test_balanced_portfolio(self):
        portfolio = [
            {"classe": "ETF", "quantidade": 50, "preco_atual": 100},
            {"classe": "FII", "quantidade": 30, "preco_atual": 100},
            {"classe": "ACAO", "quantidade": 20, "preco_atual": 100},
        ]
        target = {"ETF": 0.50, "FII": 0.30, "ACAO": 0.20}
        result = calculateRebalanceSuggestion(portfolio, target)

        for classe_data in result["pesos_e_distorcoes"].values():
            assert abs(classe_data["distorcao"]) < 0.01

    def test_single_class(self):
        portfolio = [{"classe": "ETF", "quantidade": 10, "preco_atual": 100}]
        target = {"ETF": 1.0}
        result = calculateRebalanceSuggestion(portfolio, target)

        assert result["classe_prioritaria_para_aporte"] == "ETF"
        assert result["pesos_e_distorcoes"]["ETF"]["distorcao"] == pytest.approx(0.0)

    def test_empty_class_gets_priority(self):
        portfolio = [
            {"classe": "ETF", "quantidade": 100, "preco_atual": 100},
            {"classe": "FII", "quantidade": 0, "preco_atual": 100},
        ]
        target = {"ETF": 0.50, "FII": 0.50}
        result = calculateRebalanceSuggestion(portfolio, target)

        assert result["classe_prioritaria_para_aporte"] == "FII"

    def test_distorcao_values_correct(self):
        portfolio = [
            {"classe": "ETF", "quantidade": 80, "preco_atual": 100},
            {"classe": "ACAO", "quantidade": 20, "preco_atual": 100},
        ]
        target = {"ETF": 0.50, "ACAO": 0.50}
        result = calculateRebalanceSuggestion(portfolio, target)

        assert result["pesos_e_distorcoes"]["ETF"]["peso_atual"] == pytest.approx(0.80)
        assert result["pesos_e_distorcoes"]["ETF"]["distorcao"] == pytest.approx(-0.30)
        assert result["pesos_e_distorcoes"]["ACAO"]["distorcao"] == pytest.approx(0.30)

    def test_returns_all_classes(self):
        portfolio = [
            {"classe": "ETF", "quantidade": 10, "preco_atual": 100},
            {"classe": "FII", "quantidade": 10, "preco_atual": 100},
        ]
        target = {"ETF": 0.60, "FII": 0.40}
        result = calculateRebalanceSuggestion(portfolio, target)

        assert set(result["pesos_e_distorcoes"].keys()) == {"ETF", "FII"}
