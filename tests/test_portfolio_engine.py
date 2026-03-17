"""Tests for core/portfolio_engine.py — Allocation and rebalance calculations."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from core.portfolio_engine import calculate_portfolio_allocation, calculate_rebalance_suggestion


class TestCalculatePortfolioAllocation:
    def test_basic_allocation(self):
        ativos = [
            {"ticker": "HGLG11", "valor": 5000.0},
            {"ticker": "XPML11", "valor": 5000.0},
        ]
        result = calculate_portfolio_allocation(ativos)
        assert result["total"] == 10000.0
        assert len(result["allocations"]) == 2
        assert result["allocations"][0]["percentual"] == pytest.approx(50.0)
        assert result["allocations"][1]["percentual"] == pytest.approx(50.0)

    def test_unequal_allocation(self):
        ativos = [
            {"ticker": "HGLG11", "valor": 7500.0},
            {"ticker": "XPML11", "valor": 2500.0},
        ]
        result = calculate_portfolio_allocation(ativos)
        assert result["total"] == 10000.0
        assert result["allocations"][0]["percentual"] == pytest.approx(75.0)
        assert result["allocations"][1]["percentual"] == pytest.approx(25.0)

    def test_single_asset(self):
        ativos = [{"ticker": "HGLG11", "valor": 10000.0}]
        result = calculate_portfolio_allocation(ativos)
        assert result["allocations"][0]["percentual"] == pytest.approx(100.0)

    def test_empty_portfolio(self):
        result = calculate_portfolio_allocation([])
        assert result["total"] == 0.0
        assert result["allocations"] == []

    def test_zero_values(self):
        ativos = [
            {"ticker": "HGLG11", "valor": 0.0},
            {"ticker": "XPML11", "valor": 0.0},
        ]
        result = calculate_portfolio_allocation(ativos)
        assert result["total"] == 0.0
        assert result["allocations"][0]["percentual"] == 0.0

    def test_negative_value_raises(self):
        ativos = [{"ticker": "HGLG11", "valor": -1000.0}]
        with pytest.raises(ValueError, match="negativo"):
            calculate_portfolio_allocation(ativos)

    def test_invalid_ticker_raises(self):
        ativos = [{"ticker": "", "valor": 1000.0}]
        with pytest.raises(ValueError, match="inválido"):
            calculate_portfolio_allocation(ativos)


class TestCalculateRebalanceSuggestion:
    def test_basic_rebalance(self):
        ativos = [
            {"ticker": "HGLG11", "valor": 6000.0},
            {"ticker": "XPML11", "valor": 4000.0},
        ]
        alvo = {"HGLG11": 0.50, "XPML11": 0.50}
        result = calculate_rebalance_suggestion(ativos, alvo, 2000.0)

        sugestoes = {s["ticker"]: s["valor_aportar"] for s in result["sugestao"]}
        assert sugestoes["XPML11"] > sugestoes["HGLG11"]
        assert sum(s["valor_aportar"] for s in result["sugestao"]) == pytest.approx(2000.0)

    def test_balanced_portfolio_proportional(self):
        ativos = [
            {"ticker": "HGLG11", "valor": 5000.0},
            {"ticker": "XPML11", "valor": 5000.0},
        ]
        alvo = {"HGLG11": 0.50, "XPML11": 0.50}
        result = calculate_rebalance_suggestion(ativos, alvo, 1000.0)

        sugestoes = {s["ticker"]: s["valor_aportar"] for s in result["sugestao"]}
        assert sugestoes["HGLG11"] == pytest.approx(500.0)
        assert sugestoes["XPML11"] == pytest.approx(500.0)

    def test_negative_aporte_raises(self):
        ativos = [{"ticker": "HGLG11", "valor": 5000.0}]
        alvo = {"HGLG11": 1.0}
        with pytest.raises(ValueError, match="negativo"):
            calculate_rebalance_suggestion(ativos, alvo, -100.0)

    def test_asset_not_in_target_raises(self):
        ativos = [{"ticker": "HGLG11", "valor": 5000.0}]
        alvo = {"XPML11": 1.0}
        with pytest.raises(ValueError, match="não encontrado"):
            calculate_rebalance_suggestion(ativos, alvo, 1000.0)

    def test_zero_aporte(self):
        ativos = [
            {"ticker": "HGLG11", "valor": 5000.0},
            {"ticker": "XPML11", "valor": 5000.0},
        ]
        alvo = {"HGLG11": 0.50, "XPML11": 0.50}
        result = calculate_rebalance_suggestion(ativos, alvo, 0.0)
        total = sum(s["valor_aportar"] for s in result["sugestao"])
        assert total == pytest.approx(0.0)
