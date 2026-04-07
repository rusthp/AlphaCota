"""Tests for core/macro_engine.py — BCB macro data with mocked API."""

import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import core.macro_engine as macro


class TestCachePath:
    def test_returns_csv_path(self):
        path = macro._cache_path("selic")
        assert path.endswith("selic.csv")
        assert "macro" in path


class TestLoadSaveMacroCSV:
    def test_roundtrip(self, tmp_path):
        with patch.object(macro, "_MACRO_DIR", str(tmp_path)):
            rows = [{"date": "2025-01-01", "value": "10.5"}, {"date": "2025-02-01", "value": "10.6"}]
            macro._save_macro_csv("test_series", rows, ["date", "value"])
            loaded = macro._load_macro_csv("test_series")
            assert len(loaded) == 2
            assert loaded[0]["date"] == "2025-01-01"
            assert loaded[1]["value"] == "10.6"

    def test_load_nonexistent_returns_empty(self, tmp_path):
        with patch.object(macro, "_MACRO_DIR", str(tmp_path)):
            result = macro._load_macro_csv("nonexistent")
            assert result == []


class TestFetchSgsMonthly:
    def test_returns_cached_data(self, tmp_path):
        with patch.object(macro, "_MACRO_DIR", str(tmp_path)):
            rows = [{"date": "2025-01-15", "value": "10.5"}, {"date": "2025-06-15", "value": "10.8"}]
            macro._save_macro_csv("selic_test", rows, ["date", "value"])

            result = macro._fetch_sgs_monthly(11, "selic_test", "2025-01-01", "2025-12-31")
            assert len(result) == 2

    def test_returns_empty_without_bcb(self, tmp_path):
        with patch.object(macro, "_MACRO_DIR", str(tmp_path)), patch.object(macro, "HAS_BCB", False):
            result = macro._fetch_sgs_monthly(11, "empty_test", "2025-01-01", "2025-12-31", force_refresh=True)
            assert result == []

    def test_force_refresh_skips_cache(self, tmp_path):
        with patch.object(macro, "_MACRO_DIR", str(tmp_path)), patch.object(macro, "HAS_BCB", False):
            rows = [{"date": "2025-01-15", "value": "10.5"}]
            macro._save_macro_csv("refresh_test", rows, ["date", "value"])
            result = macro._fetch_sgs_monthly(11, "refresh_test", "2025-01-01", "2025-12-31", force_refresh=True)
            assert result == []

    def test_bcb_api_exception_returns_empty(self, tmp_path):
        mock_sgs = MagicMock()
        mock_sgs.get.side_effect = Exception("API down")
        with (
            patch.object(macro, "_MACRO_DIR", str(tmp_path)),
            patch.object(macro, "HAS_BCB", True),
            patch.object(macro, "sgs", mock_sgs),
        ):
            result = macro._fetch_sgs_monthly(11, "error_test", "2025-01-01", "2025-12-31", force_refresh=True)
            assert result == []

    def test_bcb_api_success_saves_and_returns_rows(self, tmp_path):
        """BCB API returns a non-empty DataFrame: rows are saved and returned (lines 99-103)."""
        import pandas as pd

        idx = pd.to_datetime(["2025-01-15", "2025-02-15", "2025-03-15"])
        df = pd.DataFrame({"selic_bcb": [10.5, 10.6, 10.7]}, index=idx)

        mock_sgs = MagicMock()
        mock_sgs.get.return_value = df

        with (
            patch.object(macro, "_MACRO_DIR", str(tmp_path)),
            patch.object(macro, "HAS_BCB", True),
            patch.object(macro, "sgs", mock_sgs),
        ):
            result = macro._fetch_sgs_monthly(
                11, "selic_bcb", "2025-01-01", "2025-12-31", force_refresh=True
            )
        assert len(result) == 3
        assert result[0]["date"] == "2025-01-15"
        assert float(result[0]["value"]) == pytest.approx(10.5)

    def test_bcb_api_returns_empty_df_yields_empty(self, tmp_path):
        """BCB API returns an empty DataFrame: must return [] (line 99-100)."""
        import pandas as pd

        mock_sgs = MagicMock()
        mock_sgs.get.return_value = pd.DataFrame()

        with (
            patch.object(macro, "_MACRO_DIR", str(tmp_path)),
            patch.object(macro, "HAS_BCB", True),
            patch.object(macro, "sgs", mock_sgs),
        ):
            result = macro._fetch_sgs_monthly(
                11, "empty_df", "2025-01-01", "2025-12-31", force_refresh=True
            )
        assert result == []


class TestGetSelicHistory:
    def test_returns_fallback_when_empty(self):
        with patch.object(macro, "_fetch_sgs_monthly", return_value=[]):
            rows, source = macro.get_selic_history()
            assert rows == []
            assert source == "fallback"

    def test_returns_bcb_when_data(self):
        mock_data = [{"date": "2025-06-01", "value": "10.5"}]
        with patch.object(macro, "_fetch_sgs_monthly", return_value=mock_data):
            rows, source = macro.get_selic_history()
            assert rows == mock_data
            assert source == "bcb"


class TestGetCdiHistory:
    def test_returns_fallback_when_empty(self):
        with patch.object(macro, "_fetch_sgs_monthly", return_value=[]):
            rows, source = macro.get_cdi_history()
            assert source == "fallback"

    def test_returns_bcb_when_data(self):
        mock_data = [{"date": "2025-06-01", "value": "10.3"}]
        with patch.object(macro, "_fetch_sgs_monthly", return_value=mock_data):
            rows, source = macro.get_cdi_history()
            assert source == "bcb"


class TestGetIpcaHistory:
    def test_returns_fallback_when_empty(self):
        with patch.object(macro, "_fetch_sgs_monthly", return_value=[]):
            rows, source = macro.get_ipca_history()
            assert source == "fallback"

    def test_returns_bcb_when_data(self):
        mock_data = [{"date": "2025-06-01", "value": "0.5"}]
        with patch.object(macro, "_fetch_sgs_monthly", return_value=mock_data):
            rows, source = macro.get_ipca_history()
            assert source == "bcb"


class TestGetCurrentRiskFreeRate:
    def test_fallback_when_no_data(self):
        with patch.object(macro, "get_selic_history", return_value=([], "fallback")):
            rate, source = macro.get_current_risk_free_rate()
            assert source == "fallback"
            assert rate == pytest.approx(0.1075)

    def test_bcb_annualization(self):
        # SGS 11 returns daily Selic rate in % per day (~0.0567%/day ≈ 14.75%/year)
        daily_rows = [{"date": f"2025-{m:02d}-01", "value": "0.0567"} for m in range(1, 13)]
        with patch.object(macro, "get_selic_history", return_value=(daily_rows, "bcb")):
            rate, source = macro.get_current_risk_free_rate()
            assert source == "bcb"
            # (1 + 0.000567)^252 - 1 ≈ 0.154 (15.4% a.a.)
            assert 0.10 < rate < 0.25


class TestGetMacroSnapshot:
    def test_snapshot_structure_with_fallback(self):
        with (
            patch.object(macro, "get_current_risk_free_rate", return_value=(0.1075, "fallback")),
            patch.object(macro, "get_ipca_history", return_value=([], "fallback")),
        ):
            snap = macro.get_macro_snapshot()
            assert "selic_anual" in snap
            assert "cdi_anual" in snap
            assert "ipca_anual" in snap
            assert "premio_risco" in snap
            assert "data_ref" in snap

    def test_snapshot_with_bcb_data(self):
        ipca_rows = [{"date": f"2025-{m:02d}-01", "value": "0.4"} for m in range(1, 13)]
        with (
            patch.object(macro, "get_current_risk_free_rate", return_value=(0.1075, "bcb")),
            patch.object(macro, "get_ipca_history", return_value=(ipca_rows, "bcb")),
        ):
            snap = macro.get_macro_snapshot()
            assert snap["fonte_selic"] == "bcb"
            assert snap["fonte_ipca"] == "bcb"
            assert snap["ipca_anual"] > 0


class TestCalcularPremioRiscoFii:
    def test_excellent_spread(self):
        macro_data = {"cdi_anual": 10.65, "ipca_anual": 4.83}
        result = macro.calcular_premio_risco_fii(15.0, macro_data)
        assert result["spread_cdi_%"] == pytest.approx(4.35)
        assert "Excelente" in result["rating"]

    def test_good_spread(self):
        macro_data = {"cdi_anual": 10.65, "ipca_anual": 4.83}
        result = macro.calcular_premio_risco_fii(13.0, macro_data)
        assert "Bom" in result["rating"]

    def test_neutral_spread(self):
        macro_data = {"cdi_anual": 10.65, "ipca_anual": 4.83}
        result = macro.calcular_premio_risco_fii(11.0, macro_data)
        assert "Neutro" in result["rating"]

    def test_negative_spread(self):
        macro_data = {"cdi_anual": 10.65, "ipca_anual": 4.83}
        result = macro.calcular_premio_risco_fii(9.0, macro_data)
        assert "Negativo" in result["rating"]

    def test_auto_fetch_macro(self):
        with patch.object(macro, "get_macro_snapshot", return_value={"cdi_anual": 10.65, "ipca_anual": 4.83}):
            result = macro.calcular_premio_risco_fii(12.0)
            assert "spread_cdi_%" in result
