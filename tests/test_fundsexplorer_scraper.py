"""Tests for data/fundsexplorer_scraper.py — FundsExplorer scraping client."""

import datetime
import json
import os
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from data.fundsexplorer_scraper import (
    _init_cache,
    _get_cached,
    _save_cache,
    _parse_br_number,
    scrape_ranking,
    scrape_fii_detail,
    fetch_fundsexplorer_data,
    fetch_fundsexplorer_bulk,
)

# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------


class TestParseBrNumber:
    def test_normal_number(self):
        assert _parse_br_number("1.234,56") == 1234.56

    def test_with_currency(self):
        assert _parse_br_number("R$ 100,50") == 100.50

    def test_with_percent(self):
        assert _parse_br_number("8,42%") == 8.42

    def test_dash(self):
        assert _parse_br_number("-") == 0.0

    def test_na(self):
        assert _parse_br_number("N/A") == 0.0

    def test_empty(self):
        assert _parse_br_number("") == 0.0

    def test_none_like(self):
        assert _parse_br_number("--") == 0.0

    def test_simple_integer(self):
        assert _parse_br_number("100") == 100.0

    def test_invalid_text(self):
        assert _parse_br_number("abc") == 0.0


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------


class TestFundsExplorerCache:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

    def teardown_method(self):
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_init_cache_creates_table(self):
        conn = _init_cache(self.db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fundsexplorer_cache'")
        assert cursor.fetchone() is not None
        conn.close()

    def test_save_and_get_cached(self):
        conn = _init_cache(self.db_path)
        _save_cache(conn, "HGLG11", {"ticker": "HGLG11", "dy_12m": 8.5})
        result = _get_cached(conn, "HGLG11")
        assert result["ticker"] == "HGLG11"
        assert result["dy_12m"] == 8.5
        assert result["_source"] == "fundsexplorer_cache"
        conn.close()

    def test_get_cached_missing(self):
        conn = _init_cache(self.db_path)
        result = _get_cached(conn, "NONEXISTENT")
        assert result is None
        conn.close()

    def test_get_cached_expired(self):
        conn = _init_cache(self.db_path)
        old_time = (datetime.datetime.now() - datetime.timedelta(hours=48)).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO fundsexplorer_cache (ticker, fetched_at, data_json) VALUES (?, ?, ?)",
            ("OLD11", old_time, '{"ticker": "OLD11"}'),
        )
        conn.commit()
        result = _get_cached(conn, "OLD11", ttl_hours=1)
        assert result is None
        conn.close()

    def test_save_cache_overwrites(self):
        conn = _init_cache(self.db_path)
        _save_cache(conn, "T11", {"v": 1})
        _save_cache(conn, "T11", {"v": 2})
        result = _get_cached(conn, "T11")
        assert result["v"] == 2
        conn.close()


# ---------------------------------------------------------------------------
# Ranking scraping
# ---------------------------------------------------------------------------

_RANKING_HTML = """
<html><body>
<table id="table-ranking">
<tbody>
<tr>
    <td><a>HGLG11</a></td>
    <td>Logistica</td>
    <td>R$ 155,00</td>
    <td>8,42%</td>
    <td>0,95</td>
    <td>11.000.000</td>
    <td>R$ 1,10</td>
    <td>R$ 5.000.000.000</td>
    <td>500.000</td>
</tr>
<tr>
    <td><a>MXRF11</a></td>
    <td>Papel</td>
    <td>R$ 10,50</td>
    <td>12,30%</td>
    <td>1,05</td>
    <td>25.000.000</td>
    <td>R$ 0,10</td>
    <td>R$ 3.000.000.000</td>
    <td>1.200.000</td>
</tr>
<tr><td>AB</td><td>Short</td></tr>
</tbody>
</table>
</body></html>
"""


class TestScrapeRanking:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

    def teardown_method(self):
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    @patch("data.fundsexplorer_scraper.requests")
    def test_scrape_ranking_success(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = _RANKING_HTML
        mock_requests.get.return_value = mock_resp

        results = scrape_ranking(db_path=self.db_path)

        assert len(results) == 2  # Short row filtered
        assert results[0]["ticker"] == "HGLG11"
        assert results[0]["setor"] == "Logistica"
        assert results[0]["_source"] == "fundsexplorer"
        assert results[1]["ticker"] == "MXRF11"

    @patch("data.fundsexplorer_scraper.requests")
    def test_scrape_ranking_http_error(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_requests.get.return_value = mock_resp

        results = scrape_ranking(db_path=self.db_path)
        assert results == []

    @patch("data.fundsexplorer_scraper.requests")
    def test_scrape_ranking_no_table(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body><p>No table here</p></body></html>"
        mock_requests.get.return_value = mock_resp

        results = scrape_ranking(db_path=self.db_path)
        assert results == []

    @patch("data.fundsexplorer_scraper.requests")
    def test_scrape_ranking_exception(self, mock_requests):
        mock_requests.get.side_effect = Exception("Timeout")
        results = scrape_ranking(db_path=self.db_path)
        assert results == []

    @patch("data.fundsexplorer_scraper.HAS_DEPS", False)
    def test_scrape_ranking_no_deps(self):
        results = scrape_ranking(db_path=self.db_path)
        assert results == []


# ---------------------------------------------------------------------------
# FII detail scraping
# ---------------------------------------------------------------------------

_DETAIL_HTML = """
<html><body>
<div class="indicator-box">
    <span class="title">Dividend Yield (12M)</span>
    <span class="value">8,42%</span>
</div>
<div class="indicator-box">
    <span class="title">P/VP</span>
    <span class="value">0,95</span>
</div>
<div class="indicator-box">
    <span class="title">Último Rendimento</span>
    <span class="value">R$ 1,10</span>
</div>
<div class="indicator-box">
    <span class="title">Patrimônio Líquido</span>
    <span class="value">R$ 5.000.000.000</span>
</div>
<div class="indicator-box">
    <span class="title">Cotistas</span>
    <span class="value">500.000</span>
</div>
<div class="indicator-box">
    <span class="title">Liquidez Diária</span>
    <span class="value">11.000.000</span>
</div>
<div class="indicator-box">
    <span class="title">Vacância Física</span>
    <span class="value">5,20%</span>
</div>
<table class="dividends-table">
<tbody>
<tr><td>Jan/2025</td><td>R$ 1,10</td></tr>
<tr><td>Dez/2024</td><td>R$ 1,05</td></tr>
</tbody>
</table>
</body></html>
"""


class TestScrapeFiiDetail:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

    def teardown_method(self):
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    @patch("data.fundsexplorer_scraper.requests")
    def test_scrape_detail_success(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = _DETAIL_HTML
        mock_requests.get.return_value = mock_resp

        result = scrape_fii_detail("HGLG11", db_path=self.db_path)

        assert result is not None
        assert result["ticker"] == "HGLG11"
        assert result["dy_12m"] == 8.42
        assert result["pvp"] == 0.95
        assert result["ultimo_dividendo"] == 1.10
        assert result["vacancia"] == 5.20
        assert "historico_dividendos" in result
        assert len(result["historico_dividendos"]) == 2

    @patch("data.fundsexplorer_scraper.requests")
    def test_scrape_detail_uses_cache(self, mock_requests):
        conn = _init_cache(self.db_path)
        _save_cache(conn, "HGLG11", {"ticker": "HGLG11", "dy_12m": 99.0})
        conn.close()

        result = scrape_fii_detail("HGLG11", db_path=self.db_path)
        assert result["dy_12m"] == 99.0
        mock_requests.get.assert_not_called()

    @patch("data.fundsexplorer_scraper.requests")
    def test_scrape_detail_http_error(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_requests.get.return_value = mock_resp

        result = scrape_fii_detail("FAKE11", db_path=self.db_path)
        assert result is None

    @patch("data.fundsexplorer_scraper.requests")
    def test_scrape_detail_exception(self, mock_requests):
        mock_requests.get.side_effect = Exception("Connection error")
        result = scrape_fii_detail("HGLG11", db_path=self.db_path)
        assert result is None

    @patch("data.fundsexplorer_scraper.HAS_DEPS", False)
    def test_scrape_detail_no_deps(self):
        result = scrape_fii_detail("HGLG11", db_path=self.db_path)
        assert result is None

    @patch("data.fundsexplorer_scraper.requests")
    def test_scrape_detail_strips_sa_suffix(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = _DETAIL_HTML
        mock_requests.get.return_value = mock_resp

        result = scrape_fii_detail("hglg11.SA", db_path=self.db_path)
        assert result["ticker"] == "HGLG11"


# ---------------------------------------------------------------------------
# Public API tests
# ---------------------------------------------------------------------------


class TestFetchFundsexplorerData:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

    def teardown_method(self):
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_fetch_data_returns_cache(self):
        conn = _init_cache(self.db_path)
        _save_cache(conn, "HGLG11", {"ticker": "HGLG11", "cached": True})
        conn.close()

        result = fetch_fundsexplorer_data("HGLG11", db_path=self.db_path)
        assert result["cached"] is True

    @patch("data.fundsexplorer_scraper.scrape_fii_detail")
    def test_fetch_data_falls_back_to_scrape(self, mock_scrape):
        mock_scrape.return_value = {"ticker": "XPML11", "scraped": True}

        result = fetch_fundsexplorer_data("XPML11", db_path=self.db_path)
        assert result["scraped"] is True


class TestFetchFundsexplorerBulk:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

    def teardown_method(self):
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_bulk_all_cached(self):
        conn = _init_cache(self.db_path)
        _save_cache(conn, "HGLG11", {"ticker": "HGLG11"})
        _save_cache(conn, "MXRF11", {"ticker": "MXRF11"})
        conn.close()

        results = fetch_fundsexplorer_bulk(["HGLG11", "MXRF11"], db_path=self.db_path)
        assert len(results) == 2
        assert "HGLG11" in results
        assert "MXRF11" in results

    @patch("data.fundsexplorer_scraper.scrape_fii_detail")
    @patch("data.fundsexplorer_scraper.scrape_ranking")
    def test_bulk_uses_ranking_then_individual(self, mock_ranking, mock_detail):
        mock_ranking.return_value = [
            {"ticker": "HGLG11", "dy_12m": 8.5},
        ]
        mock_detail.return_value = {"ticker": "XPML11", "dy_12m": 7.0}

        results = fetch_fundsexplorer_bulk(["HGLG11", "XPML11"], db_path=self.db_path)

        assert "HGLG11" in results
        assert results["HGLG11"]["dy_12m"] == 8.5
        # XPML11 should have been fetched individually
        mock_detail.assert_called()
