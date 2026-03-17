"""Tests for core/position_engine.py — Position P&L calculations."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from core.position_engine import calculate_position_metrics


class TestCalculatePositionMetrics:
    def test_single_buy(self):
        ops = [{"ticker": "HGLG11", "tipo": "compra", "quantidade": 10, "preco": 150.0}]
        prices = {"HGLG11": 160.0}
        result = calculate_position_metrics(ops, prices)

        assert "HGLG11" in result
        pos = result["HGLG11"]
        assert pos["quantidade_total"] == 10
        assert pos["preco_medio"] == 150.0
        assert pos["valor_investido"] == 1500.0
        assert pos["valor_atual"] == 1600.0
        assert pos["lucro_prejuizo"] == 100.0
        assert pos["lucro_prejuizo_percentual"] == pytest.approx(6.6667, rel=0.01)

    def test_multiple_buys_average_price(self):
        ops = [
            {"ticker": "HGLG11", "tipo": "compra", "quantidade": 10, "preco": 100.0},
            {"ticker": "HGLG11", "tipo": "compra", "quantidade": 10, "preco": 200.0},
        ]
        prices = {"HGLG11": 150.0}
        result = calculate_position_metrics(ops, prices)

        pos = result["HGLG11"]
        assert pos["quantidade_total"] == 20
        assert pos["preco_medio"] == 150.0
        assert pos["lucro_prejuizo"] == 0.0

    def test_buy_and_partial_sell(self):
        ops = [
            {"ticker": "HGLG11", "tipo": "compra", "quantidade": 20, "preco": 100.0},
            {"ticker": "HGLG11", "tipo": "venda", "quantidade": 10, "preco": 120.0},
        ]
        prices = {"HGLG11": 110.0}
        result = calculate_position_metrics(ops, prices)

        pos = result["HGLG11"]
        assert pos["quantidade_total"] == 10
        assert pos["preco_medio"] == 100.0
        assert pos["valor_investido"] == 1000.0
        assert pos["valor_atual"] == 1100.0

    def test_full_sell_excluded(self):
        ops = [
            {"ticker": "HGLG11", "tipo": "compra", "quantidade": 10, "preco": 100.0},
            {"ticker": "HGLG11", "tipo": "venda", "quantidade": 10, "preco": 120.0},
        ]
        prices = {"HGLG11": 110.0}
        result = calculate_position_metrics(ops, prices)
        assert "HGLG11" not in result

    def test_short_sell_raises(self):
        ops = [
            {"ticker": "HGLG11", "tipo": "compra", "quantidade": 5, "preco": 100.0},
            {"ticker": "HGLG11", "tipo": "venda", "quantidade": 10, "preco": 100.0},
        ]
        prices = {"HGLG11": 100.0}
        with pytest.raises(ValueError, match="descoberto"):
            calculate_position_metrics(ops, prices)

    def test_invalid_tipo_raises(self):
        ops = [{"ticker": "HGLG11", "tipo": "troca", "quantidade": 10, "preco": 100.0}]
        prices = {"HGLG11": 100.0}
        with pytest.raises(ValueError, match="inválido"):
            calculate_position_metrics(ops, prices)

    def test_negative_quantity_raises(self):
        ops = [{"ticker": "HGLG11", "tipo": "compra", "quantidade": -5, "preco": 100.0}]
        prices = {"HGLG11": 100.0}
        with pytest.raises(ValueError, match="negativo"):
            calculate_position_metrics(ops, prices)

    def test_invalid_ticker_raises(self):
        ops = [{"ticker": "", "tipo": "compra", "quantidade": 10, "preco": 100.0}]
        prices = {}
        with pytest.raises(ValueError, match="inválido"):
            calculate_position_metrics(ops, prices)

    def test_multiple_tickers(self):
        ops = [
            {"ticker": "HGLG11", "tipo": "compra", "quantidade": 10, "preco": 100.0},
            {"ticker": "XPML11", "tipo": "compra", "quantidade": 5, "preco": 200.0},
        ]
        prices = {"HGLG11": 110.0, "XPML11": 190.0}
        result = calculate_position_metrics(ops, prices)

        assert len(result) == 2
        assert result["HGLG11"]["lucro_prejuizo"] == 100.0
        assert result["XPML11"]["lucro_prejuizo"] == -50.0

    def test_missing_price_uses_zero(self):
        ops = [{"ticker": "HGLG11", "tipo": "compra", "quantidade": 10, "preco": 100.0}]
        prices = {}
        result = calculate_position_metrics(ops, prices)

        assert result["HGLG11"]["valor_atual"] == 0.0
        assert result["HGLG11"]["lucro_prejuizo"] == -1000.0
