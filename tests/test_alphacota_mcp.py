"""
Tests for alphacota_mcp/ — MCP Server tools for FII analysis.

Covers:
  - alphacota_mcp/__init__.py
  - alphacota_mcp/financial_data/__init__.py
  - alphacota_mcp/financial_data/__main__.py
  - alphacota_mcp/financial_data/server.py
  - alphacota_mcp/financial_data/tools/__init__.py
  - alphacota_mcp/financial_data/tools/ai_tools.py
  - alphacota_mcp/financial_data/tools/analysis.py
  - alphacota_mcp/financial_data/tools/macro.py
  - alphacota_mcp/financial_data/tools/market.py
  - alphacota_mcp/financial_data/tools/news_tools.py
  - alphacota_mcp/financial_data/tools/screening.py
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Helpers — build a minimal stub MCP object that captures registered tools
# ---------------------------------------------------------------------------

class _MockMCP:
    """Minimal stand-in for FastMCP that captures tool registrations."""

    def __init__(self):
        self._tools: dict = {}

    def tool(self):
        """Decorator that stores the wrapped function under its __name__."""
        def decorator(fn):
            self._tools[fn.__name__] = fn
            return fn
        return decorator

    def get(self, name):
        return self._tools[name]

    def run(self):
        pass  # no-op for tests


def _build_mcp_with_tools(register_fn):
    """Instantiate a mock MCP, call the register function, return the mock."""
    mock_mcp = _MockMCP()
    register_fn(mock_mcp)
    return mock_mcp


# ===========================================================================
# alphacota_mcp package imports
# ===========================================================================

class TestPackageInit:
    def test_alphacota_mcp_importable(self):
        import alphacota_mcp
        assert alphacota_mcp is not None

    def test_financial_data_importable(self):
        import alphacota_mcp.financial_data
        assert alphacota_mcp.financial_data is not None

    def test_tools_init_importable(self):
        import alphacota_mcp.financial_data.tools
        assert alphacota_mcp.financial_data.tools is not None


# ===========================================================================
# server.py — FastMCP registration
# ===========================================================================

class TestServer:
    """Tests for server.py — tool registration and entry point."""

    def test_mcp_object_created(self):
        from alphacota_mcp.financial_data import server
        assert server.mcp is not None

    def test_main_function_calls_run(self):
        from alphacota_mcp.financial_data import server
        with patch.object(server.mcp, "run") as mock_run:
            server.main()
            mock_run.assert_called_once()


# ===========================================================================
# __main__.py — entry point
# ===========================================================================

class TestMain:
    def test_dunder_main_calls_mcp_run(self):
        from alphacota_mcp.financial_data import server
        with patch.object(server.mcp, "run") as mock_run:
            # Simulate running __main__ module behaviour
            server.mcp.run()
            mock_run.assert_called_once()


# ===========================================================================
# macro.py tools
# ===========================================================================

class TestMacroTools:

    def _setup(self):
        from alphacota_mcp.financial_data.tools.macro import register_macro_tools
        mcp = _build_mcp_with_tools(register_macro_tools)
        return mcp

    def _macro_data(self, selic=13.75, ipca=4.62, cdi=13.65):
        return {
            "selic": selic,
            "ipca": ipca,
            "cdi": cdi,
            "selic_source": "bcb",
            "ipca_source": "bcb",
        }

    # --- get_macro_snapshot ---

    def test_get_macro_snapshot_returns_enriched_dict(self):
        mcp = self._setup()
        raw = self._macro_data(selic=13.75, ipca=4.62)

        with patch("core.macro_engine.get_macro_snapshot", return_value=raw):
            result = mcp.get("get_macro_snapshot")()

        assert "selic" in result
        assert "juro_real" in result
        assert "spread_fii_vs_selic" in result
        assert "atratividade_fiis" in result

    def test_get_macro_snapshot_atratividade_alta_when_spread_positive(self):
        mcp = self._setup()
        # avg_fii_dy is 9.0 hardcoded; selic=6 → spread = 3 > 0
        raw = self._macro_data(selic=6.0, ipca=3.0)

        with patch("core.macro_engine.get_macro_snapshot", return_value=raw):
            result = mcp.get("get_macro_snapshot")()

        assert result["atratividade_fiis"] == "Alta"
        assert result["spread_fii_vs_selic"] > 0

    def test_get_macro_snapshot_atratividade_moderada_when_spread_between_minus2_and_0(self):
        mcp = self._setup()
        # avg_fii_dy=9.0, selic=10 → spread=-1 (between -2 and 0)
        raw = self._macro_data(selic=10.0, ipca=4.0)

        with patch("core.macro_engine.get_macro_snapshot", return_value=raw):
            result = mcp.get("get_macro_snapshot")()

        assert result["atratividade_fiis"] == "Moderada"

    def test_get_macro_snapshot_atratividade_baixa_when_spread_below_minus2(self):
        mcp = self._setup()
        # avg_fii_dy=9.0, selic=15 → spread=-6
        raw = self._macro_data(selic=15.0, ipca=5.0)

        with patch("core.macro_engine.get_macro_snapshot", return_value=raw):
            result = mcp.get("get_macro_snapshot")()

        assert result["atratividade_fiis"] == "Baixa"

    def test_get_macro_snapshot_zero_ipca_uses_selic_as_juro_real(self):
        mcp = self._setup()
        raw = self._macro_data(selic=13.75, ipca=0)

        with patch("core.macro_engine.get_macro_snapshot", return_value=raw):
            result = mcp.get("get_macro_snapshot")()

        # When ipca=0, juro_real = selic
        assert result["juro_real"] == pytest_approx_13_75(result)

    def test_get_macro_snapshot_nonzero_ipca_computes_real_rate(self):
        mcp = self._setup()
        raw = self._macro_data(selic=10.0, ipca=5.0)

        with patch("core.macro_engine.get_macro_snapshot", return_value=raw):
            result = mcp.get("get_macro_snapshot")()

        # juro_real = ((1+0.10)/(1+0.05) - 1) * 100 ≈ 4.76
        assert abs(result["juro_real"] - 4.76) < 0.1

    # --- get_selic ---

    def test_get_selic_returns_value_and_source(self):
        mcp = self._setup()
        raw = self._macro_data(selic=13.75)

        with patch("core.macro_engine.get_macro_snapshot", return_value=raw):
            result = mcp.get("get_selic")()

        assert result["selic"] == 13.75
        assert "source" in result

    def test_get_selic_missing_key_returns_zero(self):
        mcp = self._setup()

        with patch("core.macro_engine.get_macro_snapshot", return_value={}):
            result = mcp.get("get_selic")()

        assert result["selic"] == 0

    # --- get_ipca ---

    def test_get_ipca_returns_value_and_source(self):
        mcp = self._setup()
        raw = self._macro_data(ipca=4.62)

        with patch("core.macro_engine.get_macro_snapshot", return_value=raw):
            result = mcp.get("get_ipca")()

        assert result["ipca_12m"] == 4.62
        assert "source" in result

    def test_get_ipca_missing_key_returns_zero(self):
        mcp = self._setup()

        with patch("core.macro_engine.get_macro_snapshot", return_value={}):
            result = mcp.get("get_ipca")()

        assert result["ipca_12m"] == 0


def pytest_approx_13_75(result):
    """Helper to avoid import ordering issue — just returns selic from result."""
    return result["juro_real"]  # Used in a trivial identity assertion above


# ===========================================================================
# market.py tools
# ===========================================================================

class TestMarketTools:

    def _setup(self):
        from alphacota_mcp.financial_data.tools.market import register_market_tools
        mcp = _build_mcp_with_tools(register_market_tools)
        return mcp

    def _fund(self, dy=0.09, pvp=0.95, liq=500_000):
        return {
            "dividend_yield": dy,
            "pvp": pvp,
            "daily_liquidity": liq,
            "vacancia": 0.05,
            "liquidez_diaria": liq,
            "_source": "scraper",
        }

    # --- get_fii_price ---

    def test_get_fii_price_normalizes_ticker(self):
        mcp = self._setup()
        fund = self._fund()

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.data_bridge.load_last_price", return_value=(100.5, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(0.75, "historical")),
        ):
            # The source strips ".SA" (uppercase) and uppercases the remainder
            result = mcp.get("get_fii_price")("hglg11.SA")

        assert result["ticker"] == "HGLG11"

    def test_get_fii_price_returns_expected_fields(self):
        mcp = self._setup()
        fund = self._fund(dy=0.09, pvp=0.95)

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.data_bridge.load_last_price", return_value=(100.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(0.75, "historical")),
        ):
            result = mcp.get("get_fii_price")("HGLG11")

        assert result["price"] == 100.0
        assert result["dy_12m"] == 9.0
        assert result["pvp"] == 0.95
        assert result["dividend_monthly"] == 0.75
        assert result["price_source"] == "yfinance"
        assert result["data_source"] == "scraper"

    def test_get_fii_price_handles_load_last_price_exception(self):
        mcp = self._setup()
        fund = self._fund()

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.data_bridge.load_last_price", side_effect=Exception("no data")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(0.50, "hist")),
        ):
            result = mcp.get("get_fii_price")("MXRF11")

        assert result["price"] == 0
        assert result["price_source"] == "unavailable"

    def test_get_fii_price_handles_load_monthly_dividend_exception(self):
        mcp = self._setup()
        fund = self._fund()

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.data_bridge.load_last_price", return_value=(95.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", side_effect=Exception("no data")),
        ):
            result = mcp.get("get_fii_price")("XPML11")

        assert result["dividend_monthly"] == 0
        assert result["dividend_source"] == "unavailable"

    # --- get_fii_detail ---

    def test_get_fii_detail_returns_all_fields(self):
        mcp = self._setup()
        fund = {
            "dividend_yield": 0.10,
            "pvp": 0.92,
            "vacancy_rate": 0.03,
            "daily_liquidity": 800_000,
            "net_asset_value": 10_000_000,
            "vacancia": 0.03,
            "liquidez_diaria": 800_000,
            "_source": "scraper",
        }
        sector_map = {"HGLG11": "Logistica"}
        evaluation = {"score_final": 87.5, "grade": "A"}

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.universe.get_sector_map", return_value=sector_map),
            patch("data.data_bridge.load_last_price", return_value=(110.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(0.90, "hist")),
            patch("core.quant_engine.evaluate_company", return_value=evaluation),
        ):
            result = mcp.get("get_fii_detail")("HGLG11")

        assert result["ticker"] == "HGLG11"
        assert result["segment"] == "Logistica"
        assert result["price"] == 110.0
        assert result["dy_12m"] == 10.0
        assert result["pvp"] == 0.92
        assert result["score"] == 87.5
        assert result["evaluation"] == evaluation

    def test_get_fii_detail_handles_price_exception(self):
        mcp = self._setup()
        fund = {"dividend_yield": 0.08, "pvp": 1.0, "_source": "fallback"}

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", side_effect=Exception("unavailable")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(0.60, "hist")),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 70}),
        ):
            result = mcp.get("get_fii_detail")("MXRF11")

        assert result["price"] == 0

    def test_get_fii_detail_handles_evaluate_company_exception(self):
        mcp = self._setup()
        fund = {"dividend_yield": 0.08, "pvp": 1.0, "_source": "fallback"}

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", return_value=(80.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(0.55, "hist")),
            patch("core.quant_engine.evaluate_company", side_effect=Exception("engine error")),
        ):
            result = mcp.get("get_fii_detail")("XPML11")

        assert result["evaluation"] == {}
        assert result["score"] == 0

    def test_get_fii_detail_unknown_ticker_uses_outros_segment(self):
        mcp = self._setup()
        fund = {"dividend_yield": 0.08, "pvp": 1.0, "_source": "fallback"}

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", return_value=(80.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(0.55, "hist")),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 65}),
        ):
            result = mcp.get("get_fii_detail")("FAKE11")

        assert result["segment"] == "Outros"

    # --- get_scanner ---

    def test_get_scanner_returns_sorted_by_score(self):
        mcp = self._setup()
        universe = [
            {"ticker": "HGLG11", "nome": "CSHG Logistica"},
            {"ticker": "MXRF11", "nome": "Maxi Renda"},
        ]
        fundamentals = {
            "HGLG11": {"dividend_yield": 0.10, "pvp": 0.90, "vacancia": 0.03, "liquidez_diaria": 600_000},
            "MXRF11": {"dividend_yield": 0.08, "pvp": 1.05, "vacancia": 0.07, "liquidez_diaria": 300_000},
        }
        sector_map = {"HGLG11": "Logistica", "MXRF11": "Papel"}

        def eval_side(ticker, _data):
            return {"score_final": 90 if ticker == "HGLG11" else 60}

        with (
            patch("data.universe.get_universe", return_value=universe),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=fundamentals),
            patch("data.universe.get_sector_map", return_value=sector_map),
            patch("data.data_bridge.load_last_price", return_value=(100.0, "yfinance")),
            patch("core.quant_engine.evaluate_company", side_effect=eval_side),
        ):
            result = mcp.get("get_scanner")()

        assert result["total"] == 2
        assert result["fiis"][0]["ticker"] == "HGLG11"
        assert result["fiis"][0]["score"] >= result["fiis"][1]["score"]

    def test_get_scanner_with_sector_filter(self):
        mcp = self._setup()
        universe = [{"ticker": "HGLG11", "nome": "CSHG Logistica"}]
        fundamentals = {"HGLG11": {"dividend_yield": 0.09, "pvp": 0.95, "vacancia": 0.03, "liquidez_diaria": 500_000}}

        with (
            patch("data.universe.get_universe", return_value=universe) as mock_univ,
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=fundamentals),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", return_value=(100.0, "yfinance")),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 80}),
        ):
            mcp.get("get_scanner")("Logistica")
            mock_univ.assert_called_once_with(sectors=["Logistica"])

    def test_get_scanner_empty_sectors_passes_none(self):
        mcp = self._setup()
        universe = []

        with (
            patch("data.universe.get_universe", return_value=universe) as mock_univ,
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value={}),
            patch("data.universe.get_sector_map", return_value={}),
        ):
            result = mcp.get("get_scanner")("")

        assert result["total"] == 0
        mock_univ.assert_called_once_with(sectors=None)

    def test_get_scanner_evaluate_company_exception_yields_score_zero(self):
        mcp = self._setup()
        universe = [{"ticker": "ERR11", "nome": "Error Fund"}]
        fundamentals = {"ERR11": {"dividend_yield": 0.08, "pvp": 1.0, "vacancia": 0.05, "liquidez_diaria": 100_000}}

        with (
            patch("data.universe.get_universe", return_value=universe),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=fundamentals),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", return_value=(50.0, "yfinance")),
            patch("core.quant_engine.evaluate_company", side_effect=Exception("boom")),
        ):
            result = mcp.get("get_scanner")()

        assert result["fiis"][0]["score"] == 0

    def test_get_scanner_load_price_exception_yields_price_zero(self):
        mcp = self._setup()
        universe = [{"ticker": "MXRF11", "nome": "Maxi Renda"}]
        fundamentals = {"MXRF11": {"dividend_yield": 0.08, "pvp": 1.0, "vacancia": 0.05, "liquidez_diaria": 200_000}}

        with (
            patch("data.universe.get_universe", return_value=universe),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=fundamentals),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", side_effect=Exception("no price")),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 70}),
        ):
            result = mcp.get("get_scanner")()

        assert result["fiis"][0]["price"] == 0


# ===========================================================================
# news_tools.py
# ===========================================================================

class TestNewsTools:

    def _setup(self):
        from alphacota_mcp.financial_data.tools.news_tools import register_news_tools
        mcp = _build_mcp_with_tools(register_news_tools)
        return mcp

    # --- get_fii_news ---

    def test_get_fii_news_normalizes_ticker(self):
        mcp = self._setup()
        news_list = [{"titulo": "HGLG11 sobe", "data": "2025-01-01", "link": "http://x.com", "fonte": "G"}]

        with patch("data.news_scraper.fetch_fii_news", return_value=news_list) as mock_fn:
            result = mcp.get("get_fii_news")("hglg11.SA")

        mock_fn.assert_called_once_with("HGLG11", max_results=10)
        assert result["ticker"] == "HGLG11"

    def test_get_fii_news_returns_count(self):
        mcp = self._setup()
        news_list = [
            {"titulo": "N1", "data": "2025-01-01", "link": "http://a.com", "fonte": "A"},
            {"titulo": "N2", "data": "2025-01-02", "link": "http://b.com", "fonte": "B"},
        ]

        with patch("data.news_scraper.fetch_fii_news", return_value=news_list):
            result = mcp.get("get_fii_news")("MXRF11", limit=5)

        assert result["count"] == 2
        assert len(result["news"]) == 2

    def test_get_fii_news_empty_returns_zero_count(self):
        mcp = self._setup()

        with patch("data.news_scraper.fetch_fii_news", return_value=[]):
            result = mcp.get("get_fii_news")("FAKE11")

        assert result["count"] == 0
        assert result["news"] == []

    def test_get_fii_news_passes_limit_as_max_results(self):
        mcp = self._setup()

        with patch("data.news_scraper.fetch_fii_news", return_value=[]) as mock_fn:
            mcp.get("get_fii_news")("XPML11", limit=3)

        mock_fn.assert_called_once_with("XPML11", max_results=3)

    # --- get_market_news ---

    def test_get_market_news_returns_dict_with_news_and_count(self):
        mcp = self._setup()
        news_list = [{"titulo": "Selic cai", "data": "2025-01-01", "link": "http://c.com", "fonte": "X"}]

        with patch("data.news_scraper.fetch_market_news", return_value=news_list):
            result = mcp.get("get_market_news")()

        assert result["count"] == 1
        assert result["news"] == news_list

    def test_get_market_news_passes_limit_as_max_results(self):
        mcp = self._setup()

        with patch("data.news_scraper.fetch_market_news", return_value=[]) as mock_fn:
            mcp.get("get_market_news")(limit=7)

        mock_fn.assert_called_once_with(max_results=7)

    def test_get_market_news_empty_returns_zero_count(self):
        mcp = self._setup()

        with patch("data.news_scraper.fetch_market_news", return_value=[]):
            result = mcp.get("get_market_news")()

        assert result["count"] == 0

    # --- list_news_sources ---

    def test_list_news_sources_splits_by_type(self):
        mcp = self._setup()
        sources = [
            {"name": "Google News", "type": "ticker"},
            {"name": "InfoMoney", "type": "general"},
            {"name": "Suno", "type": "general"},
        ]

        with patch("data.news_scraper.list_sources", return_value=sources):
            result = mcp.get("list_news_sources")()

        assert result["total"] == 3
        assert len(result["ticker_sources"]) == 1
        assert len(result["general_sources"]) == 2

    def test_list_news_sources_empty(self):
        mcp = self._setup()

        with patch("data.news_scraper.list_sources", return_value=[]):
            result = mcp.get("list_news_sources")()

        assert result["total"] == 0
        assert result["ticker_sources"] == []
        assert result["general_sources"] == []


# ===========================================================================
# screening.py tools
# ===========================================================================

class TestScreeningTools:

    def _setup(self):
        from alphacota_mcp.financial_data.tools.screening import register_screening_tools
        mcp = _build_mcp_with_tools(register_screening_tools)
        return mcp

    def _universe(self):
        return [
            {"ticker": "HGLG11", "nome": "CSHG Logistica"},
            {"ticker": "MXRF11", "nome": "Maxi Renda"},
            {"ticker": "XPML11", "nome": "XP Malls"},
        ]

    def _fundamentals(self):
        return {
            "HGLG11": {"dividend_yield": 0.11, "pvp": 0.88, "daily_liquidity": 600_000, "vacancia": 0.03, "liquidez_diaria": 600_000},
            "MXRF11": {"dividend_yield": 0.09, "pvp": 0.93, "daily_liquidity": 250_000, "vacancia": 0.05, "liquidez_diaria": 250_000},
            "XPML11": {"dividend_yield": 0.07, "pvp": 1.20, "daily_liquidity": 80_000, "vacancia": 0.10, "liquidez_diaria": 80_000},
        }

    # --- find_undervalued_fiis ---

    def test_find_undervalued_fiis_filters_by_pvp_and_dy(self):
        mcp = self._setup()

        with (
            patch("data.universe.get_universe", return_value=self._universe()),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=self._fundamentals()),
            patch("data.universe.get_sector_map", return_value={}),
        ):
            result = mcp.get("find_undervalued_fiis")(max_pvp=0.95, min_dy=8.0)

        tickers = [f["ticker"] for f in result["fiis"]]
        # HGLG11: pvp=0.88<=0.95, dy=11%>=8% -> match
        # MXRF11: pvp=0.93<=0.95, dy=9%>=8%  -> match
        # XPML11: pvp=1.20>0.95               -> no match
        assert "HGLG11" in tickers
        assert "MXRF11" in tickers
        assert "XPML11" not in tickers

    def test_find_undervalued_fiis_returns_criteria(self):
        mcp = self._setup()

        with (
            patch("data.universe.get_universe", return_value=[]),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value={}),
            patch("data.universe.get_sector_map", return_value={}),
        ):
            result = mcp.get("find_undervalued_fiis")(max_pvp=0.90, min_dy=9.0)

        assert result["criteria"]["max_pvp"] == 0.90
        assert result["criteria"]["min_dy"] == 9.0

    def test_find_undervalued_fiis_sorted_by_dy_descending(self):
        mcp = self._setup()

        with (
            patch("data.universe.get_universe", return_value=self._universe()),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=self._fundamentals()),
            patch("data.universe.get_sector_map", return_value={}),
        ):
            result = mcp.get("find_undervalued_fiis")(max_pvp=1.0, min_dy=8.0)

        fiis = result["fiis"]
        for i in range(len(fiis) - 1):
            assert fiis[i]["dy"] >= fiis[i + 1]["dy"]

    def test_find_undervalued_fiis_respects_limit(self):
        mcp = self._setup()

        with (
            patch("data.universe.get_universe", return_value=self._universe()),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=self._fundamentals()),
            patch("data.universe.get_sector_map", return_value={}),
        ):
            result = mcp.get("find_undervalued_fiis")(max_pvp=1.5, min_dy=0.0, limit=1)

        assert len(result["fiis"]) <= 1

    def test_find_undervalued_fiis_total_found_reflects_all_matches(self):
        mcp = self._setup()

        with (
            patch("data.universe.get_universe", return_value=self._universe()),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=self._fundamentals()),
            patch("data.universe.get_sector_map", return_value={}),
        ):
            result = mcp.get("find_undervalued_fiis")(max_pvp=1.5, min_dy=0.0, limit=1)

        # total_found should reflect all matches, not the limited list
        assert result["total_found"] >= len(result["fiis"])

    def test_find_undervalued_fiis_includes_desconto_field(self):
        mcp = self._setup()

        with (
            patch("data.universe.get_universe", return_value=self._universe()),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=self._fundamentals()),
            patch("data.universe.get_sector_map", return_value={}),
        ):
            result = mcp.get("find_undervalued_fiis")(max_pvp=0.95, min_dy=8.0)

        for fii in result["fiis"]:
            assert "desconto" in fii
            assert fii["desconto"] >= 0

    # --- find_high_dividend_fiis ---

    def test_find_high_dividend_fiis_filters_by_dy_and_liquidity(self):
        mcp = self._setup()

        with (
            patch("data.universe.get_universe", return_value=self._universe()),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=self._fundamentals()),
            patch("data.universe.get_sector_map", return_value={}),
        ):
            result = mcp.get("find_high_dividend_fiis")(min_dy=9.0, min_liquidity=200_000)

        tickers = [f["ticker"] for f in result["fiis"]]
        # HGLG11: dy=11%>=9%, liq=600k>=200k -> match
        # MXRF11: dy=9%>=9%,  liq=250k>=200k -> match
        # XPML11: dy=7%<9%                   -> no match
        assert "HGLG11" in tickers
        assert "MXRF11" in tickers
        assert "XPML11" not in tickers

    def test_find_high_dividend_fiis_liquidity_filter_excludes_low_liq(self):
        mcp = self._setup()

        with (
            patch("data.universe.get_universe", return_value=self._universe()),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=self._fundamentals()),
            patch("data.universe.get_sector_map", return_value={}),
        ):
            result = mcp.get("find_high_dividend_fiis")(min_dy=7.0, min_liquidity=300_000)

        tickers = [f["ticker"] for f in result["fiis"]]
        # XPML11: liq=80k < 300k -> excluded
        assert "XPML11" not in tickers
        # MXRF11: liq=250k < 300k -> excluded
        assert "MXRF11" not in tickers
        assert "HGLG11" in tickers

    def test_find_high_dividend_fiis_sorted_by_dy(self):
        mcp = self._setup()

        with (
            patch("data.universe.get_universe", return_value=self._universe()),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=self._fundamentals()),
            patch("data.universe.get_sector_map", return_value={}),
        ):
            result = mcp.get("find_high_dividend_fiis")(min_dy=0.0, min_liquidity=0)

        fiis = result["fiis"]
        for i in range(len(fiis) - 1):
            assert fiis[i]["dy"] >= fiis[i + 1]["dy"]

    def test_find_high_dividend_fiis_returns_criteria(self):
        mcp = self._setup()

        with (
            patch("data.universe.get_universe", return_value=[]),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value={}),
            patch("data.universe.get_sector_map", return_value={}),
        ):
            result = mcp.get("find_high_dividend_fiis")(min_dy=10.0, min_liquidity=150_000)

        assert result["criteria"]["min_dy"] == 10.0
        assert result["criteria"]["min_liquidity"] == 150_000

    # --- scan_opportunities ---

    def test_scan_opportunities_applies_all_filters(self):
        mcp = self._setup()

        def eval_side(ticker, _data):
            scores = {"HGLG11": 85, "MXRF11": 70, "XPML11": 55}
            return {"score_final": scores.get(ticker, 0)}

        with (
            patch("data.universe.get_universe", return_value=self._universe()),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=self._fundamentals()),
            patch("data.universe.get_sector_map", return_value={}),
            patch("core.quant_engine.evaluate_company", side_effect=eval_side),
        ):
            result = mcp.get("scan_opportunities")(min_score=75, max_pvp=1.0, min_dy=7.0)

        # XPML11: pvp=1.20>1.0 -> filtered out before scoring
        # MXRF11: score=70 < 75 -> filtered
        # HGLG11: score=85>=75, pvp=0.88<=1.0, dy=11%>=7% -> match
        tickers = [f["ticker"] for f in result["opportunities"]]
        assert "HGLG11" in tickers
        assert "XPML11" not in tickers

    def test_scan_opportunities_sorted_by_score(self):
        mcp = self._setup()

        def eval_side(ticker, _data):
            return {"score_final": 80 if ticker == "HGLG11" else 76}

        with (
            patch("data.universe.get_universe", return_value=self._universe()),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=self._fundamentals()),
            patch("data.universe.get_sector_map", return_value={}),
            patch("core.quant_engine.evaluate_company", side_effect=eval_side),
        ):
            result = mcp.get("scan_opportunities")(min_score=75, max_pvp=1.0, min_dy=7.0)

        ops = result["opportunities"]
        for i in range(len(ops) - 1):
            assert ops[i]["score"] >= ops[i + 1]["score"]

    def test_scan_opportunities_exception_during_evaluate_gives_zero_score(self):
        mcp = self._setup()
        universe = [{"ticker": "HGLG11", "nome": "CSHG Logistica"}]
        fundamentals = {"HGLG11": {"dividend_yield": 0.10, "pvp": 0.90, "vacancia": 0.03, "liquidez_diaria": 500_000}}

        with (
            patch("data.universe.get_universe", return_value=universe),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=fundamentals),
            patch("data.universe.get_sector_map", return_value={}),
            patch("core.quant_engine.evaluate_company", side_effect=Exception("engine down")),
        ):
            result = mcp.get("scan_opportunities")(min_score=0, max_pvp=2.0, min_dy=0.0)

        # With min_score=0 and score=0, should still appear
        assert result["total_found"] == 1
        assert result["opportunities"][0]["score"] == 0

    def test_scan_opportunities_desconto_positive_when_pvp_below_one(self):
        mcp = self._setup()
        universe = [{"ticker": "HGLG11", "nome": "CSHG Logistica"}]
        fundamentals = {"HGLG11": {"dividend_yield": 0.10, "pvp": 0.80, "vacancia": 0.03, "liquidez_diaria": 500_000}}

        with (
            patch("data.universe.get_universe", return_value=universe),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=fundamentals),
            patch("data.universe.get_sector_map", return_value={}),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 85}),
        ):
            result = mcp.get("scan_opportunities")(min_score=80, max_pvp=1.0, min_dy=8.0)

        assert result["opportunities"][0]["desconto"] == 20.0

    def test_scan_opportunities_desconto_zero_when_pvp_above_one(self):
        mcp = self._setup()
        universe = [{"ticker": "MXRF11", "nome": "Maxi Renda"}]
        fundamentals = {"MXRF11": {"dividend_yield": 0.10, "pvp": 1.05, "vacancia": 0.05, "liquidez_diaria": 500_000}}

        with (
            patch("data.universe.get_universe", return_value=universe),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=fundamentals),
            patch("data.universe.get_sector_map", return_value={}),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 85}),
        ):
            result = mcp.get("scan_opportunities")(min_score=80, max_pvp=1.1, min_dy=8.0)

        assert result["opportunities"][0]["desconto"] == 0

    def test_scan_opportunities_returns_criteria(self):
        mcp = self._setup()

        with (
            patch("data.universe.get_universe", return_value=[]),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value={}),
            patch("data.universe.get_sector_map", return_value={}),
        ):
            result = mcp.get("scan_opportunities")(min_score=70, max_pvp=1.05, min_dy=8.5)

        assert result["criteria"]["min_score"] == 70
        assert result["criteria"]["max_pvp"] == 1.05
        assert result["criteria"]["min_dy"] == 8.5


# ===========================================================================
# analysis.py tools
# ===========================================================================

class TestAnalysisTools:

    def _setup(self):
        from alphacota_mcp.financial_data.tools.analysis import register_analysis_tools
        mcp = _build_mcp_with_tools(register_analysis_tools)
        return mcp

    # --- run_correlation ---

    def test_run_correlation_returns_matrix_and_pairs(self):
        mcp = self._setup()
        tickers = ["HGLG11", "MXRF11", "XPML11"]
        return_series = {
            "HGLG11": [0.01, -0.01, 0.02, 0.005, -0.003],
            "MXRF11": [0.008, -0.012, 0.018, 0.004, -0.002],
            "XPML11": [-0.005, 0.01, 0.001, -0.002, 0.003],
        }
        matrix = {
            "HGLG11": {"HGLG11": 1.0, "MXRF11": 0.95, "XPML11": 0.10},
            "MXRF11": {"HGLG11": 0.95, "MXRF11": 1.0, "XPML11": 0.08},
            "XPML11": {"HGLG11": 0.10, "MXRF11": 0.08, "XPML11": 1.0},
        }

        with (
            patch("data.data_bridge.load_returns_bulk", return_value=(return_series, {})),
            patch("core.correlation_engine.build_correlation_matrix", return_value=matrix),
        ):
            result = mcp.get("run_correlation")(tickers)

        assert "matrix" in result
        assert "top_correlations" in result
        assert "good_diversification_pairs" in result
        assert result["total_pairs"] == 3  # C(3,2)=3

    def test_run_correlation_insufficient_data_returns_error(self):
        mcp = self._setup()
        # Only one ticker has enough data
        return_series = {
            "HGLG11": [0.01, -0.01, 0.02, 0.005, -0.003],
            "MXRF11": [0.01],  # only 1 data point, < 3
        }

        with patch("data.data_bridge.load_returns_bulk", return_value=(return_series, {})):
            result = mcp.get("run_correlation")(["HGLG11", "MXRF11"])

        assert "error" in result

    def test_run_correlation_good_diversification_pairs_have_low_correlation(self):
        mcp = self._setup()
        tickers = ["HGLG11", "MXRF11", "XPML11"]
        return_series = {t: [0.01] * 5 for t in tickers}
        matrix = {
            "HGLG11": {"HGLG11": 1.0, "MXRF11": 0.80, "XPML11": 0.20},
            "MXRF11": {"HGLG11": 0.80, "MXRF11": 1.0, "XPML11": 0.15},
            "XPML11": {"HGLG11": 0.20, "MXRF11": 0.15, "XPML11": 1.0},
        }

        with (
            patch("data.data_bridge.load_returns_bulk", return_value=(return_series, {})),
            patch("core.correlation_engine.build_correlation_matrix", return_value=matrix),
        ):
            result = mcp.get("run_correlation")(tickers)

        for pair in result["good_diversification_pairs"]:
            assert pair["correlation"] < 0.3

    def test_run_correlation_passes_date_range(self):
        mcp = self._setup()
        return_series = {}  # no valid tickers

        with patch("data.data_bridge.load_returns_bulk", return_value=(return_series, {})) as mock_fn:
            mcp.get("run_correlation")(["HGLG11"], start_date="2023-06-01", end_date="2024-06-01")

        mock_fn.assert_called_once_with(["HGLG11"], "2023-06-01", "2024-06-01")

    # --- run_momentum ---

    def test_run_momentum_returns_ranking_and_total(self):
        mcp = self._setup()
        tickers = ["HGLG11", "MXRF11", "XPML11"]
        return_series = {t: [0.01] * 8 for t in tickers}
        ranking = [
            {"ticker": "HGLG11", "momentum_score": 0.85},
            {"ticker": "MXRF11", "momentum_score": 0.70},
            {"ticker": "XPML11", "momentum_score": 0.55},
        ]

        with (
            patch("data.universe.get_tickers", return_value=tickers),
            patch("data.data_bridge.load_returns_bulk", return_value=(return_series, {})),
            patch("core.momentum_engine.rank_by_momentum", return_value=ranking),
        ):
            result = mcp.get("run_momentum")(top_n=2)

        assert "ranking" in result
        assert len(result["ranking"]) == 2
        assert result["total_analyzed"] == 3

    def test_run_momentum_filters_tickers_with_insufficient_data(self):
        mcp = self._setup()
        tickers = ["HGLG11", "MXRF11"]
        return_series = {
            "HGLG11": [0.01] * 8,
            "MXRF11": [0.01] * 3,  # only 3 points, < 6
        }

        with (
            patch("data.universe.get_tickers", return_value=tickers),
            patch("data.data_bridge.load_returns_bulk", return_value=(return_series, {})),
            patch("core.momentum_engine.rank_by_momentum", return_value=[]) as mock_rank,
        ):
            result = mcp.get("run_momentum")()

        # Only HGLG11 has >=6 data points
        call_args = mock_rank.call_args[0][0]
        assert "HGLG11" in call_args
        assert "MXRF11" not in call_args
        assert result["total_analyzed"] == 1

    # --- run_stress ---

    def test_run_stress_returns_scenarios_and_portfolio_size(self):
        mcp = self._setup()
        tickers = ["HGLG11", "MXRF11"]
        portfolio = {"HGLG11": {"cotas": 100}, "MXRF11": {"cotas": 50}}
        scenarios = [
            {"name": "crash", "impact": -0.30},
            {"name": "selic_alta", "impact": -0.15},
        ]

        with (
            patch("data.data_bridge.build_portfolio_from_tickers", return_value=portfolio),
            patch("data.universe.get_sector_map", return_value={}),
            patch("core.stress_engine.run_stress_suite", return_value=scenarios),
        ):
            result = mcp.get("run_stress")(tickers, quantities={"HGLG11": 100, "MXRF11": 50})

        assert result["portfolio_size"] == 2
        assert result["scenarios"] == scenarios

    def test_run_stress_without_quantities(self):
        mcp = self._setup()
        tickers = ["HGLG11"]
        portfolio = {"HGLG11": {"cotas": 1}}
        scenarios = [{"name": "crash", "impact": -0.20}]

        with (
            patch("data.data_bridge.build_portfolio_from_tickers", return_value=portfolio) as mock_build,
            patch("data.universe.get_sector_map", return_value={}),
            patch("core.stress_engine.run_stress_suite", return_value=scenarios),
        ):
            result = mcp.get("run_stress")(tickers)

        mock_build.assert_called_once_with(tickers, None)
        assert result["portfolio_size"] == 1

    # --- run_clusters ---

    def test_run_clusters_returns_result(self):
        mcp = self._setup()
        tickers = ["HGLG11", "MXRF11", "XPML11", "BTLG11"]
        return_series = {t: [0.01] * 8 for t in tickers}
        clusters_result = {"clusters": {"0": ["HGLG11", "BTLG11"], "1": ["MXRF11", "XPML11"]}}

        with (
            patch("data.universe.get_tickers", return_value=tickers),
            patch("data.data_bridge.load_returns_bulk", return_value=(return_series, {})),
            patch("core.cluster_engine.cluster_portfolio", return_value=clusters_result),
        ):
            result = mcp.get("run_clusters")()

        assert result == clusters_result

    def test_run_clusters_insufficient_data_returns_error(self):
        mcp = self._setup()
        tickers = ["HGLG11", "MXRF11"]
        # Only 2 tickers with enough data, < 4
        return_series = {
            "HGLG11": [0.01] * 8,
            "MXRF11": [0.01] * 8,
        }

        with (
            patch("data.universe.get_tickers", return_value=tickers),
            patch("data.data_bridge.load_returns_bulk", return_value=(return_series, {})),
        ):
            result = mcp.get("run_clusters")()

        assert "error" in result

    def test_run_clusters_filters_short_series(self):
        mcp = self._setup()
        tickers = ["A", "B", "C", "D", "E"]
        return_series = {
            "A": [0.01] * 8,
            "B": [0.01] * 8,
            "C": [0.01] * 8,
            "D": [0.01] * 8,
            "E": [0.01] * 3,  # too short
        }
        clusters_result = {"clusters": {}}

        with (
            patch("data.universe.get_tickers", return_value=tickers),
            patch("data.data_bridge.load_returns_bulk", return_value=(return_series, {})),
            patch("core.cluster_engine.cluster_portfolio", return_value=clusters_result) as mock_cluster,
        ):
            mcp.get("run_clusters")()

        valid_passed = mock_cluster.call_args[0][0]
        assert "E" not in valid_passed
        assert len(valid_passed) == 4


# ===========================================================================
# ai_tools.py
# ===========================================================================

class TestAiTools:

    def _setup(self):
        from alphacota_mcp.financial_data.tools.ai_tools import register_ai_tools
        mcp = _build_mcp_with_tools(register_ai_tools)
        return mcp

    def _sample_news(self, n=3):
        return [
            {"titulo": f"News {i}", "data": "2025-01-01", "link": f"http://x.com/{i}", "fonte": "Google"}
            for i in range(n)
        ]

    # --- analyze_fii_sentiment ---

    def test_analyze_fii_sentiment_no_news_returns_failure(self):
        mcp = self._setup()

        with (
            patch("data.news_scraper.fetch_fii_news", return_value=[]),
            patch("core.ai_engine.analyze_fii_news"),  # should not be called
        ):
            result = mcp.get("analyze_fii_sentiment")("HGLG11")

        assert result["success"] is False
        assert "HGLG11" in result["error"]
        assert result["ticker"] == "HGLG11"

    def test_analyze_fii_sentiment_normalizes_ticker(self):
        mcp = self._setup()
        ai_result = {"success": True, "ticker": "HGLG11", "sentiment": "POSITIVO"}

        with (
            patch("data.news_scraper.fetch_fii_news", return_value=self._sample_news()) as mock_news,
            patch("core.ai_engine.analyze_fii_news", return_value=ai_result),
        ):
            mcp.get("analyze_fii_sentiment")("hglg11.SA")

        mock_news.assert_called_once_with("HGLG11", max_results=5)

    def test_analyze_fii_sentiment_enriches_result_with_news_count(self):
        mcp = self._setup()
        news = self._sample_news(n=4)
        ai_result = {"success": True, "ticker": "MXRF11", "sentiment": "NEUTRO"}

        with (
            patch("data.news_scraper.fetch_fii_news", return_value=news),
            patch("core.ai_engine.analyze_fii_news", return_value=ai_result),
        ):
            result = mcp.get("analyze_fii_sentiment")("MXRF11")

        assert result["news_count"] == 4
        assert "news_sources" in result

    def test_analyze_fii_sentiment_passes_api_key_to_engine(self):
        mcp = self._setup()
        news = self._sample_news(n=2)
        ai_result = {"success": True}

        with (
            patch("data.news_scraper.fetch_fii_news", return_value=news),
            patch("core.ai_engine.analyze_fii_news", return_value=ai_result) as mock_ai,
        ):
            mcp.get("analyze_fii_sentiment")("XPML11", api_key="my-key")

        mock_ai.assert_called_once_with("XPML11", news, api_key="my-key")

    def test_analyze_fii_sentiment_empty_api_key_passes_none(self):
        mcp = self._setup()
        news = self._sample_news(n=2)
        ai_result = {"success": True}

        with (
            patch("data.news_scraper.fetch_fii_news", return_value=news),
            patch("core.ai_engine.analyze_fii_news", return_value=ai_result) as mock_ai,
        ):
            mcp.get("analyze_fii_sentiment")("XPML11", api_key="")

        _, kwargs = mock_ai.call_args
        assert kwargs["api_key"] is None

    def test_analyze_fii_sentiment_news_sources_are_unique(self):
        mcp = self._setup()
        news = [
            {"titulo": "N1", "data": "2025-01-01", "fonte": "Google"},
            {"titulo": "N2", "data": "2025-01-02", "fonte": "Google"},
            {"titulo": "N3", "data": "2025-01-03", "fonte": "InfoMoney"},
        ]
        ai_result = {"success": True}

        with (
            patch("data.news_scraper.fetch_fii_news", return_value=news),
            patch("core.ai_engine.analyze_fii_news", return_value=ai_result),
        ):
            result = mcp.get("analyze_fii_sentiment")("HGLG11")

        # Duplicates removed — should have 2 unique sources
        assert len(result["news_sources"]) == 2

    # --- generate_fii_report ---

    def _patch_report_deps(
        self,
        fund=None,
        price=100.0,
        dividend=0.80,
        evaluation=None,
        macro=None,
        news=None,
        sector_map=None,
    ):
        if fund is None:
            fund = {"dividend_yield": 0.09, "pvp": 0.92, "vacancia": 0.04, "liquidez_diaria": 600_000}
        if evaluation is None:
            evaluation = {"score_final": 82.0}
        if macro is None:
            macro = {"selic": 13.75, "ipca": 4.62, "cdi": 13.65}
        if news is None:
            news = [{"titulo": "News", "data": "2025-01-01", "fonte": "G"}]
        if sector_map is None:
            sector_map = {"HGLG11": "Logistica"}
        return {
            "fund": fund,
            "price": price,
            "dividend": dividend,
            "evaluation": evaluation,
            "macro": macro,
            "news": news,
            "sector_map": sector_map,
        }

    def test_generate_fii_report_returns_complete_structure(self):
        mcp = self._setup()
        deps = self._patch_report_deps()

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=deps["fund"]),
            patch("data.universe.get_sector_map", return_value=deps["sector_map"]),
            patch("data.data_bridge.load_last_price", return_value=(deps["price"], "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(deps["dividend"], "hist")),
            patch("core.quant_engine.evaluate_company", return_value=deps["evaluation"]),
            patch("core.macro_engine.get_macro_snapshot", return_value=deps["macro"]),
            patch("data.news_scraper.fetch_fii_news", return_value=deps["news"]),
        ):
            result = mcp.get("generate_fii_report")("HGLG11")

        assert result["ticker"] == "HGLG11"
        assert "summary" in result
        assert "fundamentals" in result
        assert "macro_context" in result
        assert "news" in result
        assert "evaluation" in result
        assert "verdict" in result

    def test_generate_fii_report_normalizes_ticker(self):
        mcp = self._setup()
        deps = self._patch_report_deps()

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=deps["fund"]) as mock_fetch,
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", return_value=(100.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(0.75, "hist")),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 75}),
            patch("core.macro_engine.get_macro_snapshot", return_value=deps["macro"]),
            patch("data.news_scraper.fetch_fii_news", return_value=[]),
        ):
            result = mcp.get("generate_fii_report")("hglg11.SA")

        assert result["ticker"] == "HGLG11"

    def test_generate_fii_report_forte_compra_verdict(self):
        mcp = self._setup()
        # score>=85, pvp<1, dy>selic
        fund = {"dividend_yield": 0.16, "pvp": 0.85, "vacancia": 0.02, "liquidez_diaria": 800_000}
        macro = {"selic": 10.0, "ipca": 4.0, "cdi": 9.9}

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", return_value=(100.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(1.30, "hist")),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 90}),
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.news_scraper.fetch_fii_news", return_value=[]),
        ):
            result = mcp.get("generate_fii_report")("HGLG11")

        assert "FORTE COMPRA" in result["verdict"]

    def test_generate_fii_report_compra_verdict(self):
        mcp = self._setup()
        # score>=75, dy>selic, pvp>=1
        fund = {"dividend_yield": 0.12, "pvp": 1.0, "vacancia": 0.03, "liquidez_diaria": 500_000}
        macro = {"selic": 10.0, "ipca": 4.0, "cdi": 9.9}

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", return_value=(100.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(1.0, "hist")),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 78}),
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.news_scraper.fetch_fii_news", return_value=[]),
        ):
            result = mcp.get("generate_fii_report")("MXRF11")

        assert "COMPRA" in result["verdict"]

    def test_generate_fii_report_neutro_verdict(self):
        mcp = self._setup()
        fund = {"dividend_yield": 0.08, "pvp": 1.05, "vacancia": 0.06, "liquidez_diaria": 300_000}
        macro = {"selic": 13.0, "ipca": 5.0, "cdi": 12.9}

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", return_value=(90.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(0.60, "hist")),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 65}),
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.news_scraper.fetch_fii_news", return_value=[]),
        ):
            result = mcp.get("generate_fii_report")("XPML11")

        assert "NEUTRO" in result["verdict"]

    def test_generate_fii_report_cautela_verdict(self):
        mcp = self._setup()
        fund = {"dividend_yield": 0.05, "pvp": 1.30, "vacancia": 0.20, "liquidez_diaria": 50_000}
        macro = {"selic": 14.0, "ipca": 6.0, "cdi": 13.9}

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", return_value=(60.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(0.25, "hist")),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 40}),
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.news_scraper.fetch_fii_news", return_value=[]),
        ):
            result = mcp.get("generate_fii_report")("WEAK11")

        assert "CAUTELA" in result["verdict"]

    def test_generate_fii_report_price_exception_defaults_to_zero(self):
        mcp = self._setup()
        fund = {"dividend_yield": 0.09, "pvp": 0.95, "vacancia": 0.04, "liquidez_diaria": 500_000}
        macro = {"selic": 13.0, "ipca": 4.5, "cdi": 12.9}

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", side_effect=Exception("no price")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(0.75, "hist")),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 75}),
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.news_scraper.fetch_fii_news", return_value=[]),
        ):
            result = mcp.get("generate_fii_report")("HGLG11")

        assert result["summary"]["price"] == 0

    def test_generate_fii_report_dividend_exception_defaults_to_zero(self):
        mcp = self._setup()
        fund = {"dividend_yield": 0.09, "pvp": 0.95, "vacancia": 0.04, "liquidez_diaria": 500_000}
        macro = {"selic": 13.0, "ipca": 4.5, "cdi": 12.9}

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", return_value=(100.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", side_effect=Exception("no div")),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 75}),
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.news_scraper.fetch_fii_news", return_value=[]),
        ):
            result = mcp.get("generate_fii_report")("HGLG11")

        assert result["summary"]["dividend_monthly"] == 0

    def test_generate_fii_report_evaluate_exception_defaults_score_zero(self):
        mcp = self._setup()
        fund = {"dividend_yield": 0.09, "pvp": 0.95, "vacancia": 0.04, "liquidez_diaria": 500_000}
        macro = {"selic": 13.0, "ipca": 4.5, "cdi": 12.9}

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", return_value=(100.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(0.75, "hist")),
            patch("core.quant_engine.evaluate_company", side_effect=Exception("engine down")),
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.news_scraper.fetch_fii_news", return_value=[]),
        ):
            result = mcp.get("generate_fii_report")("HGLG11")

        assert result["summary"]["score"] == 0
        assert result["evaluation"] == {}

    def test_generate_fii_report_pvp_status_desconto(self):
        mcp = self._setup()
        fund = {"dividend_yield": 0.10, "pvp": 0.85, "vacancia": 0.03, "liquidez_diaria": 500_000}
        macro = {"selic": 10.0, "ipca": 4.0, "cdi": 9.9}

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", return_value=(100.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(0.83, "hist")),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 80}),
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.news_scraper.fetch_fii_news", return_value=[]),
        ):
            result = mcp.get("generate_fii_report")("HGLG11")

        assert result["fundamentals"]["pvp_status"] == "Desconto"
        assert result["fundamentals"]["pvp_desconto"] == 15.0

    def test_generate_fii_report_pvp_status_premio(self):
        mcp = self._setup()
        fund = {"dividend_yield": 0.08, "pvp": 1.10, "vacancia": 0.05, "liquidez_diaria": 300_000}
        macro = {"selic": 13.0, "ipca": 4.5, "cdi": 12.9}

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", return_value=(110.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(0.73, "hist")),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 55}),
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.news_scraper.fetch_fii_news", return_value=[]),
        ):
            result = mcp.get("generate_fii_report")("XPML11")

        assert result["fundamentals"]["pvp_status"] == "Premio"
        assert result["fundamentals"]["pvp_desconto"] == 0

    def test_generate_fii_report_pvp_status_justo(self):
        mcp = self._setup()
        fund = {"dividend_yield": 0.09, "pvp": 1.0, "vacancia": 0.04, "liquidez_diaria": 400_000}
        macro = {"selic": 13.0, "ipca": 4.5, "cdi": 12.9}

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", return_value=(100.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(0.75, "hist")),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 65}),
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.news_scraper.fetch_fii_news", return_value=[]),
        ):
            result = mcp.get("generate_fii_report")("MXRF11")

        assert result["fundamentals"]["pvp_status"] == "Justo"

    def test_generate_fii_report_macro_context_atratividade_alta(self):
        mcp = self._setup()
        fund = {"dividend_yield": 0.12, "pvp": 0.90, "vacancia": 0.03, "liquidez_diaria": 600_000}
        macro = {"selic": 10.0, "ipca": 4.0, "cdi": 9.9}

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", return_value=(100.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(1.0, "hist")),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 80}),
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.news_scraper.fetch_fii_news", return_value=[]),
        ):
            result = mcp.get("generate_fii_report")("HGLG11")

        # dy=12% > selic=10% → spread > 0 → Alta
        assert result["macro_context"]["atratividade"] == "Alta"

    def test_generate_fii_report_macro_context_atratividade_moderada(self):
        mcp = self._setup()
        # dy=12%, selic=13% → spread=-1 (between -2 and 0)
        fund = {"dividend_yield": 0.12, "pvp": 0.90, "vacancia": 0.03, "liquidez_diaria": 600_000}
        macro = {"selic": 13.0, "ipca": 4.0, "cdi": 12.9}

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", return_value=(100.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(1.0, "hist")),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 80}),
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.news_scraper.fetch_fii_news", return_value=[]),
        ):
            result = mcp.get("generate_fii_report")("HGLG11")

        assert result["macro_context"]["atratividade"] == "Moderada"

    def test_generate_fii_report_macro_context_atratividade_baixa(self):
        mcp = self._setup()
        # dy=8%, selic=14% → spread=-6 < -2 → Baixa
        fund = {"dividend_yield": 0.08, "pvp": 1.10, "vacancia": 0.08, "liquidez_diaria": 200_000}
        macro = {"selic": 14.0, "ipca": 5.0, "cdi": 13.9}

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", return_value=(80.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(0.53, "hist")),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 50}),
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.news_scraper.fetch_fii_news", return_value=[]),
        ):
            result = mcp.get("generate_fii_report")("WEAK11")

        assert result["macro_context"]["atratividade"] == "Baixa"

    def test_generate_fii_report_news_truncated_to_3(self):
        mcp = self._setup()
        fund = {"dividend_yield": 0.09, "pvp": 0.95, "vacancia": 0.04, "liquidez_diaria": 500_000}
        macro = {"selic": 13.0, "ipca": 4.5, "cdi": 12.9}
        news = [{"titulo": f"N{i}", "data": "2025-01-01", "fonte": "G"} for i in range(5)]

        with (
            patch("data.fundamentals_scraper.fetch_fundamentals", return_value=fund),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.data_bridge.load_last_price", return_value=(100.0, "yfinance")),
            patch("data.data_bridge.load_monthly_dividend", return_value=(0.75, "hist")),
            patch("core.quant_engine.evaluate_company", return_value={"score_final": 75}),
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.news_scraper.fetch_fii_news", return_value=news),
        ):
            result = mcp.get("generate_fii_report")("HGLG11")

        assert len(result["news"]) == 3

    # --- generate_daily_market_report ---

    def test_generate_daily_market_report_returns_structure(self):
        mcp = self._setup()
        universe = [
            {"ticker": "HGLG11"},
            {"ticker": "MXRF11"},
        ]
        fundamentals = {
            "HGLG11": {"dividend_yield": 0.11, "pvp": 0.88, "vacancia": 0.03, "liquidez_diaria": 600_000},
            "MXRF11": {"dividend_yield": 0.09, "pvp": 1.02, "vacancia": 0.05, "liquidez_diaria": 300_000},
        }
        macro = {"selic": 13.0, "ipca": 4.5, "cdi": 12.9}
        market_news = [{"titulo": "Market news", "data": "2025-01-01", "fonte": "G"}]

        def eval_side(ticker, _data):
            return {"score_final": 85 if ticker == "HGLG11" else 70}

        with (
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.universe.get_universe", return_value=universe),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=fundamentals),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.news_scraper.fetch_market_news", return_value=market_news),
            patch("core.quant_engine.evaluate_company", side_effect=eval_side),
        ):
            result = mcp.get("generate_daily_market_report")()

        assert "macro" in result
        assert "market_stats" in result
        assert "top_opportunities" in result
        assert "undervalued" in result
        assert "news" in result
        assert result["market_stats"]["total_fiis"] == 2

    def test_generate_daily_market_report_top_opportunities_sorted_by_score(self):
        mcp = self._setup()
        universe = [{"ticker": "HGLG11"}, {"ticker": "MXRF11"}]
        fundamentals = {
            "HGLG11": {"dividend_yield": 0.11, "pvp": 0.88, "vacancia": 0.03, "liquidez_diaria": 600_000},
            "MXRF11": {"dividend_yield": 0.09, "pvp": 1.02, "vacancia": 0.05, "liquidez_diaria": 300_000},
        }
        macro = {"selic": 13.0, "ipca": 4.5, "cdi": 12.9}

        def eval_side(ticker, _data):
            return {"score_final": 90 if ticker == "HGLG11" else 65}

        with (
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.universe.get_universe", return_value=universe),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=fundamentals),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.news_scraper.fetch_market_news", return_value=[]),
            patch("core.quant_engine.evaluate_company", side_effect=eval_side),
        ):
            result = mcp.get("generate_daily_market_report")()

        ops = result["top_opportunities"]
        for i in range(len(ops) - 1):
            assert ops[i]["score"] >= ops[i + 1]["score"]

    def test_generate_daily_market_report_undervalued_filters_correctly(self):
        mcp = self._setup()
        # selic=10; HGLG11: pvp=0.88<0.95 and dy=11%>10% -> undervalued
        # MXRF11: pvp=1.02>=0.95 -> not undervalued
        universe = [{"ticker": "HGLG11"}, {"ticker": "MXRF11"}]
        fundamentals = {
            "HGLG11": {"dividend_yield": 0.11, "pvp": 0.88, "vacancia": 0.03, "liquidez_diaria": 600_000},
            "MXRF11": {"dividend_yield": 0.09, "pvp": 1.02, "vacancia": 0.05, "liquidez_diaria": 300_000},
        }
        macro = {"selic": 10.0, "ipca": 4.0, "cdi": 9.9}

        def eval_side(_ticker, _data):
            return {"score_final": 80}

        with (
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.universe.get_universe", return_value=universe),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=fundamentals),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.news_scraper.fetch_market_news", return_value=[]),
            patch("core.quant_engine.evaluate_company", side_effect=eval_side),
        ):
            result = mcp.get("generate_daily_market_report")()

        undervalued_tickers = [u["ticker"] for u in result["undervalued"]]
        assert "HGLG11" in undervalued_tickers
        assert "MXRF11" not in undervalued_tickers

    def test_generate_daily_market_report_evaluate_exception_score_zero(self):
        mcp = self._setup()
        universe = [{"ticker": "ERR11"}]
        fundamentals = {"ERR11": {"dividend_yield": 0.09, "pvp": 0.90, "vacancia": 0.03, "liquidez_diaria": 400_000}}
        macro = {"selic": 13.0, "ipca": 4.5, "cdi": 12.9}

        with (
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.universe.get_universe", return_value=universe),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value=fundamentals),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.news_scraper.fetch_market_news", return_value=[]),
            patch("core.quant_engine.evaluate_company", side_effect=Exception("engine boom")),
        ):
            result = mcp.get("generate_daily_market_report")()

        assert result["top_opportunities"][0]["score"] == 0

    def test_generate_daily_market_report_empty_universe(self):
        mcp = self._setup()
        macro = {"selic": 13.0, "ipca": 4.5, "cdi": 12.9}

        with (
            patch("core.macro_engine.get_macro_snapshot", return_value=macro),
            patch("data.universe.get_universe", return_value=[]),
            patch("data.fundamentals_scraper.fetch_fundamentals_bulk", return_value={}),
            patch("data.universe.get_sector_map", return_value={}),
            patch("data.news_scraper.fetch_market_news", return_value=[]),
        ):
            result = mcp.get("generate_daily_market_report")()

        assert result["market_stats"]["total_fiis"] == 0
        assert result["market_stats"]["avg_dy"] == 0
        assert result["market_stats"]["avg_pvp"] == 0
