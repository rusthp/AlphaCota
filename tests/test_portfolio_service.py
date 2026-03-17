"""Tests for services/portfolio_service.py — Full cycle orchestrator."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.portfolio_service import run_full_cycle


class TestRunFullCycle:
    def test_returns_report(self):
        mock_ops = [{"ticker": "HGLG11", "tipo": "compra", "quantidade": 10, "preco": 150.0}]
        mock_provs = [{"ticker": "HGLG11", "valor": 50.0}]
        mock_report = {
            "resumo_carteira": {"valor_total": 1600.0},
            "renda_passiva": {"renda_total": 50.0},
            "fogo_financeiro": {"patrimonio_necessario": 600000.0},
            "rebalanceamento": {"sugestao": []},
        }

        with patch("services.portfolio_service.get_operations", return_value=mock_ops), \
             patch("services.portfolio_service.get_proventos", return_value=mock_provs), \
             patch("services.portfolio_service.generate_decision_report", return_value=mock_report), \
             patch("services.portfolio_service.save_portfolio_snapshot") as mock_save:
            result = run_full_cycle(
                user_id=1,
                precos_atuais={"HGLG11": 160.0},
                alocacao_alvo={"HGLG11": 1.0},
                aporte_mensal=1000.0,
                taxa_anual_esperada=0.10,
                renda_alvo_anual=60000.0,
            )
            assert result == mock_report
            mock_save.assert_called_once_with(1, mock_report)

    def test_empty_portfolio(self):
        mock_report = {
            "resumo_carteira": {"valor_total": 0.0},
            "renda_passiva": {},
            "fogo_financeiro": {},
            "rebalanceamento": {"sugestao": []},
        }

        with patch("services.portfolio_service.get_operations", return_value=[]), \
             patch("services.portfolio_service.get_proventos", return_value=[]), \
             patch("services.portfolio_service.generate_decision_report", return_value=mock_report), \
             patch("services.portfolio_service.save_portfolio_snapshot"):
            result = run_full_cycle(1, {}, {}, 0, 0.10, 60000)
            assert result["resumo_carteira"]["valor_total"] == 0.0
