"""Tests for data/fundamentals_scraper.py — Fundamentals cache and scraping."""

import sys
import json
import datetime
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import data.fundamentals_scraper as scraper


class TestParseIndicator:
    def test_percentage(self):
        assert scraper._parse_indicator("10,50%") == pytest.approx(10.5)

    def test_currency(self):
        assert scraper._parse_indicator("R$ 0,09") == pytest.approx(0.09)

    def test_simple_number(self):
        assert scraper._parse_indicator("1,02") == pytest.approx(1.02)

    def test_dash(self):
        assert scraper._parse_indicator("-") == 0.0

    def test_na(self):
        assert scraper._parse_indicator("N/A") == 0.0

    def test_empty(self):
        assert scraper._parse_indicator("") == 0.0

    def test_none(self):
        assert scraper._parse_indicator(None) == 0.0

    def test_double_dash(self):
        assert scraper._parse_indicator("--") == 0.0

    def test_thousands(self):
        # "1.500,00" → remove dots, replace comma → 1500.00
        assert scraper._parse_indicator("1.500,00") == pytest.approx(1500.0)


class TestCacheDB:
    def test_init_creates_table(self, tmp_path):
        db = str(tmp_path / "test.db")
        conn = scraper._init_cache_db(db)
        # Table should exist
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fundamentals_cache'"
        ).fetchone()
        assert row is not None
        conn.close()

    def test_save_and_get_cached(self, tmp_path):
        db = str(tmp_path / "test.db")
        conn = scraper._init_cache_db(db)
        data = {"dividend_yield": 0.10, "pvp": 0.95}
        scraper._save_cache(conn, "MXRF11", data, source="test")

        cached = scraper._get_cached(conn, "MXRF11", ttl_hours=24)
        assert cached is not None
        assert cached["dividend_yield"] == 0.10
        assert cached["_source"] == "cache"
        conn.close()

    def test_get_cached_missing(self, tmp_path):
        db = str(tmp_path / "test.db")
        conn = scraper._init_cache_db(db)
        assert scraper._get_cached(conn, "ZZZZ11") is None
        conn.close()

    def test_get_cached_expired(self, tmp_path):
        db = str(tmp_path / "test.db")
        conn = scraper._init_cache_db(db)
        # Insert with old timestamp
        old_time = (datetime.datetime.now() - datetime.timedelta(hours=48)).isoformat()
        conn.execute(
            "INSERT INTO fundamentals_cache (ticker, fetched_at, data_json, source) VALUES (?, ?, ?, ?)",
            ("MXRF11", old_time, json.dumps({"pvp": 1.0}), "test"),
        )
        conn.commit()
        assert scraper._get_cached(conn, "MXRF11", ttl_hours=24) is None
        conn.close()

    def test_get_stale_cache(self, tmp_path):
        db = str(tmp_path / "test.db")
        conn = scraper._init_cache_db(db)
        old_time = (datetime.datetime.now() - datetime.timedelta(hours=48)).isoformat()
        conn.execute(
            "INSERT INTO fundamentals_cache (ticker, fetched_at, data_json, source) VALUES (?, ?, ?, ?)",
            ("MXRF11", old_time, json.dumps({"pvp": 1.0}), "test"),
        )
        conn.commit()
        stale = scraper._get_stale_cache(conn, "MXRF11")
        assert stale is not None
        assert stale["_source"] == "stale_cache"
        assert stale["pvp"] == 1.0
        conn.close()

    def test_get_stale_cache_missing(self, tmp_path):
        db = str(tmp_path / "test.db")
        conn = scraper._init_cache_db(db)
        assert scraper._get_stale_cache(conn, "ZZZZ11") is None
        conn.close()


class TestScrapeStatusInvest:
    def test_no_deps(self, monkeypatch):
        monkeypatch.setattr(scraper, "HAS_SCRAPER_DEPS", False)
        assert scraper._scrape_status_invest("MXRF11") is None

    def test_non_200_status(self, monkeypatch):
        monkeypatch.setattr(scraper, "HAS_SCRAPER_DEPS", True)
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_resp
        monkeypatch.setattr(scraper, "requests", mock_requests, raising=False)
        assert scraper._scrape_status_invest("MXRF11") is None

    def test_empty_indicators(self, monkeypatch):
        monkeypatch.setattr(scraper, "HAS_SCRAPER_DEPS", True)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body></body></html>"
        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_resp
        monkeypatch.setattr(scraper, "requests", mock_requests, raising=False)
        assert scraper._scrape_status_invest("MXRF11") is None

    def test_timeout_exception(self, monkeypatch):
        monkeypatch.setattr(scraper, "HAS_SCRAPER_DEPS", True)
        mock_requests = MagicMock()
        mock_requests.exceptions.Timeout = type("Timeout", (Exception,), {})
        mock_requests.exceptions.RequestException = type("RequestException", (Exception,), {})
        mock_requests.get.side_effect = mock_requests.exceptions.Timeout("timeout")
        monkeypatch.setattr(scraper, "requests", mock_requests, raising=False)
        assert scraper._scrape_status_invest("MXRF11") is None

    def test_request_exception(self, monkeypatch):
        monkeypatch.setattr(scraper, "HAS_SCRAPER_DEPS", True)
        mock_requests = MagicMock()
        mock_requests.exceptions.Timeout = type("Timeout", (Exception,), {})
        mock_requests.exceptions.RequestException = type("RequestException", (Exception,), {})
        mock_requests.get.side_effect = mock_requests.exceptions.RequestException("network")
        monkeypatch.setattr(scraper, "requests", mock_requests, raising=False)
        assert scraper._scrape_status_invest("MXRF11") is None

    def test_generic_exception(self, monkeypatch):
        monkeypatch.setattr(scraper, "HAS_SCRAPER_DEPS", True)
        mock_requests = MagicMock()
        mock_requests.exceptions.Timeout = type("Timeout", (Exception,), {})
        mock_requests.exceptions.RequestException = type("RequestException", (Exception,), {})
        mock_requests.get.side_effect = RuntimeError("unexpected")
        monkeypatch.setattr(scraper, "requests", mock_requests, raising=False)
        assert scraper._scrape_status_invest("MXRF11") is None

    def test_successful_scrape(self, monkeypatch):
        monkeypatch.setattr(scraper, "HAS_SCRAPER_DEPS", True)
        html = """
        <html><body>
        <div class="info">
            <h3 class="title">DIVIDEND YIELD</h3>
            <strong class="value">10,50%</strong>
        </div>
        <div class="info">
            <h3 class="title">P/VP</h3>
            <strong class="value">0,95</strong>
        </div>
        </body></html>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_resp
        mock_requests.exceptions.Timeout = type("Timeout", (Exception,), {})
        mock_requests.exceptions.RequestException = type("RequestException", (Exception,), {})
        monkeypatch.setattr(scraper, "requests", mock_requests, raising=False)
        result = scraper._scrape_status_invest("MXRF11")
        assert result is not None
        assert result["ticker"] == "MXRF11"
        assert result["_source"] == "scraper"


class TestFetchFundamentals:
    def test_returns_from_cache(self, tmp_path, monkeypatch):
        db = str(tmp_path / "test.db")
        conn = scraper._init_cache_db(db)
        scraper._save_cache(conn, "MXRF11", {"pvp": 0.95, "dividend_yield": 0.10})
        conn.close()

        monkeypatch.setattr(scraper, "_scrape_status_invest", lambda t: None)
        result = scraper.fetch_fundamentals("MXRF11", db_path=db)
        assert result["pvp"] == 0.95
        assert result["_source"] == "cache"

    def test_scrapes_when_no_cache(self, tmp_path, monkeypatch):
        db = str(tmp_path / "test.db")
        scraped = {"ticker": "HGLG11", "pvp": 1.05, "_source": "scraper"}
        monkeypatch.setattr(scraper, "_scrape_status_invest", lambda t: scraped)
        result = scraper.fetch_fundamentals("HGLG11", db_path=db)
        assert result["pvp"] == 1.05

    def test_fallback_to_stale_cache(self, tmp_path, monkeypatch):
        db = str(tmp_path / "test.db")
        conn = scraper._init_cache_db(db)
        old_time = (datetime.datetime.now() - datetime.timedelta(hours=48)).isoformat()
        conn.execute(
            "INSERT INTO fundamentals_cache (ticker, fetched_at, data_json, source) VALUES (?, ?, ?, ?)",
            ("MXRF11", old_time, json.dumps({"pvp": 0.90}), "test"),
        )
        conn.commit()
        conn.close()

        monkeypatch.setattr(scraper, "_scrape_status_invest", lambda t: None)
        result = scraper.fetch_fundamentals("MXRF11", db_path=db)
        assert result["pvp"] == 0.90
        assert result["_source"] == "stale_cache"

    def test_fallback_to_defaults(self, tmp_path, monkeypatch):
        db = str(tmp_path / "test.db")
        monkeypatch.setattr(scraper, "_scrape_status_invest", lambda t: None)
        result = scraper.fetch_fundamentals("ZZZZ11", db_path=db)
        assert result["_source"] == "default"
        assert result["dividend_yield"] == 0.08

    def test_force_refresh(self, tmp_path, monkeypatch):
        db = str(tmp_path / "test.db")
        conn = scraper._init_cache_db(db)
        scraper._save_cache(conn, "MXRF11", {"pvp": 0.80})
        conn.close()

        scraped = {"ticker": "MXRF11", "pvp": 1.10, "_source": "scraper"}
        monkeypatch.setattr(scraper, "_scrape_status_invest", lambda t: scraped)
        result = scraper.fetch_fundamentals("MXRF11", db_path=db, force_refresh=True)
        assert result["pvp"] == 1.10


class TestSaveManualFundamentals:
    def test_saves_and_retrieves(self, tmp_path):
        db = str(tmp_path / "test.db")
        scraper.save_manual_fundamentals("MXRF11", {"pvp": 0.88, "dividend_yield": 0.12}, db_path=db)
        result = scraper.fetch_fundamentals("MXRF11", db_path=db)
        assert result["pvp"] == 0.88
        assert result["dividend_yield"] == 0.12


class TestImportCSVFundamentals:
    def test_imports_csv(self, tmp_path):
        csv_file = tmp_path / "funds.csv"
        csv_file.write_text(
            "ticker,dividend_yield,pvp\nMXRF11,0.10,0.95\nHGLG11,0.08,1.05\n",
            encoding="utf-8",
        )
        db = str(tmp_path / "test.db")
        count = scraper.import_csv_fundamentals(str(csv_file), db_path=db)
        assert count == 2

        result = scraper.fetch_fundamentals("MXRF11", db_path=db)
        assert result["dividend_yield"] == 0.10

    def test_skips_empty_ticker(self, tmp_path):
        csv_file = tmp_path / "funds.csv"
        csv_file.write_text(
            "ticker,dividend_yield\n,0.10\nMXRF11,0.08\n",
            encoding="utf-8",
        )
        db = str(tmp_path / "test.db")
        count = scraper.import_csv_fundamentals(str(csv_file), db_path=db)
        assert count == 1

    def test_handles_invalid_values(self, tmp_path):
        csv_file = tmp_path / "funds.csv"
        csv_file.write_text(
            "ticker,dividend_yield,pvp\nMXRF11,abc,0.95\n",
            encoding="utf-8",
        )
        db = str(tmp_path / "test.db")
        count = scraper.import_csv_fundamentals(str(csv_file), db_path=db)
        assert count == 1


class TestGetCacheStatus:
    def test_status_structure(self, tmp_path):
        db = str(tmp_path / "test.db")
        conn = scraper._init_cache_db(db)
        scraper._save_cache(conn, "MXRF11", {"pvp": 1.0})
        conn.close()

        status = scraper.get_cache_status(["MXRF11", "ZZZZ11"], db_path=db)
        assert status["total"] == 2
        assert status["cached"] == 1
        assert status["missing"] == 1
        assert status["details"]["MXRF11"] == "valid"
        assert status["details"]["ZZZZ11"] == "missing"

    def test_stale_detection(self, tmp_path):
        db = str(tmp_path / "test.db")
        conn = scraper._init_cache_db(db)
        old_time = (datetime.datetime.now() - datetime.timedelta(hours=48)).isoformat()
        conn.execute(
            "INSERT INTO fundamentals_cache (ticker, fetched_at, data_json, source) VALUES (?, ?, ?, ?)",
            ("MXRF11", old_time, json.dumps({"pvp": 1.0}), "test"),
        )
        conn.commit()
        conn.close()

        status = scraper.get_cache_status(["MXRF11"], db_path=db)
        assert status["stale"] == 1
        assert "stale" in status["details"]["MXRF11"]
