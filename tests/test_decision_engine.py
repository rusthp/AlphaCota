"""Tests for core/decision_engine.py — Orchestrator report generation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from core.decision_engine import generate_decision_report


def _make_fixtures():
    """Shared test fixtures for decision engine."""
    operacoes = [
        {"ticker": "HGLG11", "tipo": "compra", "quantidade": 10, "preco": 150.0},
        {"ticker": "XPML11", "tipo": "compra", "quantidade": 5, "preco": 100.0},
    ]
    precos = {"HGLG11": 160.0, "XPML11": 110.0}
    proventos = [
        {"ticker": "HGLG11", "valor": 80.0},
        {"ticker": "XPML11", "valor": 40.0},
    ]
    alvo = {"HGLG11": 0.60, "XPML11": 0.40}
    return operacoes, precos, proventos, alvo


class TestGenerateDecisionReport:
    def test_returns_all_sections(self):
        ops, precos, provs, alvo = _make_fixtures()
        report = generate_decision_report(ops, precos, provs, alvo, 2000.0, 0.10, 60000.0)

        assert "resumo_carteira" in report
        assert "renda_passiva" in report
        assert "fogo_financeiro" in report
        assert "rebalanceamento" in report

    def test_resumo_carteira_values(self):
        ops, precos, provs, alvo = _make_fixtures()
        report = generate_decision_report(ops, precos, provs, alvo, 2000.0, 0.10, 60000.0)

        resumo = report["resumo_carteira"]
        # HGLG11: 10 * 160 = 1600, XPML11: 5 * 110 = 550
        assert resumo["valor_total"] == pytest.approx(2150.0)
        assert resumo["lucro_prejuizo_total"] == pytest.approx(150.0)  # (1600-1500)=100 + (550-500)=50

    def test_renda_passiva_yield(self):
        ops, precos, provs, alvo = _make_fixtures()
        report = generate_decision_report(ops, precos, provs, alvo, 2000.0, 0.10, 60000.0)

        renda = report["renda_passiva"]
        assert renda["renda_total"] == 120.0
        assert renda["yield_percentual"] > 0

    def test_fire_patrimonio_necessario(self):
        ops, precos, provs, alvo = _make_fixtures()
        report = generate_decision_report(ops, precos, provs, alvo, 2000.0, 0.10, 60000.0)

        fire = report["fogo_financeiro"]
        assert fire["patrimonio_necessario"] == pytest.approx(600000.0)
        assert fire["anos_estimados"] > 0

    def test_rebalanceamento_has_sugestao(self):
        ops, precos, provs, alvo = _make_fixtures()
        report = generate_decision_report(ops, precos, provs, alvo, 2000.0, 0.10, 60000.0)

        rebal = report["rebalanceamento"]
        assert "sugestao" in rebal
        assert isinstance(rebal["sugestao"], list)
        assert len(rebal["sugestao"]) == 2

    def test_empty_portfolio(self):
        report = generate_decision_report(
            operacoes=[],
            precos_atuais={},
            proventos=[],
            alocacao_alvo={},
            aporte_mensal=1000.0,
            taxa_anual_esperada=0.10,
            renda_alvo_anual=60000.0,
        )
        assert report["resumo_carteira"]["valor_total"] == 0.0
        assert report["renda_passiva"]["renda_total"] == 0.0

    def test_unreachable_fire_returns_minus_one(self):
        ops = [{"ticker": "HGLG11", "tipo": "compra", "quantidade": 1, "preco": 10.0}]
        precos = {"HGLG11": 10.0}
        report = generate_decision_report(
            operacoes=ops,
            precos_atuais=precos,
            proventos=[],
            alocacao_alvo={"HGLG11": 1.0},
            aporte_mensal=1.0,
            taxa_anual_esperada=0.001,
            renda_alvo_anual=10000000.0,
        )
        assert report["fogo_financeiro"]["anos_estimados"] == -1.0

    def test_proventos_with_zero_portfolio(self):
        """Proventos exist but all positions are sold."""
        ops = [
            {"ticker": "HGLG11", "tipo": "compra", "quantidade": 10, "preco": 100.0},
            {"ticker": "HGLG11", "tipo": "venda", "quantidade": 10, "preco": 110.0},
        ]
        provs = [{"ticker": "HGLG11", "valor": 50.0}]
        report = generate_decision_report(
            operacoes=ops,
            precos_atuais={"HGLG11": 110.0},
            proventos=provs,
            alocacao_alvo={},
            aporte_mensal=1000.0,
            taxa_anual_esperada=0.10,
            renda_alvo_anual=60000.0,
        )
        assert report["resumo_carteira"]["valor_total"] == 0.0
        assert report["renda_passiva"]["renda_total"] == 50.0
