"""Tests for core/report_engine.py — CSV and HTML report generation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from core.report_engine import (
    portfolio_to_csv,
    backtest_metrics_to_csv,
    generate_html_tearsheet,
    generate_portfolio_csv_download,
    generate_html_download,
)


def _portfolio():
    return [
        {"ticker": "HGLG11", "quantidade": 10, "preco_atual": 160.0, "dividend_mensal": 1.20},
        {"ticker": "XPML11", "quantidade": 5, "preco_atual": 100.0, "dividend_mensal": 0.85},
    ]


class TestPortfolioCsv:
    def test_has_header(self):
        csv = portfolio_to_csv(_portfolio())
        assert "ticker" in csv
        assert "dy_anual_%" in csv

    def test_contains_tickers(self):
        csv = portfolio_to_csv(_portfolio())
        assert "HGLG11" in csv
        assert "XPML11" in csv

    def test_empty_portfolio(self):
        csv = portfolio_to_csv([])
        lines = csv.strip().split("\n")
        assert len(lines) == 1  # header only

    def test_dy_calculation(self):
        csv = portfolio_to_csv([{"ticker": "T11", "quantidade": 1, "preco_atual": 100.0, "dividend_mensal": 1.0}])
        assert "12.00" in csv  # DY = 1.0 * 12 / 100 * 100 = 12%


class TestBacktestMetricsCsv:
    def test_header(self):
        csv = backtest_metrics_to_csv({"cagr": 0.12, "sharpe": 1.5})
        assert "Métrica" in csv
        assert "Valor" in csv

    def test_float_formatting(self):
        csv = backtest_metrics_to_csv({"cagr": 0.1234})
        assert "0.1234" in csv

    def test_non_float_values(self):
        csv = backtest_metrics_to_csv({"status": "ok"})
        assert "ok" in csv


class TestGenerateHtmlTearsheet:
    def test_returns_valid_html(self):
        html = generate_html_tearsheet(_portfolio())
        assert "<!DOCTYPE html>" in html
        assert "HGLG11" in html
        assert "XPML11" in html

    def test_custom_title(self):
        html = generate_html_tearsheet(_portfolio(), title="Test Report")
        assert "Test Report" in html

    def test_with_backtest_metrics(self):
        metrics = {"cagr": 0.15, "sharpe": 1.2, "max_drawdown": -0.08}
        html = generate_html_tearsheet(_portfolio(), backtest_metrics=metrics)
        assert "Backtest" in html
        assert "CAGR" in html

    def test_with_correlation_matrix(self):
        corr = {"HGLG11": {"HGLG11": 1.0, "XPML11": 0.6}, "XPML11": {"HGLG11": 0.6, "XPML11": 1.0}}
        html = generate_html_tearsheet(_portfolio(), correlation_matrix=corr)
        assert "Correlação" in html

    def test_with_stress_summary(self):
        stress = {
            "worst_scenario": "Crise",
            "worst_drawdown": -0.25,
            "avg_drawdown": -0.15,
            "avg_div_cut": -0.10,
            "n_scenarios": 5,
        }
        html = generate_html_tearsheet(_portfolio(), stress_summary=stress)
        assert "Stress" in html
        assert "Crise" in html

    def test_empty_portfolio(self):
        html = generate_html_tearsheet([])
        assert "<!DOCTYPE html>" in html


class TestDownloadHelpers:
    def test_csv_download_returns_bytes(self):
        result = generate_portfolio_csv_download(_portfolio())
        assert isinstance(result, bytes)
        assert b"HGLG11" in result

    def test_html_download_returns_bytes(self):
        html = generate_html_tearsheet(_portfolio())
        result = generate_html_download(html)
        assert isinstance(result, bytes)
        assert b"<!DOCTYPE html>" in result
