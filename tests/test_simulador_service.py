"""Tests for services/simulador_service.py — Portfolio simulation engines."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from services.simulador_service import (
    simulate_12_months,
    simulate_with_growth,
    simulate_with_growth_and_shock,
    compare_profiles_under_scenario,
    simulate_stochastic,
    simulate_monte_carlo,
)


@pytest.fixture
def base_portfolio():
    return [
        {"ticker": "IVVB11", "classe": "ETF", "quantidade": 10, "preco_atual": 250.0},
        {"ticker": "BBSE3", "classe": "ACAO", "quantidade": 20, "preco_atual": 30.0},
        {"ticker": "MXRF11", "classe": "FII", "quantidade": 50, "preco_atual": 10.0},
    ]


@pytest.fixture
def base_universe():
    return [
        {"ticker": "IVVB11", "classe": "ETF", "ativo": True, "preco_atual": 250.0},
        {"ticker": "BNDX11", "classe": "ETF", "ativo": True, "preco_atual": 100.0},
        {"ticker": "BBSE3", "classe": "ACAO", "ativo": True, "preco_atual": 30.0},
        {"ticker": "WEGE3", "classe": "ACAO", "ativo": True, "preco_atual": 40.0},
        {"ticker": "MXRF11", "classe": "FII", "ativo": True, "preco_atual": 10.0},
    ]


@pytest.fixture
def target_allocation():
    return {"ETF": 0.50, "ACAO": 0.30, "FII": 0.20}


@pytest.fixture
def growth_rates():
    return {"ETF": 0.10, "ACAO": 0.12, "FII": 0.08}


@pytest.fixture
def volatilities():
    return {"ETF": 0.15, "ACAO": 0.25, "FII": 0.10}


class TestSimulate12Months:
    def test_returns_structure(self, base_portfolio, base_universe, target_allocation):
        result = simulate_12_months(base_portfolio, base_universe, target_allocation, 500.0, 3)
        assert "historico_mensal" in result
        assert "valor_final" in result
        assert "composicao_final" in result
        assert len(result["historico_mensal"]) == 3

    def test_value_increases_with_aportes(self, base_portfolio, base_universe, target_allocation):
        result = simulate_12_months(base_portfolio, base_universe, target_allocation, 1000.0, 6)
        initial_value = sum(a["quantidade"] * a["preco_atual"] for a in base_portfolio)
        assert result["valor_final"] >= initial_value

    def test_empty_portfolio(self, base_universe, target_allocation):
        result = simulate_12_months([], base_universe, target_allocation, 500.0, 3)
        assert result["valor_final"] >= 0

    def test_does_not_mutate_input(self, base_portfolio, base_universe, target_allocation):
        original_qty = base_portfolio[0]["quantidade"]
        simulate_12_months(base_portfolio, base_universe, target_allocation, 500.0, 3)
        assert base_portfolio[0]["quantidade"] == original_qty


class TestSimulateWithGrowth:
    def test_prices_grow(self, base_portfolio, base_universe, target_allocation, growth_rates):
        result = simulate_with_growth(base_portfolio, base_universe, target_allocation, 500.0, growth_rates, 6)
        assert result["valor_final"] > 0
        last_prices = result["historico_mensal"][-1]["precos_atuais"]
        assert "IVVB11" in last_prices

    def test_structure(self, base_portfolio, base_universe, target_allocation, growth_rates):
        result = simulate_with_growth(base_portfolio, base_universe, target_allocation, 500.0, growth_rates, 3)
        assert len(result["historico_mensal"]) == 3


class TestSimulateWithGrowthAndShock:
    def test_shock_applied(self, base_portfolio, base_universe, target_allocation, growth_rates):
        shock = {"mes": 3, "impacto": {"ETF": -0.20, "ACAO": -0.30, "FII": -0.15}}
        result = simulate_with_growth_and_shock(
            base_portfolio, base_universe, target_allocation, 500.0, growth_rates, shock, 6
        )
        shock_snap = result["historico_mensal"][2]
        assert shock_snap["shock_aplicado"] is True
        non_shock = result["historico_mensal"][0]
        assert non_shock["shock_aplicado"] is False

    def test_value_drops_on_shock(self, base_portfolio, base_universe, target_allocation, growth_rates):
        shock = {"mes": 2, "impacto": {"ETF": -0.50, "ACAO": -0.50, "FII": -0.50}}
        result = simulate_with_growth_and_shock(
            base_portfolio, base_universe, target_allocation, 100.0, growth_rates, shock, 3
        )
        val_before = result["historico_mensal"][0]["valor_total"]
        val_shock = result["historico_mensal"][1]["valor_total"]
        assert val_shock < val_before


class TestCompareProfilesUnderScenario:
    def test_returns_all_profiles(self, base_portfolio, base_universe, growth_rates):
        shock = {"mes": 3, "impacto": {"ETF": -0.10, "ACAO": -0.20, "FII": -0.05}}
        result = compare_profiles_under_scenario(
            ["conservador", "moderado", "agressivo"], base_portfolio, base_universe, 500.0, growth_rates, shock, 6
        )
        assert "conservador" in result
        assert "moderado" in result
        assert "agressivo" in result
        for perfil in result.values():
            assert "valor_final" in perfil
            assert "maior_drawdown_percentual" in perfil
            assert "meses_para_recuperacao" in perfil


class TestSimulateStochastic:
    def test_returns_structure(self, base_portfolio, base_universe, target_allocation, growth_rates, volatilities):
        result = simulate_stochastic(
            base_portfolio, base_universe, target_allocation, 500.0, growth_rates, volatilities, 6
        )
        assert "valor_final" in result
        assert "drawdown_maximo" in result
        assert "retornos_mensais" in result
        assert len(result["retornos_mensais"]) == 6

    def test_positive_value(self, base_portfolio, base_universe, target_allocation, growth_rates, volatilities):
        result = simulate_stochastic(
            base_portfolio, base_universe, target_allocation, 500.0, growth_rates, volatilities, 3
        )
        assert result["valor_final"] > 0


class TestSimulateMonteCarlo:
    def test_returns_statistics(self, base_portfolio, base_universe, target_allocation, growth_rates, volatilities):
        result = simulate_monte_carlo(
            base_portfolio, base_universe, target_allocation, 500.0, growth_rates, volatilities, meses=3, simulacoes=10
        )
        assert "media_valor_final" in result
        assert "mediana_valor_final" in result
        assert "percentil_10" in result
        assert "percentil_90" in result
        assert "probabilidade_prejuizo" in result
        assert "sharpe_ratio_medio" in result
        assert len(result["valores_finais_lista"]) == 10

    def test_more_sims_smoother(self, base_portfolio, base_universe, target_allocation, growth_rates, volatilities):
        result = simulate_monte_carlo(
            base_portfolio, base_universe, target_allocation, 500.0, growth_rates, volatilities, meses=3, simulacoes=20
        )
        assert result["percentil_10"] <= result["mediana_valor_final"] <= result["percentil_90"]

    def test_zero_simulacoes_returns_empty(self, base_portfolio, base_universe, target_allocation, growth_rates, volatilities):
        """simulate_monte_carlo with simulacoes=0 returns {} immediately (line 559)."""
        result = simulate_monte_carlo(
            base_portfolio, base_universe, target_allocation, 500.0, growth_rates, volatilities, meses=3, simulacoes=0
        )
        assert result == {}


class TestSimulateWithGrowthEmptyPortfolio:
    """Cover the empty-portfolio branch in simulate_with_growth (line 128)."""

    def test_empty_portfolio_still_returns_structure(self):
        universe = [
            {"ticker": "IVVB11", "classe": "ETF", "ativo": True, "preco_atual": 250.0},
            {"ticker": "MXRF11", "classe": "FII", "ativo": True, "preco_atual": 10.0},
        ]
        allocation = {"ETF": 0.60, "FII": 0.40}
        growth = {"ETF": 0.10, "FII": 0.08}

        result = simulate_with_growth([], universe, allocation, 500.0, growth, meses=3)

        assert "historico_mensal" in result
        assert "valor_final" in result
        assert len(result["historico_mensal"]) == 3


class TestSimulateWithGrowthAndShockEmptyPortfolio:
    """Cover the empty-portfolio branch in simulate_with_growth_and_shock (line 244)."""

    def test_empty_portfolio_shock_returns_structure(self):
        from services.simulador_service import simulate_with_growth_and_shock

        universe = [
            {"ticker": "IVVB11", "classe": "ETF", "ativo": True, "preco_atual": 250.0},
        ]
        allocation = {"ETF": 1.0}
        growth = {"ETF": 0.10}
        shock = {"mes": 2, "impacto": {"ETF": -0.20}}

        result = simulate_with_growth_and_shock([], universe, allocation, 500.0, growth, shock, meses=3)

        assert "historico_mensal" in result
        assert len(result["historico_mensal"]) == 3


class TestSimulateStochasticEdgeCases:
    """Cover price-floor, zero-valor_anterior, and empty-portfolio branches."""

    def test_empty_portfolio_stochastic(self):
        """Empty portfolio triggers the empty-portfolio branch (line 444)."""
        from services.simulador_service import simulate_stochastic

        universe = [{"ticker": "MXRF11", "classe": "FII", "ativo": True, "preco_atual": 10.0}]
        allocation = {"FII": 1.0}
        growth = {"FII": 0.08}
        vols = {"FII": 0.10}

        result = simulate_stochastic([], universe, allocation, 500.0, growth, vols, meses=3)
        assert "valor_final" in result
        assert "retornos_mensais" in result

    def test_price_floor_triggered_by_extreme_negative_return(self):
        """Extreme negative returns drive preco_atual below 0.01 — floor clamps to 0.01 (lines 424-432)."""
        from unittest.mock import patch
        from services.simulador_service import simulate_stochastic

        portfolio = [{"ticker": "X11", "classe": "FII", "quantidade": 1, "preco_atual": 0.001}]
        universe = [{"ticker": "X11", "classe": "FII", "ativo": True, "preco_atual": 0.001}]
        allocation = {"FII": 1.0}
        growth = {"FII": -0.99}
        vols = {"FII": 0.01}

        # Force gauss to return a deeply negative value every call
        with patch("services.simulador_service.random.gauss", return_value=-0.999):
            result = simulate_stochastic(portfolio, universe, allocation, 0.0, growth, vols, meses=2)

        # Price floor ensures result is non-negative
        assert result["valor_final"] >= 0

    def test_zero_valor_anterior_gives_zero_monthly_return(self):
        """When valor_anterior == 0 (zero-quantity portfolio), first retorno_mensal is 0.0 (line 439)."""
        from services.simulador_service import simulate_stochastic

        # quantidade=0 → initial value = 0 → valor_anterior = 0
        portfolio = [{"ticker": "MXRF11", "classe": "FII", "quantidade": 0, "preco_atual": 10.0}]
        universe = [{"ticker": "MXRF11", "classe": "FII", "ativo": True, "preco_atual": 10.0}]
        allocation = {"FII": 1.0}
        growth = {"FII": 0.08}
        vols = {"FII": 0.10}

        result = simulate_stochastic(portfolio, universe, allocation, 100.0, growth, vols, meses=2)
        # First month: valor_anterior was 0 so retorno_mensal = 0.0
        assert result["retornos_mensais"][0] == pytest.approx(0.0)


class TestCompareProfilesDrawdownRecovery:
    """Cover the still-in-drawdown branch at simulation end (lines 375-377)."""

    def test_portfolio_ends_still_in_drawdown(self):
        """A severe shock at the last month ensures the portfolio ends below its peak,
        so in_drawdown is still True when the loop finishes — covering lines 375-377."""
        portfolio = [
            {"ticker": "IVVB11", "classe": "ETF", "quantidade": 10, "preco_atual": 250.0},
        ]
        universe = [
            {"ticker": "IVVB11", "classe": "ETF", "ativo": True, "preco_atual": 250.0},
        ]
        # -80% shock at the final month — portfolio cannot recover by end
        shock = {"mes": 3, "impacto": {"ETF": -0.80}}
        growth = {"ETF": 0.05}

        result = compare_profiles_under_scenario(
            ["conservador"],
            portfolio,
            universe,
            aporte_mensal=0.0,
            growth_rates=growth,
            shock_event=shock,
            meses=3,
        )

        conservador = result["conservador"]
        assert "meses_para_recuperacao" in conservador
        # Portfolio ends in drawdown — recovery time was computed from the still-active path
        assert conservador["maior_drawdown_percentual"] > 0
        assert conservador["meses_para_recuperacao"] >= 0
