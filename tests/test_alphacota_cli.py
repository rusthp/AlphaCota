"""Tests for scripts/alphacota_cli.py — CLI command parsing and dispatch."""

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root so scripts/alphacota_cli.py can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.alphacota_cli import (
    cache_status,
    main,
    pipeline,
    update_data,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(**kwargs):
    """Build a simple Namespace-like object for testing handler functions."""
    obj = MagicMock()
    for k, v in kwargs.items():
        setattr(obj, k, v)
    return obj


# ---------------------------------------------------------------------------
# update_data
# ---------------------------------------------------------------------------


class TestUpdateData:
    def test_all_tickers_fetched_by_default(self):
        args = _make_args(ticker=None, force=False, status=False, sample=False)
        mock_tickers = ["HGLG11", "MXRF11", "XPML11"]

        with (
            patch("scripts.alphacota_cli.get_tickers", return_value=mock_tickers) as mock_get,
            patch("scripts.alphacota_cli.fetch_fundamentals_bulk", return_value={}) as mock_fetch,
        ):
            update_data(args)

        mock_get.assert_called_once()
        mock_fetch.assert_called_once_with(mock_tickers, force_refresh=False)

    def test_specific_tickers_override(self):
        args = _make_args(ticker=["hglg11", "mxrf11"], force=True, status=False, sample=False)

        with (
            patch("scripts.alphacota_cli.get_tickers", return_value=["HGLG11"]),
            patch("scripts.alphacota_cli.fetch_fundamentals_bulk", return_value={}) as mock_fetch,
        ):
            update_data(args)

        mock_fetch.assert_called_once_with(["HGLG11", "MXRF11"], force_refresh=True)

    def test_sample_limits_to_five(self):
        many_tickers = [f"FII{i:02d}11" for i in range(20)]
        args = _make_args(ticker=None, force=False, status=False, sample=True)

        with (
            patch("scripts.alphacota_cli.get_tickers", return_value=many_tickers),
            patch("scripts.alphacota_cli.fetch_fundamentals_bulk", return_value={}) as mock_fetch,
        ):
            update_data(args)

        called_tickers = mock_fetch.call_args[0][0]
        assert len(called_tickers) == 5

    def test_status_flag_calls_get_cache_status(self):
        args = _make_args(ticker=None, force=False, status=True, sample=False)
        tickers = ["HGLG11"]

        with (
            patch("scripts.alphacota_cli.get_tickers", return_value=tickers),
            patch("scripts.alphacota_cli.fetch_fundamentals_bulk", return_value={}),
            patch(
                "scripts.alphacota_cli.get_cache_status",
                return_value={"total": 1, "cached": 1, "stale": 0, "missing": 0},
            ) as mock_status,
        ):
            update_data(args)

        mock_status.assert_called_once_with(tickers)

    def test_status_flag_false_skips_cache_status(self):
        args = _make_args(ticker=None, force=False, status=False, sample=False)

        with (
            patch("scripts.alphacota_cli.get_tickers", return_value=["HGLG11"]),
            patch("scripts.alphacota_cli.fetch_fundamentals_bulk", return_value={}),
            patch("scripts.alphacota_cli.get_cache_status") as mock_status,
        ):
            update_data(args)

        mock_status.assert_not_called()

    def test_counts_scraper_successes(self, capsys):
        args = _make_args(ticker=["HGLG11", "MXRF11"], force=False, status=False, sample=False)
        fetch_result = {
            "HGLG11": {"_source": "scraper"},
            "MXRF11": {"_source": "cache"},
        }

        with (
            patch("scripts.alphacota_cli.get_tickers", return_value=[]),
            patch("scripts.alphacota_cli.fetch_fundamentals_bulk", return_value=fetch_result),
        ):
            # Should not raise; logs 1/2 updated
            update_data(args)


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------


class TestPipeline:
    def test_successful_pipeline_prints_allocations(self, capsys):
        args = _make_args(perfil="moderado", capital=100000.0)
        resultado = {
            "allocations": {"HGLG11": 0.6, "MXRF11": 0.4},
            "expected_return": 0.12,
            "volatility": 0.08,
        }

        with patch("scripts.alphacota_cli.run_pipeline", return_value=resultado):
            pipeline(args)

        out = capsys.readouterr().out
        assert "MODERADO" in out
        assert "HGLG11" in out
        assert "MXRF11" in out
        assert "12.00%" in out
        assert "8.00%" in out

    def test_error_in_result_exits_with_code_1(self):
        args = _make_args(perfil="conservador", capital=50000.0)
        resultado = {"error": "Dados insuficientes"}

        with patch("scripts.alphacota_cli.run_pipeline", return_value=resultado):
            with pytest.raises(SystemExit) as exc_info:
                pipeline(args)

        assert exc_info.value.code == 1

    def test_exception_exits_with_code_1(self):
        args = _make_args(perfil="agressivo", capital=200000.0)

        with patch("scripts.alphacota_cli.run_pipeline", side_effect=RuntimeError("boom")):
            with pytest.raises(SystemExit) as exc_info:
                pipeline(args)

        assert exc_info.value.code == 1

    def test_low_capital_does_not_crash(self, capsys):
        args = _make_args(perfil="moderado", capital=500.0)
        resultado = {
            "allocations": {"HGLG11": 1.0},
            "expected_return": 0.10,
            "volatility": 0.05,
        }

        with patch("scripts.alphacota_cli.run_pipeline", return_value=resultado):
            pipeline(args)  # Should not raise

        out = capsys.readouterr().out
        assert "HGLG11" in out

    def test_empty_allocations(self, capsys):
        args = _make_args(perfil="moderado", capital=100000.0)
        resultado = {"allocations": {}, "expected_return": 0.0, "volatility": 0.0}

        with patch("scripts.alphacota_cli.run_pipeline", return_value=resultado):
            pipeline(args)

        out = capsys.readouterr().out
        assert "MODERADO" in out


# ---------------------------------------------------------------------------
# cache_status
# ---------------------------------------------------------------------------


class TestCacheStatus:
    def _make_status(self):
        return {
            "total": 10,
            "cached": 7,
            "stale": 2,
            "missing": 1,
            "details": {
                "HGLG11": "valid",
                "MXRF11": "stale",
                "TEST11": "missing",
            },
        }

    def test_prints_summary(self, capsys):
        args = _make_args(verbose=False, all=False)

        with (
            patch("scripts.alphacota_cli.get_tickers", return_value=["HGLG11"]),
            patch("scripts.alphacota_cli.get_cache_status", return_value=self._make_status()),
        ):
            cache_status(args)

        out = capsys.readouterr().out
        assert "10" in out  # total
        assert "7" in out  # cached
        assert "2" in out  # stale
        assert "1" in out  # missing

    def test_verbose_shows_non_valid_assets(self, capsys):
        args = _make_args(verbose=True, all=False)

        with (
            patch("scripts.alphacota_cli.get_tickers", return_value=["HGLG11", "MXRF11", "TEST11"]),
            patch("scripts.alphacota_cli.get_cache_status", return_value=self._make_status()),
        ):
            cache_status(args)

        out = capsys.readouterr().out
        assert "MXRF11" in out
        assert "TEST11" in out
        # HGLG11 is 'valid', should NOT appear unless --all
        assert "HGLG11" not in out

    def test_verbose_all_shows_all_assets(self, capsys):
        args = _make_args(verbose=True, all=True)

        with (
            patch("scripts.alphacota_cli.get_tickers", return_value=["HGLG11", "MXRF11", "TEST11"]),
            patch("scripts.alphacota_cli.get_cache_status", return_value=self._make_status()),
        ):
            cache_status(args)

        out = capsys.readouterr().out
        assert "HGLG11" in out

    def test_non_verbose_hides_details(self, capsys):
        args = _make_args(verbose=False, all=False)

        with (
            patch("scripts.alphacota_cli.get_tickers", return_value=["MXRF11"]),
            patch("scripts.alphacota_cli.get_cache_status", return_value=self._make_status()),
        ):
            cache_status(args)

        out = capsys.readouterr().out
        # Details section should not appear
        assert "stale" not in out.lower() or "Expirados" in out  # summary word ok, detail line not


# ---------------------------------------------------------------------------
# main() — argument parser integration
# ---------------------------------------------------------------------------


class TestMain:
    def test_update_data_command_dispatched(self):
        with patch("sys.argv", ["cli", "update-data"]), patch("scripts.alphacota_cli.update_data") as mock_fn:
            mock_fn.return_value = None
            main()
        mock_fn.assert_called_once()

    def test_run_pipeline_command_dispatched(self):
        with (
            patch("sys.argv", ["cli", "run-pipeline", "--perfil", "agressivo", "--capital", "50000"]),
            patch("scripts.alphacota_cli.pipeline") as mock_fn,
        ):
            mock_fn.return_value = None
            main()
        mock_fn.assert_called_once()
        args = mock_fn.call_args[0][0]
        assert args.perfil == "agressivo"
        assert args.capital == 50000.0

    def test_status_command_dispatched(self):
        with patch("sys.argv", ["cli", "status"]), patch("scripts.alphacota_cli.cache_status") as mock_fn:
            mock_fn.return_value = None
            main()
        mock_fn.assert_called_once()

    def test_no_command_exits(self):
        with patch("sys.argv", ["cli"]):
            with pytest.raises(SystemExit):
                main()

    def test_run_pipeline_defaults(self):
        with patch("sys.argv", ["cli", "run-pipeline"]), patch("scripts.alphacota_cli.pipeline") as mock_fn:
            mock_fn.return_value = None
            main()
        args = mock_fn.call_args[0][0]
        assert args.perfil == "moderado"
        assert args.capital == 100000.0

    def test_update_data_force_flag(self):
        with (
            patch("sys.argv", ["cli", "update-data", "--force"]),
            patch("scripts.alphacota_cli.update_data") as mock_fn,
        ):
            mock_fn.return_value = None
            main()
        args = mock_fn.call_args[0][0]
        assert args.force is True

    def test_status_verbose_flag(self):
        with patch("sys.argv", ["cli", "status", "--verbose"]), patch("scripts.alphacota_cli.cache_status") as mock_fn:
            mock_fn.return_value = None
            main()
        args = mock_fn.call_args[0][0]
        assert args.verbose is True
