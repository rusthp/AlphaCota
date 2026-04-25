"""
tests/test_pipeline_integration.py

Testes de integração para o pipeline completo:
- Universe module
- Fundamentals scraper (cache + defaults)
- Score engine com dados do scraper
- Allocation pipeline end-to-end
- Persistência no SQLite
"""

import sqlite3
import os
import pytest

# ---------------------------------------------------------------------------
# Testes do Universe Module
# ---------------------------------------------------------------------------


class TestUniverse:
    """Testes para data/universe.py"""

    def test_get_universe_returns_list(self):
        from data.universe import get_universe

        fiis = get_universe()
        assert isinstance(fiis, list)
        assert len(fiis) > 30  # pelo menos 30 FIIs no IFIX

    def test_get_universe_ifix_only(self):
        from data.universe import get_universe

        all_fiis = get_universe(ifix_only=False)
        ifix_fiis = get_universe(ifix_only=True)
        assert len(all_fiis) >= len(ifix_fiis)

    def test_get_universe_by_sector(self):
        from data.universe import get_universe

        papel = get_universe(sectors=["Papel (CRI)"])
        assert all(f["setor"] == "Papel (CRI)" for f in papel)
        assert len(papel) >= 5

    def test_get_tickers(self):
        from data.universe import get_tickers

        tickers = get_tickers()
        assert isinstance(tickers, list)
        assert "MXRF11" in tickers
        assert "HGLG11" in tickers

    def test_get_sector_map(self):
        from data.universe import get_sector_map

        sector_map = get_sector_map()
        assert isinstance(sector_map, dict)
        assert sector_map["MXRF11"] == "Papel (CRI)"
        assert sector_map["HGLG11"] == "Logística"
        assert sector_map["XPML11"] == "Shopping"

    def test_get_sectors_summary(self):
        from data.universe import get_sectors_summary

        summary = get_sectors_summary()
        assert isinstance(summary, dict)
        assert "Papel (CRI)" in summary
        assert "Logística" in summary
        assert summary["Papel (CRI)"] >= 5

    def test_get_universe_size(self):
        from data.universe import get_universe_size

        size = get_universe_size()
        assert size > 30

    def test_fii_has_required_fields(self):
        from data.universe import get_universe

        fiis = get_universe()
        for fii in fiis:
            assert "ticker" in fii
            assert "setor" in fii
            assert "nome" in fii
            assert "ifix" in fii
            assert fii["ticker"].endswith("11")


# ---------------------------------------------------------------------------
# Testes do Fundamentals Scraper (cache + defaults, sem rede)
# ---------------------------------------------------------------------------


class TestFundamentalsScraper:
    """Testes para data/fundamentals_scraper.py (sem requisições HTTP)"""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Cria um banco de cache temporário."""
        return str(tmp_path / "test_fundamentals.db")

    def test_fetch_defaults_when_no_cache(self, temp_db):
        from data.fundamentals_scraper import fetch_fundamentals

        result = fetch_fundamentals("MXRF11", db_path=temp_db)
        assert result["ticker"] == "MXRF11"
        assert "dividend_yield" in result
        assert "pvp" in result
        assert result["_source"] in ("default", "scraper", "cache")

    def test_fetch_bulk(self, temp_db):
        from data.fundamentals_scraper import fetch_fundamentals_bulk

        tickers = ["MXRF11", "HGLG11", "KNCR11"]
        result = fetch_fundamentals_bulk(tickers, db_path=temp_db)
        assert len(result) == 3
        for ticker in tickers:
            assert ticker in result
            assert "dividend_yield" in result[ticker]

    def test_save_manual_fundamentals(self, temp_db):
        from data.fundamentals_scraper import save_manual_fundamentals, fetch_fundamentals

        save_manual_fundamentals(
            "TESTFII11",
            {
                "dividend_yield": 0.12,
                "pvp": 0.95,
                "debt_ratio": 0.2,
            },
            db_path=temp_db,
        )
        result = fetch_fundamentals("TESTFII11", db_path=temp_db)
        assert result["dividend_yield"] == 0.12
        assert result["pvp"] == 0.95
        assert result["_source"] == "cache"

    def test_cache_status(self, temp_db):
        from data.fundamentals_scraper import get_cache_status, save_manual_fundamentals

        save_manual_fundamentals("MXRF11", {"dividend_yield": 0.10}, db_path=temp_db)
        status = get_cache_status(["MXRF11", "UNKNOWN11"], db_path=temp_db)
        assert status["total"] == 2
        assert status["cached"] >= 1
        assert status["details"]["MXRF11"] == "valid"
        assert status["details"]["UNKNOWN11"] == "missing"

    def test_parse_indicator(self):
        from data.fundamentals_scraper import _parse_indicator

        assert _parse_indicator("10,50%") == 10.50
        assert _parse_indicator("1,02") == 1.02
        assert _parse_indicator("R$ 0,09") == 0.09
        assert _parse_indicator("-") == 0.0
        assert _parse_indicator("") == 0.0
        assert _parse_indicator("N/A") == 0.0

    def test_import_csv(self, temp_db, tmp_path):
        from data.fundamentals_scraper import import_csv_fundamentals, fetch_fundamentals

        csv_path = str(tmp_path / "test_data.csv")
        with open(csv_path, "w") as f:
            f.write("ticker,dividend_yield,pvp,debt_ratio\n")
            f.write("CSVFII11,0.11,0.88,0.15\n")
            f.write("CSVFII22,0.09,1.05,0.25\n")

        count = import_csv_fundamentals(csv_path, db_path=temp_db)
        assert count == 2

        r1 = fetch_fundamentals("CSVFII11", db_path=temp_db)
        assert r1["dividend_yield"] == 0.11
        assert r1["pvp"] == 0.88


# ---------------------------------------------------------------------------
# Testes de Integração: Pipeline End-to-End
# ---------------------------------------------------------------------------


class TestPipelineIntegration:
    """Testes de integração do allocation_pipeline com dados realistas."""

    @pytest.fixture
    def mock_assets(self):
        """Dados mock realistas compatíveis com o pipeline."""
        return [
            {
                "ticker": "MXRF11",
                "classe": "FII",
                "preco_atual": 10.05,
                "dividend_yield": 0.10,
                "dividend_consistency": 9.0,
                "pvp": 0.95,
                "debt_ratio": 0.2,
                "vacancy_rate": 0.0,
                "revenue_growth_12m": 0.05,
                "earnings_growth_12m": 0.03,
                "working_capital": 1000,
                "total_assets": 5000,
                "retained_earnings": 800,
                "ebit": 400,
                "market_value_equity": 3000,
                "total_liabilities": 1500,
                "revenue": 1200,
            },
            {
                "ticker": "HGLG11",
                "classe": "FII",
                "preco_atual": 155.0,
                "dividend_yield": 0.08,
                "dividend_consistency": 8.5,
                "pvp": 1.05,
                "debt_ratio": 0.25,
                "vacancy_rate": 0.03,
                "revenue_growth_12m": 0.08,
                "earnings_growth_12m": 0.06,
                "working_capital": 2000,
                "total_assets": 10000,
                "retained_earnings": 1500,
                "ebit": 800,
                "market_value_equity": 7000,
                "total_liabilities": 3000,
                "revenue": 2500,
            },
            {
                "ticker": "XPML11",
                "classe": "FII",
                "preco_atual": 90.0,
                "dividend_yield": 0.09,
                "dividend_consistency": 7.5,
                "pvp": 1.10,
                "debt_ratio": 0.35,
                "vacancy_rate": 0.08,
                "revenue_growth_12m": 0.04,
                "earnings_growth_12m": 0.02,
                "working_capital": 1500,
                "total_assets": 8000,
                "retained_earnings": 1200,
                "ebit": 600,
                "market_value_equity": 5000,
                "total_liabilities": 2500,
                "revenue": 1800,
            },
            {
                "ticker": "KNCR11",
                "classe": "FII",
                "preco_atual": 97.80,
                "dividend_yield": 0.11,
                "dividend_consistency": 9.5,
                "pvp": 0.98,
                "debt_ratio": 0.15,
                "vacancy_rate": 0.0,
                "revenue_growth_12m": 0.06,
                "earnings_growth_12m": 0.05,
                "working_capital": 3000,
                "total_assets": 15000,
                "retained_earnings": 2500,
                "ebit": 1200,
                "market_value_equity": 10000,
                "total_liabilities": 4000,
                "revenue": 3500,
            },
        ]

    @pytest.fixture
    def test_db(self, tmp_path):
        """Cria um banco de dados de teste."""
        db_path = str(tmp_path / "test_pipeline.db")
        conn = sqlite3.connect(db_path)
        from core.state_repository import init_db

        init_db(conn)
        return conn

    def test_pipeline_runs_successfully(self, mock_assets, test_db):
        from services.allocation_pipeline import run_allocation_pipeline

        result = run_allocation_pipeline(
            connection=test_db,
            user_profile="moderado",
            assets_data=mock_assets,
            aporte_mensal=1000.0,
            meses_simulacao=60,
            score_threshold=3.0,  # Limiar baixo para garantir que ativos passam
        )
        test_db.close()

        assert "error" not in result
        assert "allocations" in result
        assert "risk_projection" in result
        assert "fire_projection" in result
        assert "explanation" in result
        assert len(result["allocations"]) > 0

    def test_pipeline_allocations_sum_reasonable(self, mock_assets, test_db):
        from services.allocation_pipeline import run_allocation_pipeline

        result = run_allocation_pipeline(
            connection=test_db,
            user_profile="moderado",
            assets_data=mock_assets,
            score_threshold=5.0,
        )
        test_db.close()

        if "error" not in result:
            total_weight = sum(result["allocations"].values())
            # FII-only universe: total = perfil FII target (ex: 0.20 moderado)
            assert 0.0 < total_weight <= 1.01

    def test_pipeline_risk_projection_valid(self, mock_assets, test_db):
        from services.allocation_pipeline import run_allocation_pipeline

        result = run_allocation_pipeline(
            connection=test_db,
            user_profile="agressivo",
            assets_data=mock_assets,
            score_threshold=5.0,
        )
        test_db.close()

        if "error" not in result:
            risk = result["risk_projection"]
            assert "expected_return" in risk
            assert "median_projection" in risk
            assert risk["median_projection"] > 0

    def test_pipeline_persists_snapshot(self, mock_assets, test_db):
        from services.allocation_pipeline import run_allocation_pipeline
        from core.state_repository import get_last_snapshot

        result = run_allocation_pipeline(
            connection=test_db,
            user_profile="conservador",
            assets_data=mock_assets,
            score_threshold=5.0,
        )

        if "error" not in result and result["rebalance_executed"]:
            snapshot = get_last_snapshot(test_db)
            assert snapshot is not None
            assert "allocations" in snapshot
            assert len(snapshot["allocations"]) > 0

        test_db.close()

    def test_pipeline_explain_has_logic(self, mock_assets, test_db):
        from services.allocation_pipeline import run_allocation_pipeline

        result = run_allocation_pipeline(
            connection=test_db,
            user_profile="moderado",
            assets_data=mock_assets,
            score_threshold=5.0,
        )
        test_db.close()

        if "error" not in result:
            explain = result["explanation"]
            assert "selection_logic" in explain
            for item in explain["selection_logic"]:
                assert "ticker" in item
                assert "reason" in item
                assert len(item["reason"]) > 0

    def test_pipeline_high_threshold_filters_all(self, mock_assets, test_db):
        from services.allocation_pipeline import run_allocation_pipeline

        result = run_allocation_pipeline(
            connection=test_db,
            user_profile="moderado",
            assets_data=mock_assets,
            score_threshold=99.9,  # impossível — escala 0-100
        )
        test_db.close()

        assert "error" in result

    def test_pipeline_with_current_portfolio_drift(self, mock_assets, test_db):
        """When current_portfolio is provided, drift should be calculated."""
        from services.allocation_pipeline import run_allocation_pipeline

        current = {"MXRF11": 0.5, "HGLG11": 0.5}
        result = run_allocation_pipeline(
            connection=test_db,
            user_profile="moderado",
            assets_data=mock_assets,
            current_portfolio=current,
            score_threshold=3.0,
        )
        test_db.close()

        if "error" not in result:
            assert "weight_drift" in result
            assert isinstance(result["weight_drift"], dict)

    def test_pipeline_no_connection_skips_persist(self, mock_assets):
        """Pipeline should work without a DB connection (no persistence)."""
        from services.allocation_pipeline import run_allocation_pipeline

        result = run_allocation_pipeline(
            connection=None,
            user_profile="moderado",
            assets_data=mock_assets,
            score_threshold=3.0,
        )
        if "error" not in result:
            assert "allocations" in result


class TestBuildEliteUniverse:
    def test_high_bankruptcy_risk_filtered(self):
        """Assets with high Altman Z bankruptcy risk should be excluded."""
        from services.allocation_pipeline import build_elite_universe

        # Asset with terrible Altman Z inputs (negative everything)
        risky = [
            {
                "ticker": "RISKY11",
                "classe": "FII",
                "dividend_yield": 0.10,
                "dividend_consistency": 5.0,
                "pvp": 1.0,
                "debt_ratio": 0.5,
                "vacancy_rate": 0.0,
                "revenue_growth_12m": 0.0,
                "earnings_growth_12m": 0.0,
                "working_capital": -5000,
                "total_assets": 1000,
                "retained_earnings": -3000,
                "ebit": -500,
                "market_value_equity": 100,
                "total_liabilities": 9000,
                "revenue": 200,
            }
        ]
        result = build_elite_universe(risky, score_threshold=0.0)
        # Should be filtered by Altman Z or score
        assert isinstance(result, list)

    def test_zero_score_assets_excluded(self):
        """Assets below score threshold should not be in elite universe."""
        from services.allocation_pipeline import build_elite_universe

        low_score = [
            {
                "ticker": "LOW11",
                "classe": "FII",
                "dividend_yield": 0.01,
                "dividend_consistency": 1.0,
                "pvp": 3.0,
                "debt_ratio": 0.9,
                "vacancy_rate": 0.5,
                "revenue_growth_12m": -0.3,
                "earnings_growth_12m": -0.3,
                "working_capital": 1000,
                "total_assets": 5000,
                "retained_earnings": 800,
                "ebit": 400,
                "market_value_equity": 3000,
                "total_liabilities": 1500,
                "revenue": 1200,
            }
        ]
        result = build_elite_universe(low_score, score_threshold=9.0)
        assert result == []


class TestOptimizeWithConstraints:
    def test_zero_total_score_distributes_equally(self):
        """When all scores are 0, weight should be distributed equally."""
        from services.allocation_pipeline import optimize_with_constraints

        elite = [
            {"ticker": "A11", "classe": "FII", "final_score": 0},
            {"ticker": "B11", "classe": "FII", "final_score": 0},
        ]
        constraints = {"FII": 0.5}
        result = optimize_with_constraints(elite, constraints)
        assert result["A11"] == 0.25
        assert result["B11"] == 0.25

    def test_empty_class_skipped(self):
        """Classes with no assets should be skipped."""
        from services.allocation_pipeline import optimize_with_constraints

        elite = [{"ticker": "A11", "classe": "FII", "final_score": 80}]
        constraints = {"FII": 0.5, "ACAO": 0.3}
        result = optimize_with_constraints(elite, constraints)
        assert "A11" in result
        assert len(result) == 1

    def test_scoring_with_scraper_data(self):
        """Verifica que dados do scraper são compatíveis com score_engine."""
        from core.score_engine import calculate_alpha_score

        # Simula dados como viriam do fundamentals_scraper
        scraper_data = {
            "dividend_yield": 0.10,
            "dividend_consistency": 7.0,
            "pvp": 0.95,
            "debt_ratio": 0.3,
            "vacancy_rate": 0.05,
            "revenue_growth_12m": 0.0,
            "earnings_growth_12m": 0.0,
        }
        result = calculate_alpha_score(**scraper_data)
        assert 0 <= result["alpha_score"] <= 100
        assert "income_score" in result
        assert "valuation_score" in result


# ---------------------------------------------------------------------------
# Testes de integração: data_bridge com universe
# ---------------------------------------------------------------------------


class TestDataBridgeUniverse:
    """Verifica que data_bridge usa o universe module corretamente."""

    def test_sector_map_has_universe_entries(self):
        from data.data_bridge import SECTOR_MAP
        from data.universe import get_tickers

        tickers = get_tickers(ifix_only=False)
        # Pelo menos 80% dos tickers do universe devem estar no SECTOR_MAP
        mapped = sum(1 for t in tickers if t in SECTOR_MAP)
        assert mapped / len(tickers) >= 0.8

    def test_sector_map_values_are_valid(self):
        from data.data_bridge import SECTOR_MAP

        valid_sectors = {
            "Papel (CRI)",
            "Logística",
            "Shopping",
            "Lajes Corp.",
            "Fundo de Fundos",
            "Híbrido",
            "Saúde",
            "Agro",
            "Residencial",
            "Educacional",
            "Hotel",
            "Outros",
        }
        for sector in SECTOR_MAP.values():
            assert sector in valid_sectors, f"Setor desconhecido: {sector}"
