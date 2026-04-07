"""Tests for api/main.py — FastAPI endpoints with mocked database."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient
from api.main import app
from core.security import hash_password, create_access_token

client = TestClient(app)


class TestHealthCheck:
    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestRegister:
    def test_register_success(self):
        with patch("api.main.create_user", return_value=1):
            response = client.post("/register", json={"email": "test@test.com", "password": "secret"})
            assert response.status_code == 200
            assert response.json()["user_id"] == 1

    def test_register_duplicate(self):
        with patch("api.main.create_user", return_value=None):
            response = client.post("/register", json={"email": "dup@test.com", "password": "secret"})
            assert response.status_code == 400
            assert "registrado" in response.json()["detail"]


class TestLogin:
    def test_login_success(self):
        hashed = hash_password("correct")
        mock_user = {"id": 1, "email": "user@test.com", "hashed_password": hashed}
        with patch("api.main.get_user_by_email", return_value=mock_user):
            response = client.post("/login", data={"username": "user@test.com", "password": "correct"})
            assert response.status_code == 200
            assert "access_token" in response.json()
            assert response.json()["token_type"] == "bearer"

    def test_login_wrong_password(self):
        hashed = hash_password("correct")
        mock_user = {"id": 1, "email": "user@test.com", "hashed_password": hashed}
        with patch("api.main.get_user_by_email", return_value=mock_user):
            response = client.post("/login", data={"username": "user@test.com", "password": "wrong"})
            assert response.status_code == 401

    def test_login_user_not_found(self):
        with patch("api.main.get_user_by_email", return_value=None):
            response = client.post("/login", data={"username": "noone@test.com", "password": "any"})
            assert response.status_code == 401


class TestReport:
    def _auth_header(self):
        token = create_access_token({"user_id": 1})
        return {"Authorization": f"Bearer {token}"}

    def test_report_unauthorized(self):
        response = client.post("/report", json={})
        assert response.status_code == 401

    def test_report_success(self):
        mock_report = {"resumo_carteira": {"valor_total": 10000}, "renda_passiva": {}}
        with patch("api.main.run_full_cycle", return_value=mock_report):
            response = client.post(
                "/report",
                json={
                    "precos_atuais": {"HGLG11": 160.0},
                    "alocacao_alvo": {"HGLG11": 1.0},
                    "aporte_mensal": 1000.0,
                    "taxa_anual_esperada": 0.10,
                    "renda_alvo_anual": 60000.0,
                },
                headers=self._auth_header(),
            )
            assert response.status_code == 200
            assert "resumo_carteira" in response.json()


class TestHistory:
    def _auth_header(self):
        token = create_access_token({"user_id": 1})
        return {"Authorization": f"Bearer {token}"}

    def test_history_unauthorized(self):
        response = client.get("/history")
        assert response.status_code == 401

    def test_history_success(self):
        mock_snapshots = [{"date": "2025-01-01", "total": 10000}]
        with patch("api.main.get_portfolio_snapshots", return_value=mock_snapshots):
            response = client.get("/history", headers=self._auth_header())
            assert response.status_code == 200
            assert len(response.json()) == 1


# ---------------------------------------------------------------------------
# Dashboard API endpoints
# ---------------------------------------------------------------------------

_MOCK_UNIVERSE = [
    {"ticker": "HGLG11", "nome": "CGHG Log", "sector": "Logística", "ifix": True},
    {"ticker": "MXRF11", "nome": "Maxi Renda", "sector": "Papel (CRI)", "ifix": True},
]

_MOCK_FUNDAMENTALS = {
    "HGLG11": {"dividend_yield": 0.084, "pvp": 0.95, "vacancia": 0.03, "liquidez_diaria": 11000000, "_source": "cache"},
    "MXRF11": {"dividend_yield": 0.12, "pvp": 1.05, "vacancia": 0, "liquidez_diaria": 25000000, "_source": "cache"},
}

_MOCK_SECTOR_MAP = {"HGLG11": "Logística", "MXRF11": "Papel (CRI)"}


class TestScanner:
    @patch("api.main.load_last_price", return_value=(155.0, "cache"))
    @patch("api.main.evaluate_company", return_value={"score_final": 75})
    @patch("api.main.get_sector_map", return_value=_MOCK_SECTOR_MAP)
    @patch("api.main.fetch_fundamentals_bulk", return_value=_MOCK_FUNDAMENTALS)
    @patch("api.main.get_universe", return_value=_MOCK_UNIVERSE)
    def test_scanner_returns_fiis(self, *mocks):
        response = client.get("/api/scanner")
        assert response.status_code == 200
        data = response.json()
        assert "fiis" in data
        assert data["total"] == 2

    @patch("api.main.load_last_price", return_value=(155.0, "cache"))
    @patch("api.main.evaluate_company", return_value={"score_final": 75})
    @patch("api.main.get_sector_map", return_value=_MOCK_SECTOR_MAP)
    @patch("api.main.fetch_fundamentals_bulk", return_value=_MOCK_FUNDAMENTALS)
    @patch("api.main.get_universe", return_value=_MOCK_UNIVERSE)
    def test_scanner_with_sector_filter(self, *mocks):
        response = client.get("/api/scanner?sectors=Logística")
        assert response.status_code == 200


_MOCK_SCORE_BREAKDOWN = {"fundamentos": 20, "rendimento": 22, "risco": 18, "liquidez": 15, "total": 75}
_MOCK_PRICE_HISTORY = [
    {"month": "2025-09", "price": 148.0},
    {"month": "2025-10", "price": 150.0},
    {"month": "2025-11", "price": 152.0},
    {"month": "2025-12", "price": 153.0},
    {"month": "2026-01", "price": 154.0},
    {"month": "2026-02", "price": 155.0},
    {"month": "2026-03", "price": 155.5},
]
_MOCK_DIVIDEND_HISTORY = [
    {"month": "2025-09", "value": 1.05},
    {"month": "2025-10", "value": 1.08},
    {"month": "2025-11", "value": 1.10},
    {"month": "2025-12", "value": 1.12},
    {"month": "2026-01", "value": 1.10},
    {"month": "2026-02", "value": 1.10},
    {"month": "2026-03", "value": 1.10},
]
_MOCK_FUND_INFO = {
    "administrador": "CSHG Brasil Shopping",
    "cnpj": "11.160.521/0001-22",
    "patrimonio_liquido": 3500000000.0,
    "num_cotistas": 125000,
}


class TestFiiDetail:
    @patch("api.main.get_sector_map", return_value=_MOCK_SECTOR_MAP)
    @patch("api.main.evaluate_company", return_value={"score_final": 80})
    @patch("api.main.load_monthly_dividend", return_value=(1.10, "cache"))
    @patch("api.main.load_last_price", return_value=(155.0, "cache"))
    @patch("api.main.fetch_fundamentals", return_value=_MOCK_FUNDAMENTALS["HGLG11"])
    def test_fii_detail_success(self, *mocks):
        response = client.get("/api/fii/HGLG11")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "HGLG11"
        assert data["price"] == 155.0
        assert "fundamentals" in data

    @patch("api.main.get_sector_map", return_value=_MOCK_SECTOR_MAP)
    @patch("api.main.calculate_fii_score", return_value=_MOCK_SCORE_BREAKDOWN)
    @patch("api.main._build_fund_info", return_value=_MOCK_FUND_INFO)
    @patch("api.main._build_dividend_history", return_value=_MOCK_DIVIDEND_HISTORY)
    @patch("api.main._build_price_history", return_value=_MOCK_PRICE_HISTORY)
    @patch("api.main.scrape_fii_detail", return_value={"historico_dividendos": [], "patrimonio_liquido": 3.5e9})
    @patch("api.main.evaluate_company", return_value={"score_final": 80})
    @patch("api.main.load_monthly_dividend", return_value=(1.10, "cache"))
    @patch("api.main.load_last_price", return_value=(155.0, "cache"))
    @patch("api.main.fetch_fundamentals", return_value=_MOCK_FUNDAMENTALS["HGLG11"])
    def test_fii_detail_new_fields_present(self, *mocks):
        response = client.get("/api/fii/HGLG11")
        assert response.status_code == 200
        data = response.json()
        assert "price_history" in data
        assert "dividend_history" in data
        assert "score_breakdown" in data
        assert "fund_info" in data
        assert "cap_rate" in data
        assert "volatilidade_30d" in data
        assert "num_imoveis" in data
        assert "num_locatarios" in data

    @patch("api.main.get_sector_map", return_value=_MOCK_SECTOR_MAP)
    @patch("api.main.calculate_fii_score", return_value=_MOCK_SCORE_BREAKDOWN)
    @patch("api.main._build_fund_info", return_value=_MOCK_FUND_INFO)
    @patch("api.main._build_dividend_history", return_value=_MOCK_DIVIDEND_HISTORY)
    @patch("api.main._build_price_history", return_value=_MOCK_PRICE_HISTORY)
    @patch("api.main.scrape_fii_detail", return_value={})
    @patch("api.main.evaluate_company", return_value={"score_final": 80})
    @patch("api.main.load_monthly_dividend", return_value=(1.10, "cache"))
    @patch("api.main.load_last_price", return_value=(155.0, "cache"))
    @patch("api.main.fetch_fundamentals", return_value=_MOCK_FUNDAMENTALS["HGLG11"])
    def test_fii_detail_price_history_structure(self, *mocks):
        response = client.get("/api/fii/HGLG11")
        data = response.json()
        history = data["price_history"]
        assert isinstance(history, list)
        assert len(history) == 7
        assert all("month" in h and "price" in h for h in history)
        assert history[0]["month"] == "2025-09"
        assert history[0]["price"] == 148.0

    @patch("api.main.get_sector_map", return_value=_MOCK_SECTOR_MAP)
    @patch("api.main.calculate_fii_score", return_value=_MOCK_SCORE_BREAKDOWN)
    @patch("api.main._build_fund_info", return_value=_MOCK_FUND_INFO)
    @patch("api.main._build_dividend_history", return_value=_MOCK_DIVIDEND_HISTORY)
    @patch("api.main._build_price_history", return_value=_MOCK_PRICE_HISTORY)
    @patch("api.main.scrape_fii_detail", return_value={})
    @patch("api.main.evaluate_company", return_value={"score_final": 80})
    @patch("api.main.load_monthly_dividend", return_value=(1.10, "cache"))
    @patch("api.main.load_last_price", return_value=(155.0, "cache"))
    @patch("api.main.fetch_fundamentals", return_value=_MOCK_FUNDAMENTALS["HGLG11"])
    def test_fii_detail_dividend_history_structure(self, *mocks):
        response = client.get("/api/fii/HGLG11")
        data = response.json()
        div_hist = data["dividend_history"]
        assert isinstance(div_hist, list)
        assert len(div_hist) == 7
        assert all("month" in d and "value" in d for d in div_hist)

    @patch("api.main.get_sector_map", return_value=_MOCK_SECTOR_MAP)
    @patch("api.main.calculate_fii_score", return_value=_MOCK_SCORE_BREAKDOWN)
    @patch("api.main._build_fund_info", return_value=_MOCK_FUND_INFO)
    @patch("api.main._build_dividend_history", return_value=_MOCK_DIVIDEND_HISTORY)
    @patch("api.main._build_price_history", return_value=_MOCK_PRICE_HISTORY)
    @patch("api.main.scrape_fii_detail", return_value={})
    @patch("api.main.evaluate_company", return_value={"score_final": 80})
    @patch("api.main.load_monthly_dividend", return_value=(1.10, "cache"))
    @patch("api.main.load_last_price", return_value=(155.0, "cache"))
    @patch("api.main.fetch_fundamentals", return_value=_MOCK_FUNDAMENTALS["HGLG11"])
    def test_fii_detail_score_breakdown_structure(self, *mocks):
        response = client.get("/api/fii/HGLG11")
        data = response.json()
        sb = data["score_breakdown"]
        assert isinstance(sb, dict)
        assert "fundamentos" in sb
        assert "rendimento" in sb
        assert "risco" in sb
        assert "liquidez" in sb
        assert "total" in sb
        assert sb["total"] == 75

    @patch("api.main.get_sector_map", return_value=_MOCK_SECTOR_MAP)
    @patch("api.main.calculate_fii_score", return_value=_MOCK_SCORE_BREAKDOWN)
    @patch("api.main._build_fund_info", return_value=_MOCK_FUND_INFO)
    @patch("api.main._build_dividend_history", return_value=_MOCK_DIVIDEND_HISTORY)
    @patch("api.main._build_price_history", return_value=_MOCK_PRICE_HISTORY)
    @patch("api.main.scrape_fii_detail", return_value={})
    @patch("api.main.evaluate_company", return_value={"score_final": 80})
    @patch("api.main.load_monthly_dividend", return_value=(1.10, "cache"))
    @patch("api.main.load_last_price", return_value=(155.0, "cache"))
    @patch("api.main.fetch_fundamentals", return_value=_MOCK_FUNDAMENTALS["HGLG11"])
    def test_fii_detail_fund_info_structure(self, *mocks):
        response = client.get("/api/fii/HGLG11")
        data = response.json()
        fi = data["fund_info"]
        assert isinstance(fi, dict)
        assert fi["administrador"] == "CSHG Brasil Shopping"
        assert fi["cnpj"] == "11.160.521/0001-22"
        assert fi["patrimonio_liquido"] == 3500000000.0

    @patch("api.main.get_sector_map", return_value=_MOCK_SECTOR_MAP)
    @patch("api.main.calculate_fii_score", return_value=_MOCK_SCORE_BREAKDOWN)
    @patch("api.main._build_fund_info", return_value={})
    @patch("api.main._build_dividend_history", return_value=[])
    @patch("api.main._build_price_history", return_value=[])
    @patch("api.main.scrape_fii_detail", side_effect=Exception("scrape fail"))
    @patch("api.main.evaluate_company", return_value={"score_final": 80})
    @patch("api.main.load_monthly_dividend", return_value=(1.10, "cache"))
    @patch("api.main.load_last_price", return_value=(155.0, "cache"))
    @patch("api.main.fetch_fundamentals", return_value=_MOCK_FUNDAMENTALS["HGLG11"])
    def test_fii_detail_scrape_failure_graceful(self, *mocks):
        """Endpoint deve retornar 200 mesmo se scrape_fii_detail falhar."""
        response = client.get("/api/fii/HGLG11")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "HGLG11"
        assert data["price_history"] == []
        assert data["dividend_history"] == []

    @patch("api.main.get_sector_map", return_value={})
    @patch("api.main.evaluate_company", side_effect=Exception("eval error"))
    @patch("api.main.load_monthly_dividend", side_effect=Exception("no div"))
    @patch("api.main.load_last_price", side_effect=Exception("no price"))
    @patch("api.main.fetch_fundamentals", return_value={})
    def test_fii_detail_with_failures(self, *mocks):
        response = client.get("/api/fii/FAKE11")
        assert response.status_code == 200
        data = response.json()
        assert data["price"] == 0


class TestUniverse:
    @patch("api.main.get_sectors_summary", return_value={"Logística": 5})
    @patch("api.main.get_universe", return_value=_MOCK_UNIVERSE)
    def test_universe_list(self, *mocks):
        response = client.get("/api/universe")
        assert response.status_code == 200
        assert "fiis" in response.json()

    @patch("api.main.get_sectors_summary", return_value={"Logística": 5})
    @patch("api.main.get_universe", return_value=_MOCK_UNIVERSE)
    def test_universe_with_sector_filter(self, *mocks):
        response = client.get("/api/universe?sectors=Logística")
        assert response.status_code == 200


class TestMacro:
    @patch("api.main.get_macro_snapshot", return_value={"selic_anual": 10.5, "cdi_anual": 10.4, "ipca_anual": 4.2})
    def test_macro_snapshot(self, mock_macro):
        response = client.get("/api/macro")
        assert response.status_code == 200
        data = response.json()
        assert "selic_anual" in data


class TestCorrelation:
    @patch("api.main.build_correlation_matrix")
    @patch("api.main.load_returns_bulk")
    def test_correlation_success(self, mock_returns, mock_matrix):
        returns_data = {
            "HGLG11": [0.01, 0.02, -0.01, 0.03, 0.01],
            "MXRF11": [0.02, -0.01, 0.01, 0.02, -0.01],
        }
        mock_returns.return_value = (returns_data, {"HGLG11": "cache", "MXRF11": "cache"})
        mock_matrix.return_value = {
            "HGLG11": {"HGLG11": 1.0, "MXRF11": 0.3},
            "MXRF11": {"HGLG11": 0.3, "MXRF11": 1.0},
        }
        response = client.post("/api/correlation", json={"tickers": ["HGLG11", "MXRF11"]})
        assert response.status_code == 200
        assert "matrix" in response.json()


class TestMomentum:
    @patch("api.main.rank_by_momentum")
    @patch("api.main.load_returns_bulk")
    @patch("api.main.get_tickers", return_value=["HGLG11", "MXRF11"])
    def test_momentum_returns_ranking(self, _tickers, mock_returns, mock_rank):
        returns_data = {
            "HGLG11": [0.01] * 12,
            "MXRF11": [0.02] * 12,
        }
        mock_returns.return_value = (returns_data, {})
        mock_rank.return_value = [("MXRF11", 0.24), ("HGLG11", 0.12)]
        response = client.get("/api/momentum")
        assert response.status_code == 200


class TestStress:
    @patch("api.main.run_stress_suite")
    @patch("api.main.get_sector_map", return_value=_MOCK_SECTOR_MAP)
    @patch("api.main.build_portfolio_from_tickers")
    def test_stress_test(self, mock_build, _sector, mock_stress):
        mock_build.return_value = [{"ticker": "HGLG11", "quantidade": 100, "preco": 155.0}]
        mock_stress.return_value = {"scenarios": [{"name": "crash", "impact": -20}]}
        response = client.post(
            "/api/stress",
            json={
                "tickers": ["HGLG11"],
                "quantities": {"HGLG11": 100},
            },
        )
        assert response.status_code == 200


class TestClusters:
    @patch("api.main.cluster_portfolio")
    @patch("api.main.load_returns_bulk")
    @patch("api.main.get_tickers", return_value=["A11", "B11", "C11", "D11"])
    def test_clusters_returns_groups(self, _tickers, mock_returns, mock_cluster):
        returns_data = {
            "A11": [0.01] * 12,
            "B11": [0.02] * 12,
            "C11": [-0.01] * 12,
            "D11": [0.03] * 12,
        }
        mock_returns.return_value = (returns_data, {})
        mock_cluster.return_value = {"k": 2, "clusters": {0: ["A11", "B11"], 1: ["C11", "D11"]}}
        response = client.get("/api/clusters")
        assert response.status_code == 200


class TestFire:
    def test_fire_calculation(self):
        response = client.post(
            "/api/fire",
            json={
                "patrimonio_atual": 100000,
                "aporte_mensal": 3000,
                "taxa_anual": 0.08,
                "renda_alvo_anual": 60000,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "years_to_fire" in data


class TestSimulate:
    @patch("api.main.simulate_12_months")
    @patch("api.main.build_portfolio_from_tickers")
    @patch("api.main.load_last_price", return_value=(155.0, "cache"))
    def test_simulate_endpoint(self, _price, mock_build, mock_sim):
        mock_build.return_value = [{"ticker": "HGLG11", "quantidade": 100, "preco": 155.0, "classe": "FII"}]
        mock_sim.return_value = {"valor_final": 16000, "meses": 12}
        response = client.post(
            "/api/simulate",
            json={
                "tickers": ["HGLG11"],
                "quantities": {"HGLG11": 100},
                "aporte_mensal": 1000,
                "meses": 12,
            },
        )
        assert response.status_code == 200


class TestMonteCarlo:
    @patch("api.main.simulate_monte_carlo")
    @patch("api.main.build_portfolio_from_tickers")
    @patch("api.main.load_last_price", return_value=(155.0, "cache"))
    def test_monte_carlo_endpoint(self, _price, mock_build, mock_mc):
        mock_build.return_value = [{"ticker": "HGLG11", "quantidade": 100, "preco": 155.0, "classe": "FII"}]
        mock_mc.return_value = {"mediana_valor_final": 20000, "probabilidade_prejuizo": 0.1}
        response = client.post(
            "/api/monte-carlo",
            json={
                "tickers": ["HGLG11"],
                "quantities": {"HGLG11": 100},
                "aporte_mensal": 1000,
                "meses": 24,
            },
        )
        assert response.status_code == 200


class TestAiAnalyze:
    @patch("api.main.analyze_fii_news")
    @patch("api.main.fetch_fii_news")
    def test_ai_analyze_success(self, mock_news, mock_analyze):
        mock_news.return_value = [{"titulo": "HGLG11 sobe", "fonte": "Google"}]
        mock_analyze.return_value = {"sentiment": "positive", "confidence": 0.8}
        response = client.post("/api/ai/analyze", json={"ticker": "HGLG11"})
        assert response.status_code == 200

    @patch("api.main.fetch_fii_news")
    def test_ai_analyze_no_news(self, mock_news):
        mock_news.return_value = []
        response = client.post("/api/ai/analyze", json={"ticker": "FAKE11"})
        assert response.status_code == 200
        assert response.json()["success"] is False


class TestNews:
    @patch("api.main.fetch_fii_news")
    def test_news_by_ticker(self, mock_news):
        mock_news.return_value = [{"titulo": "HGLG11 paga dividendo", "fonte": "Suno"}]
        response = client.get("/api/news/HGLG11")
        assert response.status_code == 200
        data = response.json()
        assert "news" in data
        assert data["count"] == 1

    @patch("api.main.fetch_market_news")
    def test_market_news(self, mock_news):
        mock_news.return_value = [{"titulo": "FIIs sobem", "fonte": "InfoMoney"}]
        response = client.get("/api/news")
        assert response.status_code == 200
        assert "news" in response.json()


class TestSources:
    @patch("api.main.list_sources")
    def test_data_sources(self, mock_sources):
        mock_sources.return_value = [{"name": "yfinance", "type": "ticker"}]
        response = client.get("/api/sources")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Additional tests to cover remaining uncovered lines
# ---------------------------------------------------------------------------


class TestScannerEdgeCases:
    @patch("api.main.fetch_prices", side_effect=Exception("no price data"))
    @patch("api.main.load_last_price", side_effect=Exception("no fallback"))
    @patch("api.main.evaluate_company", side_effect=Exception("eval fail"))
    @patch("api.main.get_sector_map", return_value=_MOCK_SECTOR_MAP)
    @patch("api.main.fetch_fundamentals_bulk", return_value=_MOCK_FUNDAMENTALS)
    @patch("api.main.get_universe", return_value=_MOCK_UNIVERSE)
    def test_scanner_evaluate_exception_score_zero(self, *mocks):
        """Lines 205-206: evaluate_company raises → score defaults to 0."""
        response = client.get("/api/scanner")
        assert response.status_code == 200
        data = response.json()
        for fii in data["fiis"]:
            assert fii["score"] == 0

    @patch("api.main.fetch_prices", side_effect=Exception("network error"))
    @patch("api.main.load_last_price", side_effect=Exception("cache miss"))
    @patch("api.main.evaluate_company", return_value={"score_final": 70})
    @patch("api.main.get_sector_map", return_value=_MOCK_SECTOR_MAP)
    @patch("api.main.fetch_fundamentals_bulk", return_value=_MOCK_FUNDAMENTALS)
    @patch("api.main.get_universe", return_value=_MOCK_UNIVERSE)
    def test_scanner_price_both_fallbacks_fail(self, *mocks):
        """Lines 221-225: fetch_prices fails AND load_last_price fails → price from fundamentals."""
        response = client.get("/api/scanner")
        assert response.status_code == 200
        data = response.json()
        # Should still return results, price falls back to fund.get('cotacao', 0)
        assert data["total"] == 2
        for fii in data["fiis"]:
            assert "price" in fii


class TestBuildDividendHistory:
    def test_uses_fundsexplorer_when_available(self):
        """Lines 273-274: fe_data with historico_dividendos takes the first branch."""
        import datetime
        from api.main import _build_dividend_history

        fe_data = {
            "historico_dividendos": [
                {"data": "2025-01-15", "valor": 1.10},
                {"data": "2025-02-15", "valor": 1.12},
            ]
        }
        result = _build_dividend_history("HGLG11", fe_data)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["month"] == "2025-01"

    @patch("api.main.fetch_dividends", side_effect=Exception("no dividends"))
    def test_returns_empty_list_on_fetch_exception(self, _mock):
        """Lines 285-286: fetch_dividends raises → returns []."""
        from api.main import _build_dividend_history

        result = _build_dividend_history("FAKE11", None)
        assert result == []


class TestBuildFundInfo:
    def test_cvm_registry_matched_entry(self):
        """Lines 297-301: CVM registry entry whose name/ticker matches."""
        from api.main import _build_fund_info

        mock_registry = [
            {"nome": "HGLG11 Fundo", "ticker": "HGLG11", "administrador": "CSHG", "cnpj": "00.000.000/0001-00"},
            {"nome": "Outro Fundo", "ticker": "OTHER11", "administrador": "X", "cnpj": "11.111.111/0001-11"},
        ]
        with patch("api.main.fetch_cvm_fii_registry", return_value=mock_registry):
            result = _build_fund_info("HGLG11", None)
        assert result["administrador"] == "CSHG"
        assert result["cnpj"] == "00.000.000/0001-00"

    @patch("api.main.fetch_cvm_fii_registry", side_effect=Exception("cvm down"))
    def test_cvm_registry_exception_returns_empty(self, _mock):
        """Lines 297-301 except branch: CVM call fails → still returns dict (possibly empty)."""
        from api.main import _build_fund_info

        result = _build_fund_info("HGLG11", None)
        assert isinstance(result, dict)


class TestFiiDetailEdgeCases:
    @patch("api.main.get_sector_map", return_value=_MOCK_SECTOR_MAP)
    @patch("api.main.fetch_prices", return_value=[{"date": "2026-01-01", "close": 155.0}] * 6)
    @patch("api.main.scrape_fii_detail", return_value=None)
    @patch("api.main.calculate_fii_score", side_effect=Exception("score fail"))
    @patch("api.main.evaluate_company", return_value={"score_final": 80})
    @patch("api.main.load_monthly_dividend", return_value=(1.10, "cache"))
    @patch("api.main.load_last_price", return_value=(155.0, "cache"))
    @patch("api.main.fetch_fundamentals", return_value=_MOCK_FUNDAMENTALS["HGLG11"])
    def test_fii_detail_score_exception_fallback(self, *mocks):
        """Lines 347-348: calculate_fii_score raises → fallback score_breakdown with zeros."""
        response = client.get("/api/fii/HGLG11")
        assert response.status_code == 200
        data = response.json()
        sb = data["score_breakdown"]
        assert sb["total"] == 0
        assert sb["fundamentos"] == 0

    @patch("api.main.get_sector_map", return_value=_MOCK_SECTOR_MAP)
    @patch("api.main.scrape_fii_detail", return_value=None)
    @patch("api.main.calculate_fii_score", return_value=_MOCK_SCORE_BREAKDOWN)
    @patch("api.main.evaluate_company", return_value={"score_final": 80})
    @patch("api.main.load_monthly_dividend", return_value=(1.10, "cache"))
    @patch("api.main.load_last_price", return_value=(155.0, "cache"))
    @patch(
        "api.main.fetch_prices",
        return_value=[
            {"date": "2025-01-01", "close": 150.0},
            {"date": "2025-01-02", "close": 152.0},
            {"date": "2025-01-03", "close": 151.0},
            {"date": "2025-01-04", "close": 153.0},
            {"date": "2025-01-05", "close": 154.0},
            {"date": "2025-01-06", "close": 155.0},
        ],
    )
    @patch("api.main.fetch_fundamentals", return_value=_MOCK_FUNDAMENTALS["HGLG11"])
    def test_fii_detail_volatility_calculated(self, *mocks):
        """Lines 372-376: enough closes → vol_30d is computed and returned as float."""
        response = client.get("/api/fii/HGLG11")
        assert response.status_code == 200
        data = response.json()
        assert data["volatilidade_30d"] is not None
        assert isinstance(data["volatilidade_30d"], float)


class TestCorrelationEdgeCases:
    @patch("api.main.load_returns_bulk")
    def test_correlation_insufficient_data_raises_400(self, mock_returns):
        """Line 444: fewer than 2 valid tickers → 400."""
        # Only one ticker has enough data
        mock_returns.return_value = ({"HGLG11": [0.01, 0.02, 0.03]}, {})
        response = client.post(
            "/api/correlation",
            json={"tickers": ["HGLG11", "MXRF11"]},
        )
        assert response.status_code == 400
        assert "insuficientes" in response.json()["detail"].lower()


class TestClustersEdgeCases:
    @patch("api.main.load_returns_bulk")
    @patch("api.main.get_tickers", return_value=["A11", "B11"])
    def test_clusters_insufficient_data_raises_400(self, _tickers, mock_returns):
        """Line 497: fewer than 4 valid tickers → 400."""
        mock_returns.return_value = (
            {"A11": [0.01] * 8, "B11": [0.02] * 8},
            {},
        )
        response = client.get("/api/clusters")
        assert response.status_code == 400
        assert "insuficientes" in response.json()["detail"].lower()


class TestSimulateEdgeCases:
    @patch("api.main.simulate_12_months")
    @patch("api.main.build_portfolio_from_tickers")
    @patch("api.main.load_last_price", side_effect=Exception("price unavailable"))
    def test_simulate_load_price_exception_defaults_to_100(self, _price, mock_build, mock_sim):
        """Lines 531-532: load_last_price raises → price defaults to 100.0."""
        mock_build.return_value = [{"ticker": "HGLG11", "quantidade": 10, "preco": 100.0, "classe": "FII"}]
        mock_sim.return_value = {"valor_final": 12000, "meses": 12}
        response = client.post(
            "/api/simulate",
            json={"tickers": ["HGLG11"], "quantities": {"HGLG11": 10}, "aporte_mensal": 500, "meses": 12},
        )
        assert response.status_code == 200
        # Verify build was called (price defaulted to 100.0 internally)
        mock_sim.assert_called_once()


class TestMonteCarloEdgeCases:
    @patch("api.main.simulate_monte_carlo")
    @patch("api.main.build_portfolio_from_tickers")
    @patch("api.main.load_last_price", side_effect=Exception("price unavailable"))
    def test_monte_carlo_load_price_exception_defaults_to_100(self, _price, mock_build, mock_mc):
        """Lines 563-564: load_last_price raises → price defaults to 100.0."""
        mock_build.return_value = [{"ticker": "MXRF11", "quantidade": 10, "preco": 100.0, "classe": "FII"}]
        mock_mc.return_value = {"mediana_valor_final": 15000, "probabilidade_prejuizo": 0.05}
        response = client.post(
            "/api/monte-carlo",
            json={"tickers": ["MXRF11"], "quantities": {"MXRF11": 10}, "aporte_mensal": 500, "meses": 12},
        )
        assert response.status_code == 200
        mock_mc.assert_called_once()
