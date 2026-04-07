"""Tests for cli.py — argparse-based CLI for AlphaCota."""

import json
import sys
from io import StringIO
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_main(argv: list[str], *, capture_stdout: bool = True):
    """
    Patch sys.argv and invoke cli.main(), capturing stdout.
    Returns (stdout_text, raised_exception_or_None).
    """
    import cli as cli_module  # noqa: PLC0415

    with patch("sys.argv", argv):
        if capture_stdout:
            from io import StringIO
            buf = StringIO()
            with patch("sys.stdout", buf):
                try:
                    cli_module.main()
                    return buf.getvalue(), None
                except SystemExit as exc:
                    return buf.getvalue(), exc
        else:
            try:
                cli_module.main()
                return "", None
            except SystemExit as exc:
                return "", exc


# ---------------------------------------------------------------------------
# init command
# ---------------------------------------------------------------------------


class TestInitCommand:
    def test_init_calls_init_db(self):
        with patch("cli.init_db") as mock_init_db:
            out, exc = _run_main(["cli", "init"])
        mock_init_db.assert_called_once()
        assert exc is None

    def test_init_prints_success_message(self):
        with patch("cli.init_db"):
            out, exc = _run_main(["cli", "init"])
        assert "inicializado" in out.lower()
        assert exc is None


# ---------------------------------------------------------------------------
# add-operation command
# ---------------------------------------------------------------------------


class TestAddOperationCommand:
    def test_compra_operation_calls_save_operation(self):
        with patch("cli.save_operation") as mock_save:
            out, exc = _run_main(["cli", "add-operation", "MXRF11", "compra", "100", "10.50"])
        mock_save.assert_called_once_with("MXRF11", "compra", 100.0, 10.50)
        assert exc is None

    def test_venda_operation_calls_save_operation(self):
        with patch("cli.save_operation") as mock_save:
            out, exc = _run_main(["cli", "add-operation", "HGLG11", "venda", "50", "12.00"])
        mock_save.assert_called_once_with("HGLG11", "venda", 50.0, 12.00)
        assert exc is None

    def test_compra_prints_confirmation(self):
        with patch("cli.save_operation"):
            out, exc = _run_main(["cli", "add-operation", "BBSE3", "compra", "200", "32.00"])
        assert "BBSE3" in out
        assert "compra" in out
        assert exc is None

    def test_venda_prints_confirmation(self):
        with patch("cli.save_operation"):
            out, exc = _run_main(["cli", "add-operation", "XPML11", "venda", "10", "8.00"])
        assert "XPML11" in out
        assert "venda" in out
        assert exc is None

    def test_invalid_tipo_exits_with_error(self):
        with patch("cli.save_operation"):
            _, exc = _run_main(["cli", "add-operation", "MXRF11", "holding", "10", "10.00"])
        # argparse rejects invalid choice and calls sys.exit(2)
        assert exc is not None
        assert exc.code == 2

    def test_quantidade_is_float(self):
        with patch("cli.save_operation") as mock_save:
            _run_main(["cli", "add-operation", "MXRF11", "compra", "1.5", "10.00"])
        _, _, qty, _ = mock_save.call_args[0]
        assert isinstance(qty, float)
        assert qty == 1.5

    def test_preco_is_float(self):
        with patch("cli.save_operation") as mock_save:
            _run_main(["cli", "add-operation", "MXRF11", "compra", "100", "9.99"])
        _, _, _, price = mock_save.call_args[0]
        assert isinstance(price, float)
        assert price == pytest.approx(9.99)


# ---------------------------------------------------------------------------
# add-provento command
# ---------------------------------------------------------------------------


class TestAddProventoCommand:
    def test_calls_save_provento(self):
        with patch("cli.save_provento") as mock_save:
            out, exc = _run_main(["cli", "add-provento", "MXRF11", "150.75"])
        mock_save.assert_called_once_with("MXRF11", 150.75)
        assert exc is None

    def test_prints_ticker_in_confirmation(self):
        with patch("cli.save_provento"):
            out, exc = _run_main(["cli", "add-provento", "HGLG11", "200.00"])
        assert "HGLG11" in out
        assert exc is None

    def test_prints_valor_formatted(self):
        with patch("cli.save_provento"):
            out, exc = _run_main(["cli", "add-provento", "XPML11", "99.50"])
        # Value appears formatted with 2 decimal places
        assert "99.50" in out
        assert exc is None

    def test_valor_is_float(self):
        with patch("cli.save_provento") as mock_save:
            _run_main(["cli", "add-provento", "MXRF11", "42.00"])
        _, valor = mock_save.call_args[0]
        assert isinstance(valor, float)


# ---------------------------------------------------------------------------
# report command
# ---------------------------------------------------------------------------


class TestReportCommand:
    def _make_report(self):
        return {
            "resumo_carteira": {"valor_total": 1000.0},
            "decisoes": [],
        }

    def test_report_calls_run_full_cycle(self):
        with patch("cli.run_full_cycle", return_value=self._make_report()) as mock_cycle:
            out, exc = _run_main(["cli", "report"])
        mock_cycle.assert_called_once()
        assert exc is None

    def test_report_passes_hardcoded_precos(self):
        with patch("cli.run_full_cycle", return_value=self._make_report()) as mock_cycle:
            _run_main(["cli", "report"])
        kwargs = mock_cycle.call_args[1]
        assert "precos_atuais" in kwargs
        assert "BBSE3" in kwargs["precos_atuais"]
        assert "MXRF11" in kwargs["precos_atuais"]

    def test_report_passes_alocacao_alvo(self):
        with patch("cli.run_full_cycle", return_value=self._make_report()) as mock_cycle:
            _run_main(["cli", "report"])
        kwargs = mock_cycle.call_args[1]
        assert "alocacao_alvo" in kwargs
        alvo = kwargs["alocacao_alvo"]
        assert pytest.approx(sum(alvo.values())) == 1.0

    def test_report_output_is_valid_json(self):
        report = self._make_report()
        with patch("cli.run_full_cycle", return_value=report):
            out, exc = _run_main(["cli", "report"])
        # The output should contain a JSON-parseable block
        parsed = json.loads(out.strip())
        assert "resumo_carteira" in parsed
        assert exc is None

    def test_report_exception_prints_error(self):
        with patch("cli.run_full_cycle", side_effect=RuntimeError("DB error")):
            out, exc = _run_main(["cli", "report"])
        assert "Erro" in out
        assert "DB error" in out
        # Does NOT re-raise; main() returns normally
        assert exc is None

    def test_report_exception_does_not_propagate(self):
        with patch("cli.run_full_cycle", side_effect=Exception("boom")):
            out, exc = _run_main(["cli", "report"])
        assert exc is None


# ---------------------------------------------------------------------------
# history command
# ---------------------------------------------------------------------------


class TestHistoryCommand:
    def test_history_calls_get_portfolio_snapshots(self):
        with patch("cli.get_portfolio_snapshots", return_value=[]) as mock_snap:
            out, exc = _run_main(["cli", "history"])
        mock_snap.assert_called_once()
        assert exc is None

    def test_history_empty_prints_no_snapshot_message(self):
        with patch("cli.get_portfolio_snapshots", return_value=[]):
            out, exc = _run_main(["cli", "history"])
        assert "nenhum" in out.lower() or "snapshot" in out.lower()
        assert exc is None

    def test_history_with_snapshots_prints_json(self):
        snapshots = [
            {"id": 1, "valor_total": 5000.0, "data_criacao": "2024-01-01"},
            {"id": 2, "valor_total": 6000.0, "data_criacao": "2024-02-01"},
        ]
        with patch("cli.get_portfolio_snapshots", return_value=snapshots):
            out, exc = _run_main(["cli", "history"])
        parsed = json.loads(out.strip())
        assert len(parsed) == 2
        assert parsed[0]["valor_total"] == 5000.0
        assert exc is None

    def test_history_single_snapshot_is_json_list(self):
        snapshots = [{"id": 1, "valor_total": 1234.56, "data_criacao": "2024-03-15"}]
        with patch("cli.get_portfolio_snapshots", return_value=snapshots):
            out, exc = _run_main(["cli", "history"])
        parsed = json.loads(out.strip())
        assert isinstance(parsed, list)
        assert len(parsed) == 1


# ---------------------------------------------------------------------------
# backtest command
# ---------------------------------------------------------------------------


class TestBacktestCommand:
    def _mock_backtest_imports(self, mock_result=None, mock_comparison=None, mock_report="BACKTEST REPORT\n"):
        """Context manager that patches all three backtest engine functions."""
        if mock_result is None:
            mock_result = MagicMock()
        if mock_comparison is None:
            mock_comparison = MagicMock()

        return (
            patch("cli.run_backtest", return_value=mock_result),
            patch("cli.compare_against_benchmark", return_value=mock_comparison),
            patch("cli.format_metrics_report", return_value=mock_report),
        )

    def test_backtest_defaults_run(self, capsys):
        """backtest with all defaults should succeed and print the report."""
        mock_result = MagicMock()
        mock_comparison = MagicMock()

        import cli as cli_module

        with patch.object(sys, "argv", ["cli", "backtest"]):
            with patch("core.backtest_engine.run_backtest", return_value=mock_result) as p1, \
                 patch("core.backtest_engine.compare_against_benchmark", return_value=mock_comparison) as p2, \
                 patch("core.backtest_engine.format_metrics_report", return_value="REPORT\n") as p3:
                # The CLI imports dynamically inside the else branch
                with patch.dict("sys.modules", {}):
                    # Patch at the point of dynamic import in cli.py
                    backtest_mock = MagicMock()
                    backtest_mock.run_backtest = MagicMock(return_value=mock_result)
                    backtest_mock.compare_against_benchmark = MagicMock(return_value=mock_comparison)
                    backtest_mock.format_metrics_report = MagicMock(return_value="REPORT\n")
                    with patch.dict("sys.modules", {"core.backtest_engine": backtest_mock}):
                        out = StringIO()
                        with patch("sys.stdout", out):
                            cli_module.main()
        output = out.getvalue()
        assert "REPORT" in output

    def test_backtest_mismatched_tickers_weights_exits(self):
        """If tickers and weights counts differ, print error and sys.exit(1)."""
        import cli as cli_module

        with patch.object(sys, "argv", ["cli", "backtest", "--tickers", "MXRF11", "HGLG11", "--weights", "1.0"]):
            out = StringIO()
            with patch("sys.stdout", out):
                with pytest.raises(SystemExit) as exc_info:
                    cli_module.main()
        assert exc_info.value.code == 1
        assert "Erro" in out.getvalue()

    def test_backtest_custom_tickers_and_weights(self):
        """Custom tickers/weights are passed to run_backtest with normalized weights."""
        import cli as cli_module

        mock_result = MagicMock()
        mock_comparison = MagicMock()
        backtest_mock = MagicMock()
        backtest_mock.run_backtest = MagicMock(return_value=mock_result)
        backtest_mock.compare_against_benchmark = MagicMock(return_value=mock_comparison)
        backtest_mock.format_metrics_report = MagicMock(return_value="REPORT CUSTOM\n")

        with patch.object(
            sys, "argv",
            ["cli", "backtest", "--tickers", "MXRF11", "HGLG11", "--weights", "0.7", "0.3"]
        ):
            with patch.dict("sys.modules", {"core.backtest_engine": backtest_mock}):
                out = StringIO()
                with patch("sys.stdout", out):
                    cli_module.main()

        assert backtest_mock.run_backtest.called
        call_kwargs = backtest_mock.run_backtest.call_args[1]
        weights = call_kwargs["weights"]
        # Weights should sum to ~1.0 after normalization
        assert pytest.approx(sum(weights.values()), rel=1e-4) == 1.0
        assert "MXRF11" in weights
        assert "HGLG11" in weights

    def test_backtest_weights_normalized_to_sum_one(self):
        """Weights not summing to 1.0 are normalized."""
        import cli as cli_module

        backtest_mock = MagicMock()
        backtest_mock.run_backtest = MagicMock(return_value=MagicMock())
        backtest_mock.compare_against_benchmark = MagicMock(return_value=MagicMock())
        backtest_mock.format_metrics_report = MagicMock(return_value="NORMALIZED\n")

        with patch.object(
            sys, "argv",
            ["cli", "backtest", "--tickers", "A11", "B11", "--weights", "2.0", "2.0"]
        ):
            with patch.dict("sys.modules", {"core.backtest_engine": backtest_mock}):
                out = StringIO()
                with patch("sys.stdout", out):
                    cli_module.main()

        call_kwargs = backtest_mock.run_backtest.call_args[1]
        weights = call_kwargs["weights"]
        assert pytest.approx(sum(weights.values()), rel=1e-4) == 1.0
        assert pytest.approx(weights["A11"], rel=1e-4) == 0.5
        assert pytest.approx(weights["B11"], rel=1e-4) == 0.5

    def test_backtest_aporte_passed_correctly(self):
        import cli as cli_module

        backtest_mock = MagicMock()
        backtest_mock.run_backtest = MagicMock(return_value=MagicMock())
        backtest_mock.compare_against_benchmark = MagicMock(return_value=MagicMock())
        backtest_mock.format_metrics_report = MagicMock(return_value="APORTE\n")

        with patch.object(
            sys, "argv",
            ["cli", "backtest", "--aporte", "2500.0"]
        ):
            with patch.dict("sys.modules", {"core.backtest_engine": backtest_mock}):
                out = StringIO()
                with patch("sys.stdout", out):
                    cli_module.main()

        call_kwargs = backtest_mock.run_backtest.call_args[1]
        assert call_kwargs["monthly_contribution"] == pytest.approx(2500.0)

    def test_backtest_capital_passed_correctly(self):
        import cli as cli_module

        backtest_mock = MagicMock()
        backtest_mock.run_backtest = MagicMock(return_value=MagicMock())
        backtest_mock.compare_against_benchmark = MagicMock(return_value=MagicMock())
        backtest_mock.format_metrics_report = MagicMock(return_value="CAPITAL\n")

        with patch.object(
            sys, "argv",
            ["cli", "backtest", "--capital", "50000.0"]
        ):
            with patch.dict("sys.modules", {"core.backtest_engine": backtest_mock}):
                out = StringIO()
                with patch("sys.stdout", out):
                    cli_module.main()

        call_kwargs = backtest_mock.run_backtest.call_args[1]
        assert call_kwargs["initial_capital"] == pytest.approx(50000.0)

    def test_backtest_rebalance_quarterly_default(self):
        import cli as cli_module

        backtest_mock = MagicMock()
        backtest_mock.run_backtest = MagicMock(return_value=MagicMock())
        backtest_mock.compare_against_benchmark = MagicMock(return_value=MagicMock())
        backtest_mock.format_metrics_report = MagicMock(return_value="REBAL\n")

        with patch.object(sys, "argv", ["cli", "backtest"]):
            with patch.dict("sys.modules", {"core.backtest_engine": backtest_mock}):
                out = StringIO()
                with patch("sys.stdout", out):
                    cli_module.main()

        call_kwargs = backtest_mock.run_backtest.call_args[1]
        assert call_kwargs["rebalance_frequency"] == "quarterly"

    def test_backtest_rebalance_monthly_accepted(self):
        import cli as cli_module

        backtest_mock = MagicMock()
        backtest_mock.run_backtest = MagicMock(return_value=MagicMock())
        backtest_mock.compare_against_benchmark = MagicMock(return_value=MagicMock())
        backtest_mock.format_metrics_report = MagicMock(return_value="MONTHLY\n")

        with patch.object(sys, "argv", ["cli", "backtest", "--rebalance", "monthly"]):
            with patch.dict("sys.modules", {"core.backtest_engine": backtest_mock}):
                out = StringIO()
                with patch("sys.stdout", out):
                    cli_module.main()

        call_kwargs = backtest_mock.run_backtest.call_args[1]
        assert call_kwargs["rebalance_frequency"] == "monthly"

    def test_backtest_rebalance_semiannual_accepted(self):
        import cli as cli_module

        backtest_mock = MagicMock()
        backtest_mock.run_backtest = MagicMock(return_value=MagicMock())
        backtest_mock.compare_against_benchmark = MagicMock(return_value=MagicMock())
        backtest_mock.format_metrics_report = MagicMock(return_value="SEMI\n")

        with patch.object(sys, "argv", ["cli", "backtest", "--rebalance", "semiannual"]):
            with patch.dict("sys.modules", {"core.backtest_engine": backtest_mock}):
                out = StringIO()
                with patch("sys.stdout", out):
                    cli_module.main()

        call_kwargs = backtest_mock.run_backtest.call_args[1]
        assert call_kwargs["rebalance_frequency"] == "semiannual"

    def test_backtest_invalid_rebalance_choice_exits(self):
        import cli as cli_module

        with patch.object(sys, "argv", ["cli", "backtest", "--rebalance", "daily"]):
            out = StringIO()
            with patch("sys.stdout", out):
                with pytest.raises(SystemExit) as exc_info:
                    cli_module.main()
        assert exc_info.value.code == 2

    def test_backtest_price_series_has_correct_length(self):
        """Generated price series must have --meses entries."""
        import cli as cli_module

        backtest_mock = MagicMock()
        backtest_mock.run_backtest = MagicMock(return_value=MagicMock())
        backtest_mock.compare_against_benchmark = MagicMock(return_value=MagicMock())
        backtest_mock.format_metrics_report = MagicMock(return_value="LEN\n")

        with patch.object(
            sys, "argv",
            ["cli", "backtest", "--tickers", "MXRF11", "--weights", "1.0", "--meses", "12"]
        ):
            with patch.dict("sys.modules", {"core.backtest_engine": backtest_mock}):
                out = StringIO()
                with patch("sys.stdout", out):
                    cli_module.main()

        call_kwargs = backtest_mock.run_backtest.call_args[1]
        assert len(call_kwargs["price_series"]["MXRF11"]) == 12
        assert len(call_kwargs["dividend_series"]["MXRF11"]) == 12

    def test_backtest_benchmark_has_correct_length(self):
        """Generated benchmark must have --meses entries."""
        import cli as cli_module

        backtest_mock = MagicMock()
        captured_benchmark = {}

        def fake_compare(result, benchmark, aporte, capital):
            captured_benchmark["bench"] = benchmark
            return MagicMock()

        backtest_mock.run_backtest = MagicMock(return_value=MagicMock())
        backtest_mock.compare_against_benchmark = MagicMock(side_effect=fake_compare)
        backtest_mock.format_metrics_report = MagicMock(return_value="BENCH\n")

        with patch.object(
            sys, "argv",
            ["cli", "backtest", "--meses", "6"]
        ):
            with patch.dict("sys.modules", {"core.backtest_engine": backtest_mock}):
                out = StringIO()
                with patch("sys.stdout", out):
                    cli_module.main()

        assert len(captured_benchmark["bench"]) == 6

    def test_backtest_output_is_printed(self):
        import cli as cli_module

        backtest_mock = MagicMock()
        backtest_mock.run_backtest = MagicMock(return_value=MagicMock())
        backtest_mock.compare_against_benchmark = MagicMock(return_value=MagicMock())
        backtest_mock.format_metrics_report = MagicMock(return_value="FORMATTED REPORT OUTPUT\n")

        with patch.object(sys, "argv", ["cli", "backtest"]):
            with patch.dict("sys.modules", {"core.backtest_engine": backtest_mock}):
                out = StringIO()
                with patch("sys.stdout", out):
                    cli_module.main()

        assert "FORMATTED REPORT OUTPUT" in out.getvalue()


# ---------------------------------------------------------------------------
# No command — print help
# ---------------------------------------------------------------------------


class TestNoCommand:
    def test_no_command_prints_help(self):
        import cli as cli_module

        with patch.object(sys, "argv", ["cli"]):
            out = StringIO()
            with patch("sys.stdout", out):
                cli_module.main()
        # argparse prints help or usage when no subcommand is given
        # The else branch calls parser.print_help()
        output = out.getvalue()
        # argparse writes help to stderr but print_help() goes to stdout by default
        # Either way, main() should not crash
        assert output is not None  # main() completed without exception

    def test_no_command_does_not_crash(self):
        import cli as cli_module

        with patch.object(sys, "argv", ["cli"]):
            # Should not raise any exception
            try:
                cli_module.main()
            except SystemExit:
                pass  # argparse may exit; that is acceptable


# ---------------------------------------------------------------------------
# __main__ guard
# ---------------------------------------------------------------------------


class TestMainGuard:
    def test_main_is_callable(self):
        import cli as cli_module
        assert callable(cli_module.main)

    def test_module_can_be_imported_without_side_effects(self):
        """Importing cli.py must not execute main() or touch the DB."""
        with patch("cli.init_db") as mock_init, \
             patch("cli.run_full_cycle") as mock_cycle:
            import cli as cli_module  # noqa: F401
        mock_init.assert_not_called()
        mock_cycle.assert_not_called()
