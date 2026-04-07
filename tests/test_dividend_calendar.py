"""Tests for data/dividend_calendar.py and data/fundamentals_scraper._enrich_with_history."""

from __future__ import annotations

import datetime
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import data.dividend_calendar as cal
import data.fundamentals_scraper as scraper


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_csv(tmp_path: Path, ticker: str, rows: list[tuple[str, float]]) -> Path:
    """Write a historical dividends CSV for a ticker and return the path."""
    content = "date,dividend\n" + "\n".join(f"{d},{v}" for d, v in rows)
    csv_path = tmp_path / f"{ticker}_dividends.csv"
    csv_path.write_text(content, encoding="utf-8")
    return csv_path


def _patch_dividends_dir(tmp_path: Path):
    """Context-manager-like patch: redirect _HISTORICAL_DIVIDENDS_DIR to tmp_path."""
    return patch.object(cal, "_HISTORICAL_DIVIDENDS_DIR", tmp_path)


def _patch_scraper_dividends_dir(tmp_path: Path):
    return patch.object(scraper, "_HISTORICAL_DIVIDENDS_DIR", tmp_path)


def _today_minus(months: int) -> str:
    """Return ISO date string `months` months before today."""
    d = datetime.date.today() - datetime.timedelta(days=months * 30)
    return d.isoformat()


def _today_minus_days(days: int) -> str:
    d = datetime.date.today() - datetime.timedelta(days=days)
    return d.isoformat()


# ---------------------------------------------------------------------------
# Tests: _enrich_with_history (fundamentals_scraper)
# ---------------------------------------------------------------------------


class TestEnrichWithHistory:
    def _base_result(self) -> dict:
        return {
            "ticker": "MXRF11",
            "dividend_consistency": 0.5,
            "revenue_growth_12m": 0.0,
            "earnings_growth_12m": 0.0,
        }

    def test_file_not_found_returns_defaults(self, tmp_path):
        result = self._base_result()
        with _patch_scraper_dividends_dir(tmp_path):
            enriched = scraper._enrich_with_history(result, "UNKNOWN11")
        assert enriched["dividend_consistency"] == 0.5
        assert enriched["revenue_growth_12m"] == 0.0
        assert enriched["earnings_growth_12m"] == 0.0

    def test_empty_csv_returns_defaults(self, tmp_path):
        csv_path = tmp_path / "MXRF11_dividends.csv"
        csv_path.write_text("date,dividend\n", encoding="utf-8")
        result = self._base_result()
        with _patch_scraper_dividends_dir(tmp_path):
            enriched = scraper._enrich_with_history(result, "MXRF11")
        assert enriched["dividend_consistency"] == 0.5
        assert enriched["revenue_growth_12m"] == 0.0
        assert enriched["earnings_growth_12m"] == 0.0

    def test_consistent_monthly_payments(self, tmp_path):
        # 24 months of consistent payments → consistency = 1.0
        rows = [(_today_minus_days(30 * i), 0.10) for i in range(1, 25)]
        _make_csv(tmp_path, "MXRF11", rows)
        result = self._base_result()
        with _patch_scraper_dividends_dir(tmp_path):
            enriched = scraper._enrich_with_history(result, "MXRF11")
        assert enriched["dividend_consistency"] == pytest.approx(1.0)

    def test_consistency_partial_payments(self, tmp_path):
        # 12 months with payments out of 24-month window → consistency = 12/24 = 0.5
        rows = [(_today_minus_days(30 * i), 0.10) for i in range(1, 13)]
        _make_csv(tmp_path, "MXRF11", rows)
        result = self._base_result()
        with _patch_scraper_dividends_dir(tmp_path):
            enriched = scraper._enrich_with_history(result, "MXRF11")
        assert enriched["dividend_consistency"] == pytest.approx(0.5)

    def test_revenue_growth_positive(self, tmp_path):
        # older average = 0.10, recent average = 0.12 → growth = 0.2
        older_rows = [(_today_minus_days(30 * i), 0.10) for i in range(8, 18)]
        recent_rows = [(_today_minus_days(30 * i), 0.12) for i in range(1, 7)]
        _make_csv(tmp_path, "MXRF11", older_rows + recent_rows)
        result = self._base_result()
        with _patch_scraper_dividends_dir(tmp_path):
            enriched = scraper._enrich_with_history(result, "MXRF11")
        assert enriched["revenue_growth_12m"] == pytest.approx(0.2, abs=0.01)
        assert enriched["earnings_growth_12m"] == enriched["revenue_growth_12m"]

    def test_revenue_growth_negative(self, tmp_path):
        # older average = 0.12, recent average = 0.09 → growth = -0.25
        older_rows = [(_today_minus_days(30 * i), 0.12) for i in range(8, 18)]
        recent_rows = [(_today_minus_days(30 * i), 0.09) for i in range(1, 7)]
        _make_csv(tmp_path, "MXRF11", older_rows + recent_rows)
        result = self._base_result()
        with _patch_scraper_dividends_dir(tmp_path):
            enriched = scraper._enrich_with_history(result, "MXRF11")
        assert enriched["revenue_growth_12m"] == pytest.approx(-0.25, abs=0.01)

    def test_revenue_growth_clamped_to_positive_one(self, tmp_path):
        # older=0.01, recent=1.00 → raw growth=99 → clamped to 1.0
        older_rows = [(_today_minus_days(30 * i), 0.01) for i in range(8, 18)]
        recent_rows = [(_today_minus_days(30 * i), 1.00) for i in range(1, 7)]
        _make_csv(tmp_path, "MXRF11", older_rows + recent_rows)
        result = self._base_result()
        with _patch_scraper_dividends_dir(tmp_path):
            enriched = scraper._enrich_with_history(result, "MXRF11")
        assert enriched["revenue_growth_12m"] == 1.0

    def test_revenue_growth_clamped_to_negative_one(self, tmp_path):
        # older=1.00, recent=0.001 → clamped to -1.0
        older_rows = [(_today_minus_days(30 * i), 1.00) for i in range(8, 18)]
        recent_rows = [(_today_minus_days(30 * i), 0.001) for i in range(1, 7)]
        _make_csv(tmp_path, "MXRF11", older_rows + recent_rows)
        result = self._base_result()
        with _patch_scraper_dividends_dir(tmp_path):
            enriched = scraper._enrich_with_history(result, "MXRF11")
        assert enriched["revenue_growth_12m"] == -1.0

    def test_zero_older_average_returns_zero_growth(self, tmp_path):
        # older period all zero → avoid div/zero → growth = 0.0
        older_rows = [(_today_minus_days(30 * i), 0.0) for i in range(8, 18)]
        recent_rows = [(_today_minus_days(30 * i), 0.10) for i in range(1, 7)]
        _make_csv(tmp_path, "MXRF11", older_rows + recent_rows)
        result = self._base_result()
        with _patch_scraper_dividends_dir(tmp_path):
            enriched = scraper._enrich_with_history(result, "MXRF11")
        assert enriched["revenue_growth_12m"] == 0.0

    def test_not_enough_data_returns_zero_growth(self, tmp_path):
        # Only 1 row, not enough to compute growth
        rows = [(_today_minus_days(10), 0.10)]
        _make_csv(tmp_path, "MXRF11", rows)
        result = self._base_result()
        with _patch_scraper_dividends_dir(tmp_path):
            enriched = scraper._enrich_with_history(result, "MXRF11")
        assert enriched["revenue_growth_12m"] == 0.0
        assert enriched["earnings_growth_12m"] == 0.0

    def test_corrupt_csv_returns_defaults(self, tmp_path):
        csv_path = tmp_path / "MXRF11_dividends.csv"
        csv_path.write_text("not,valid\ndata,here\n", encoding="utf-8")
        result = self._base_result()
        with _patch_scraper_dividends_dir(tmp_path):
            enriched = scraper._enrich_with_history(result, "MXRF11")
        # Should not raise — graceful defaults
        assert enriched["dividend_consistency"] == 0.5
        assert enriched["revenue_growth_12m"] == 0.0

    def test_result_dict_mutated_and_returned(self, tmp_path):
        """_enrich_with_history returns the same dict object (mutates in place)."""
        rows = [(_today_minus_days(30 * i), 0.10) for i in range(1, 7)]
        _make_csv(tmp_path, "MXRF11", rows)
        result = self._base_result()
        with _patch_scraper_dividends_dir(tmp_path):
            returned = scraper._enrich_with_history(result, "MXRF11")
        assert returned is result


# ---------------------------------------------------------------------------
# Tests: dividend_calendar._load_csv
# ---------------------------------------------------------------------------


class TestLoadCsv:
    def test_valid_csv(self, tmp_path):
        _make_csv(tmp_path, "MXRF11", [("2025-01-01", 0.10), ("2025-02-01", 0.11)])
        with _patch_dividends_dir(tmp_path):
            rows = cal._load_csv("MXRF11")
        assert len(rows) == 2
        assert rows[0][1] == pytest.approx(0.10)

    def test_csv_not_found(self, tmp_path):
        with _patch_dividends_dir(tmp_path):
            rows = cal._load_csv("UNKNOWN11")
        assert rows == []

    def test_empty_csv(self, tmp_path):
        csv_path = tmp_path / "EMPTY11_dividends.csv"
        csv_path.write_text("date,dividend\n", encoding="utf-8")
        with _patch_dividends_dir(tmp_path):
            rows = cal._load_csv("EMPTY11")
        assert rows == []

    def test_zero_dividends_filtered(self, tmp_path):
        _make_csv(tmp_path, "MXRF11", [("2025-01-01", 0.0), ("2025-02-01", 0.10)])
        with _patch_dividends_dir(tmp_path):
            rows = cal._load_csv("MXRF11")
        assert len(rows) == 1
        assert rows[0][1] == pytest.approx(0.10)

    def test_sorted_by_date(self, tmp_path):
        _make_csv(tmp_path, "MXRF11", [("2025-03-01", 0.12), ("2025-01-01", 0.10), ("2025-02-01", 0.11)])
        with _patch_dividends_dir(tmp_path):
            rows = cal._load_csv("MXRF11")
        dates = [r[0] for r in rows]
        assert dates == sorted(dates)

    def test_ticker_sa_suffix_stripped(self, tmp_path):
        _make_csv(tmp_path, "MXRF11", [("2025-01-01", 0.10)])
        with _patch_dividends_dir(tmp_path):
            rows = cal._load_csv("MXRF11.SA")
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Tests: get_historical_events
# ---------------------------------------------------------------------------


class TestGetHistoricalEvents:
    def test_returns_events_within_months(self, tmp_path):
        today = datetime.date.today()
        recent = (today - datetime.timedelta(days=30)).isoformat()
        old = (today - datetime.timedelta(days=800)).isoformat()
        _make_csv(tmp_path, "MXRF11", [(recent, 0.10), (old, 0.08)])
        with _patch_dividends_dir(tmp_path):
            events = cal.get_historical_events("MXRF11", months=24)
        assert len(events) == 1
        assert events[0]["valor_por_cota"] == pytest.approx(0.10)

    def test_event_structure(self, tmp_path):
        today = datetime.date.today()
        ex = (today - datetime.timedelta(days=30)).isoformat()
        _make_csv(tmp_path, "MXRF11", [(ex, 0.10)])
        with _patch_dividends_dir(tmp_path):
            events = cal.get_historical_events("MXRF11", months=24)
        assert len(events) == 1
        e = events[0]
        assert e["ticker"] == "MXRF11"
        assert e["fonte"] == "historico"
        assert e["confirmado"] is True
        assert e["tipo"] == "rendimento"
        # pay_date = ex_date + 14 days
        ex_date = datetime.date.fromisoformat(e["ex_date"])
        pay_date = datetime.date.fromisoformat(e["pay_date"])
        assert (pay_date - ex_date).days == 14

    def test_sorted_by_ex_date(self, tmp_path):
        today = datetime.date.today()
        rows = [
            ((today - datetime.timedelta(days=60)).isoformat(), 0.10),
            ((today - datetime.timedelta(days=30)).isoformat(), 0.11),
            ((today - datetime.timedelta(days=90)).isoformat(), 0.09),
        ]
        _make_csv(tmp_path, "MXRF11", rows)
        with _patch_dividends_dir(tmp_path):
            events = cal.get_historical_events("MXRF11", months=24)
        dates = [e["ex_date"] for e in events]
        assert dates == sorted(dates)

    def test_missing_csv_returns_empty(self, tmp_path):
        with _patch_dividends_dir(tmp_path):
            events = cal.get_historical_events("MISSING11", months=24)
        assert events == []

    def test_setor_populated(self, tmp_path):
        today = datetime.date.today()
        ex = (today - datetime.timedelta(days=10)).isoformat()
        _make_csv(tmp_path, "MXRF11", [(ex, 0.10)])
        with _patch_dividends_dir(tmp_path):
            with patch.object(cal, "_get_sector_map", return_value={"MXRF11": "Papel (CRI)"}):
                events = cal.get_historical_events("MXRF11", months=24)
        assert events[0]["setor"] == "Papel (CRI)"

    def test_unknown_ticker_setor_fallback(self, tmp_path):
        today = datetime.date.today()
        ex = (today - datetime.timedelta(days=10)).isoformat()
        _make_csv(tmp_path, "UNKNOWN11", [(ex, 0.10)])
        with _patch_dividends_dir(tmp_path):
            with patch.object(cal, "_get_sector_map", return_value={}):
                events = cal.get_historical_events("UNKNOWN11", months=24)
        assert events[0]["setor"] == "Outros"


# ---------------------------------------------------------------------------
# Tests: estimate_next_events
# ---------------------------------------------------------------------------


class TestEstimateNextEvents:
    def _recent_rows(self, n: int = 6, valor: float = 0.10) -> list[tuple[str, float]]:
        today = datetime.date.today()
        return [((today - datetime.timedelta(days=20 * i)).isoformat(), valor) for i in range(1, n + 1)]

    def test_returns_correct_count(self, tmp_path):
        _make_csv(tmp_path, "MXRF11", self._recent_rows())
        with _patch_dividends_dir(tmp_path):
            events = cal.estimate_next_events("MXRF11", months_ahead=3)
        assert len(events) == 3

    def test_events_are_future(self, tmp_path):
        _make_csv(tmp_path, "MXRF11", self._recent_rows())
        today = datetime.date.today()
        with _patch_dividends_dir(tmp_path):
            events = cal.estimate_next_events("MXRF11", months_ahead=3)
        for e in events:
            assert datetime.date.fromisoformat(e["pay_date"]) > today

    def test_event_structure(self, tmp_path):
        _make_csv(tmp_path, "MXRF11", self._recent_rows())
        with _patch_dividends_dir(tmp_path):
            events = cal.estimate_next_events("MXRF11", months_ahead=1)
        e = events[0]
        assert e["ticker"] == "MXRF11"
        assert e["fonte"] == "estimativa"
        assert e["confirmado"] is False
        assert e["tipo"] == "rendimento"

    def test_average_valor_used(self, tmp_path):
        rows = self._recent_rows(valor=0.10)
        _make_csv(tmp_path, "MXRF11", rows)
        with _patch_dividends_dir(tmp_path):
            events = cal.estimate_next_events("MXRF11", months_ahead=2)
        for e in events:
            assert e["valor_por_cota"] == pytest.approx(0.10, abs=0.001)

    def test_missing_csv_returns_empty(self, tmp_path):
        with _patch_dividends_dir(tmp_path):
            events = cal.estimate_next_events("MISSING11", months_ahead=3)
        assert events == []

    def test_no_recent_data_falls_back_to_12m(self, tmp_path):
        # All data older than 6 months but within 12 months
        today = datetime.date.today()
        old_rows = [
            ((today - datetime.timedelta(days=7 * 30 + i * 30)).isoformat(), 0.10)
            for i in range(6)
        ]
        _make_csv(tmp_path, "MXRF11", old_rows)
        with _patch_dividends_dir(tmp_path):
            events = cal.estimate_next_events("MXRF11", months_ahead=2)
        # Should still return estimates using the fallback 12m window
        assert len(events) == 2

    def test_sorted_by_ex_date(self, tmp_path):
        _make_csv(tmp_path, "MXRF11", self._recent_rows())
        with _patch_dividends_dir(tmp_path):
            events = cal.estimate_next_events("MXRF11", months_ahead=4)
        dates = [e["ex_date"] for e in events]
        assert dates == sorted(dates)

    def test_sa_suffix_stripped(self, tmp_path):
        _make_csv(tmp_path, "MXRF11", self._recent_rows())
        with _patch_dividends_dir(tmp_path):
            events = cal.estimate_next_events("MXRF11.SA", months_ahead=2)
        assert len(events) == 2
        assert events[0]["ticker"] == "MXRF11"


# ---------------------------------------------------------------------------
# Tests: get_calendar_month
# ---------------------------------------------------------------------------


class TestGetCalendarMonth:
    def test_filters_to_correct_month(self, tmp_path):
        today = datetime.date.today()
        # Event with pay_date falling in a specific past month
        target_pay = datetime.date(today.year - 1, 3, 15)
        ex = target_pay - datetime.timedelta(days=14)
        _make_csv(tmp_path, "MXRF11", [(ex.isoformat(), 0.10)])
        with _patch_dividends_dir(tmp_path):
            events = cal.get_calendar_month(today.year - 1, 3, ["MXRF11"])
        assert len(events) == 1
        assert events[0]["ticker"] == "MXRF11"

    def test_empty_month(self, tmp_path):
        with _patch_dividends_dir(tmp_path):
            events = cal.get_calendar_month(2000, 1, ["MXRF11"])
        assert events == []

    def test_multiple_tickers(self, tmp_path):
        today = datetime.date.today()
        target_pay = datetime.date(today.year - 1, 6, 15)
        ex = target_pay - datetime.timedelta(days=14)
        _make_csv(tmp_path, "MXRF11", [(ex.isoformat(), 0.10)])
        _make_csv(tmp_path, "XPML11", [(ex.isoformat(), 0.15)])
        with _patch_dividends_dir(tmp_path):
            events = cal.get_calendar_month(today.year - 1, 6, ["MXRF11", "XPML11"])
        tickers = {e["ticker"] for e in events}
        assert "MXRF11" in tickers
        assert "XPML11" in tickers

    def test_sorted_by_pay_date(self, tmp_path):
        today = datetime.date.today()
        yr = today.year - 1
        rows = [
            (datetime.date(yr, 4, 20).isoformat(), 0.10),
            (datetime.date(yr, 4, 5).isoformat(), 0.11),
        ]
        _make_csv(tmp_path, "MXRF11", rows)
        with _patch_dividends_dir(tmp_path):
            events = cal.get_calendar_month(yr, 5, ["MXRF11"])
        # pay_dates should be sorted ascending
        dates = [e["pay_date"] for e in events]
        assert dates == sorted(dates)

    def test_no_duplicate_ex_date_per_ticker(self, tmp_path):
        today = datetime.date.today()
        ex = (today - datetime.timedelta(days=30)).isoformat()
        _make_csv(tmp_path, "MXRF11", [(ex, 0.10)])
        with _patch_dividends_dir(tmp_path):
            events = cal.get_calendar_month(
                datetime.date.today().year,
                datetime.date.today().month,
                ["MXRF11"],
            )
        # No duplicates for the same ex_date/ticker
        keys = [f"{e['ticker']}:{e['ex_date']}" for e in events]
        assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# Tests: get_calendar_year
# ---------------------------------------------------------------------------


class TestGetCalendarYear:
    def test_returns_dict_with_month_keys(self, tmp_path):
        today = datetime.date.today()
        yr = today.year - 1
        ex1 = datetime.date(yr, 1, 10).isoformat()
        ex2 = datetime.date(yr, 6, 10).isoformat()
        _make_csv(tmp_path, "MXRF11", [(ex1, 0.10), (ex2, 0.11)])
        with _patch_dividends_dir(tmp_path):
            result = cal.get_calendar_year(yr, ["MXRF11"])
        # Keys should be "YYYY-MM" format
        for key in result:
            assert len(key) == 7
            assert key[:4] == str(yr)

    def test_empty_year_returns_empty_dict(self, tmp_path):
        with _patch_dividends_dir(tmp_path):
            result = cal.get_calendar_year(1990, ["MXRF11"])
        assert result == {}

    def test_months_with_no_events_excluded(self, tmp_path):
        today = datetime.date.today()
        yr = today.year - 1
        # Only events in January
        ex = datetime.date(yr, 1, 10).isoformat()
        _make_csv(tmp_path, "MXRF11", [(ex, 0.10)])
        with _patch_dividends_dir(tmp_path):
            result = cal.get_calendar_year(yr, ["MXRF11"])
        # Only January's pay_date month should be in result
        assert all(v != [] for v in result.values())


# ---------------------------------------------------------------------------
# Tests: get_portfolio_income
# ---------------------------------------------------------------------------


class TestGetPortfolioIncome:
    def _recent_rows(self, valor: float = 0.10, n: int = 8) -> list[tuple[str, float]]:
        today = datetime.date.today()
        return [((today - datetime.timedelta(days=20 * i)).isoformat(), valor) for i in range(1, n + 1)]

    def test_returns_list_of_monthly_dicts(self, tmp_path):
        _make_csv(tmp_path, "MXRF11", self._recent_rows())
        with _patch_dividends_dir(tmp_path):
            result = cal.get_portfolio_income({"MXRF11": 100}, months_ahead=3)
        assert isinstance(result, list)
        for item in result:
            assert "month" in item
            assert "total_renda" in item
            assert "events" in item

    def test_month_key_format(self, tmp_path):
        _make_csv(tmp_path, "MXRF11", self._recent_rows())
        with _patch_dividends_dir(tmp_path):
            result = cal.get_portfolio_income({"MXRF11": 100}, months_ahead=3)
        for item in result:
            assert len(item["month"]) == 7
            assert "-" in item["month"]

    def test_total_renda_calculation(self, tmp_path):
        # 100 cotas x 0.10/cota = 10.00 per month
        _make_csv(tmp_path, "MXRF11", self._recent_rows(valor=0.10))
        with _patch_dividends_dir(tmp_path):
            result = cal.get_portfolio_income({"MXRF11": 100}, months_ahead=3)
        for item in result:
            if item["events"]:
                assert item["total_renda"] == pytest.approx(10.0, abs=0.5)

    def test_multiple_tickers_income_aggregated(self, tmp_path):
        _make_csv(tmp_path, "MXRF11", self._recent_rows(valor=0.10))
        _make_csv(tmp_path, "XPML11", self._recent_rows(valor=0.20))
        with _patch_dividends_dir(tmp_path):
            result = cal.get_portfolio_income({"MXRF11": 100, "XPML11": 50}, months_ahead=3)
        # MXRF11: 100*0.10=10, XPML11: 50*0.20=10 → total=20 (approx)
        for item in result:
            tickers_in_month = {e["ticker"] for e in item["events"]}
            if "MXRF11" in tickers_in_month and "XPML11" in tickers_in_month:
                assert item["total_renda"] == pytest.approx(20.0, abs=1.0)

    def test_past_events_excluded(self, tmp_path):
        _make_csv(tmp_path, "MXRF11", self._recent_rows())
        with _patch_dividends_dir(tmp_path):
            result = cal.get_portfolio_income({"MXRF11": 100}, months_ahead=3)
        today = datetime.date.today()
        for item in result:
            for e in item["events"]:
                pay = datetime.date.fromisoformat(e["pay_date"])
                assert pay > today

    def test_sorted_by_month(self, tmp_path):
        _make_csv(tmp_path, "MXRF11", self._recent_rows())
        with _patch_dividends_dir(tmp_path):
            result = cal.get_portfolio_income({"MXRF11": 100}, months_ahead=6)
        months = [item["month"] for item in result]
        assert months == sorted(months)

    def test_events_include_renda_total_field(self, tmp_path):
        _make_csv(tmp_path, "MXRF11", self._recent_rows())
        with _patch_dividends_dir(tmp_path):
            result = cal.get_portfolio_income({"MXRF11": 100}, months_ahead=2)
        for item in result:
            for e in item["events"]:
                assert "renda_total" in e
                assert "quantidade" in e

    def test_zero_quantity_gives_zero_renda(self, tmp_path):
        _make_csv(tmp_path, "MXRF11", self._recent_rows())
        with _patch_dividends_dir(tmp_path):
            result = cal.get_portfolio_income({"MXRF11": 0}, months_ahead=2)
        for item in result:
            assert item["total_renda"] == pytest.approx(0.0)

    def test_empty_tickers_returns_empty(self, tmp_path):
        with _patch_dividends_dir(tmp_path):
            result = cal.get_portfolio_income({}, months_ahead=3)
        assert result == []

    def test_missing_csv_returns_empty(self, tmp_path):
        with _patch_dividends_dir(tmp_path):
            result = cal.get_portfolio_income({"MISSING11": 100}, months_ahead=3)
        assert result == []


# ---------------------------------------------------------------------------
# Tests: _make_event helper
# ---------------------------------------------------------------------------


class TestMakeEvent:
    def test_structure(self):
        ex = datetime.date(2026, 3, 14)
        pay = datetime.date(2026, 3, 28)
        e = cal._make_event("MXRF11", ex, pay, 0.10, "historico", True, "Papel (CRI)")
        assert e["ticker"] == "MXRF11"
        assert e["ex_date"] == "2026-03-14"
        assert e["pay_date"] == "2026-03-28"
        assert e["valor_por_cota"] == pytest.approx(0.10)
        assert e["tipo"] == "rendimento"
        assert e["fonte"] == "historico"
        assert e["confirmado"] is True
        assert e["setor"] == "Papel (CRI)"

    def test_valor_rounded_to_6_decimals(self):
        ex = datetime.date(2026, 1, 1)
        pay = datetime.date(2026, 1, 15)
        e = cal._make_event("X", ex, pay, 0.123456789, "test", False, "Outros")
        assert len(str(e["valor_por_cota"]).split(".")[-1]) <= 6


# ---------------------------------------------------------------------------
# Tests: _get_sector_map (integration via universe)
# ---------------------------------------------------------------------------


class TestGetSectorMap:
    def test_returns_dict(self):
        result = cal._get_sector_map()
        assert isinstance(result, dict)

    def test_known_ticker_has_setor(self):
        sector_map = cal._get_sector_map()
        # MXRF11 is in universe.py
        assert "MXRF11" in sector_map
        assert isinstance(sector_map["MXRF11"], str)

    def test_fails_gracefully_when_universe_unavailable(self):
        with patch("data.universe.get_sector_map", side_effect=ImportError("no module")):
            result = cal._get_sector_map()
        # Should return empty dict without raising
        assert isinstance(result, dict)
