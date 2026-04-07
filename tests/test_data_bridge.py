"""Tests for data/data_bridge.py — Data bridge with synthetic fallbacks."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import data.data_bridge as bridge


class TestSyntheticReturns:
    def test_returns_list(self):
        returns = bridge._synthetic_returns("HGLG11", 12)
        assert isinstance(returns, list)
        assert len(returns) == 12

    def test_deterministic_for_same_ticker(self):
        r1 = bridge._synthetic_returns("HGLG11", 12)
        r2 = bridge._synthetic_returns("HGLG11", 12)
        assert r1 == r2

    def test_different_tickers_differ(self):
        r1 = bridge._synthetic_returns("HGLG11", 12)
        r2 = bridge._synthetic_returns("XPML11", 12)
        assert r1 != r2

    def test_unknown_sector_uses_outros(self):
        returns = bridge._synthetic_returns("ZZZZ11", 12)
        assert len(returns) == 12


class TestLoadReturns:
    def test_synthetic_fallback_without_loader(self):
        with patch.object(bridge, "_HAS_LOADER", False):
            returns, source = bridge.load_returns("HGLG11", "2023-01-01", "2025-01-01")
            assert source == "sintético"
            assert len(returns) > 0

    def test_synthetic_date_range(self):
        with patch.object(bridge, "_HAS_LOADER", False):
            returns, _ = bridge.load_returns("HGLG11", "2024-01-01", "2025-01-01")
            assert len(returns) == 12

    def test_invalid_dates_fallback(self):
        with patch.object(bridge, "_HAS_LOADER", False):
            returns, source = bridge.load_returns("HGLG11", "bad", "dates")
            assert source == "sintético"
            assert len(returns) == 36


class TestLoadReturnsBulk:
    def test_multiple_tickers(self):
        with patch.object(bridge, "_HAS_LOADER", False):
            series, sources = bridge.load_returns_bulk(["HGLG11", "XPML11"], "2024-01-01", "2025-01-01")
            assert len(series) == 2
            assert all(s == "sintético" for s in sources.values())


class TestLoadLastPrice:
    def test_fallback_price(self):
        with patch.object(bridge, "_HAS_LOADER", False):
            price, source = bridge.load_last_price("HGLG11")
            assert source == "fallback"
            assert price == 155.0

    def test_unknown_ticker_default(self):
        with patch.object(bridge, "_HAS_LOADER", False):
            price, source = bridge.load_last_price("ZZZZ11")
            assert source == "fallback"
            assert price == 10.0


class TestLoadMonthlyDividend:
    def test_fallback_dividend(self):
        with patch.object(bridge, "_HAS_LOADER", False):
            div, source = bridge.load_monthly_dividend("HGLG11")
            assert source == "fallback"
            assert div == 1.10

    def test_unknown_ticker_default(self):
        with patch.object(bridge, "_HAS_LOADER", False):
            div, source = bridge.load_monthly_dividend("ZZZZ11")
            assert source == "fallback"
            assert div == 0.07


class TestBuildPortfolioFromTickers:
    def test_builds_portfolio(self):
        with patch.object(bridge, "_HAS_LOADER", False):
            portfolio = bridge.build_portfolio_from_tickers(["HGLG11", "XPML11"])
            assert len(portfolio) == 2
            assert portfolio[0]["ticker"] == "HGLG11"
            assert portfolio[0]["quantidade"] == 100
            assert portfolio[0]["preco_atual"] > 0

    def test_custom_quantities(self):
        with patch.object(bridge, "_HAS_LOADER", False):
            portfolio = bridge.build_portfolio_from_tickers(["HGLG11"], quantities={"HGLG11": 50})
            assert portfolio[0]["quantidade"] == 50


class TestGetDataQualityReport:
    def test_report_structure(self):
        with patch.object(bridge, "_HAS_LOADER", False):
            report = bridge.get_data_quality_report(["HGLG11", "XPML11"], "2024-01-01", "2025-01-01")
            assert report["total"] == 2
            assert report["sintetico"] == 2
            assert report["real"] == 0
            assert report["pct_real"] == 0.0


class TestLoadReturnsWithMockedLoader:
    def test_real_returns_when_loader_available(self):
        mock_prices = [{"close": "100"}, {"close": "105"}, {"close": "110"}, {"close": "108"}]
        with (
            patch.object(bridge, "_HAS_LOADER", True),
            patch.object(bridge, "HAS_YFINANCE", True),
            patch("data.data_bridge.fetch_prices", return_value=mock_prices),
            patch("data.data_bridge.get_close_prices", return_value=[100, 105, 110, 108]),
            patch("data.data_bridge.calculate_monthly_returns", return_value=[0.0, 0.05, 0.048, -0.018]),
        ):
            returns, source = bridge.load_returns("HGLG11", "2024-01-01", "2025-01-01")
            assert source == "real"

    def test_fallback_on_few_prices(self):
        with (
            patch.object(bridge, "_HAS_LOADER", True),
            patch.object(bridge, "HAS_YFINANCE", True),
            patch("data.data_bridge.fetch_prices", return_value=[{"close": "100"}]),
        ):
            returns, source = bridge.load_returns("HGLG11", "2024-01-01", "2025-01-01")
            assert source == "sintético"

    def test_fallback_on_exception(self):
        with (
            patch.object(bridge, "_HAS_LOADER", True),
            patch.object(bridge, "HAS_YFINANCE", True),
            patch("data.data_bridge.fetch_prices", side_effect=Exception("API error")),
        ):
            returns, source = bridge.load_returns("HGLG11", "2024-01-01", "2025-01-01")
            assert source == "sintético"


class TestLoadLastPriceWithMockedLoader:
    def test_real_price(self):
        with (
            patch.object(bridge, "_HAS_LOADER", True),
            patch.object(bridge, "HAS_YFINANCE", True),
            patch("data.data_bridge.fetch_prices", return_value=[{"close": "155.50"}]),
        ):
            price, source = bridge.load_last_price("HGLG11")
            assert source == "real"
            assert price == 155.50

    def test_fallback_on_zero_price(self):
        with (
            patch.object(bridge, "_HAS_LOADER", True),
            patch.object(bridge, "HAS_YFINANCE", True),
            patch("data.data_bridge.fetch_prices", return_value=[{"close": "0"}]),
        ):
            price, source = bridge.load_last_price("HGLG11")
            assert source == "fallback"

    def test_fallback_on_empty(self):
        with (
            patch.object(bridge, "_HAS_LOADER", True),
            patch.object(bridge, "HAS_YFINANCE", True),
            patch("data.data_bridge.fetch_prices", return_value=[]),
        ):
            price, source = bridge.load_last_price("HGLG11")
            assert source == "fallback"

    def test_fallback_on_exception(self):
        with (
            patch.object(bridge, "_HAS_LOADER", True),
            patch.object(bridge, "HAS_YFINANCE", True),
            patch("data.data_bridge.fetch_prices", side_effect=Exception("fail")),
        ):
            price, source = bridge.load_last_price("HGLG11")
            assert source == "fallback"


class TestLoadMonthlyDividendWithMockedLoader:
    def test_real_dividends(self):
        mock_divs = [{"dividend": "0.10"} for _ in range(8)]
        with (
            patch.object(bridge, "_HAS_LOADER", True),
            patch.object(bridge, "HAS_YFINANCE", True),
            patch("data.data_bridge.fetch_dividends", return_value=mock_divs),
        ):
            div, source = bridge.load_monthly_dividend("HGLG11")
            assert source == "real"
            assert div == pytest.approx(0.10)

    def test_fallback_few_dividends(self):
        with (
            patch.object(bridge, "_HAS_LOADER", True),
            patch.object(bridge, "HAS_YFINANCE", True),
            patch("data.data_bridge.fetch_dividends", return_value=[{"dividend": "0.1"}] * 3),
        ):
            div, source = bridge.load_monthly_dividend("HGLG11")
            assert source == "fallback"

    def test_fallback_on_exception(self):
        with (
            patch.object(bridge, "_HAS_LOADER", True),
            patch.object(bridge, "HAS_YFINANCE", True),
            patch("data.data_bridge.fetch_dividends", side_effect=Exception("fail")),
        ):
            div, source = bridge.load_monthly_dividend("HGLG11")
            assert source == "fallback"
