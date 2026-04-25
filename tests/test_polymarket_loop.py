"""tests/test_polymarket_loop.py — Tests for the trading loop."""

import os
import signal
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.polymarket_loop import _GracefulStop, _cancel_all_pending, _is_killed, _write_pnl_snapshot
from core.polymarket_ledger import init_db


@pytest.fixture
def conn(tmp_path):
    db_file = str(tmp_path / "loop_test.db")
    c = init_db(db_file)
    yield c
    c.close()


@pytest.fixture
def kill_file(tmp_path, monkeypatch):
    kf = tmp_path / "POLYMARKET_KILL"
    monkeypatch.setattr("core.polymarket_loop._KILL_FILE", kf)
    return kf


class TestIsKilled:
    def test_returns_false_when_file_absent(self, kill_file):
        assert not _is_killed()

    def test_returns_true_when_file_present(self, kill_file):
        kill_file.touch()
        assert _is_killed()


class TestCancelAllPending:
    def _insert_pending(self, conn, oid: str = "ord-1") -> None:
        from core.polymarket_ledger import insert_order_if_new
        insert_order_if_new(conn, oid, "cid1", "tok1", "yes", 25.0, 0.55, mode="paper")

    def test_cancels_pending_paper_orders(self, conn):
        self._insert_pending(conn, "ord-1")
        self._insert_pending(conn, "ord-2")
        _cancel_all_pending(conn, mode="paper")
        rows = conn.execute("SELECT status FROM pm_orders").fetchall()
        assert all(row["status"] == "cancelled" for row in rows)

    def test_does_not_cancel_live_orders(self, conn):
        from core.polymarket_ledger import insert_order_if_new
        insert_order_if_new(conn, "live-ord", "cid1", "tok1", "yes", 25.0, 0.55, mode="live")
        _cancel_all_pending(conn, mode="paper")
        row = conn.execute("SELECT status FROM pm_orders WHERE client_order_id='live-ord'").fetchone()
        assert row["status"] == "pending"

    def test_noop_for_live_mode(self, conn):
        self._insert_pending(conn, "ord-3")
        _cancel_all_pending(conn, mode="live")
        row = conn.execute("SELECT status FROM pm_orders WHERE client_order_id='ord-3'").fetchone()
        assert row["status"] == "pending"


class TestWritePnlSnapshot:
    def test_creates_snapshot_row(self, conn):
        _write_pnl_snapshot(conn, mode="paper")
        rows = conn.execute("SELECT * FROM pm_pnl_snapshots").fetchall()
        assert len(rows) >= 1
        assert rows[0]["mode"] == "paper"

    def test_idempotent_same_day(self, conn):
        _write_pnl_snapshot(conn, mode="paper")
        _write_pnl_snapshot(conn, mode="paper")
        rows = conn.execute("SELECT COUNT(*) FROM pm_pnl_snapshots").fetchone()[0]
        assert rows == 1


class TestKillSwitchHaltsLoop:
    def test_kill_file_stops_loop_before_first_iteration(self, tmp_path, monkeypatch, kill_file):
        kill_file.touch()

        calls = []

        def mock_discover(**kwargs):
            calls.append(1)
            return []

        with (
            patch("core.polymarket_loop._is_killed", return_value=True),
            patch("core.polymarket_ledger.init_db", return_value=MagicMock()),
            patch("core.polymarket_client.get_wallet_health"),
            patch("core.polymarket_client.discover_markets", side_effect=mock_discover),
        ):
            from core.polymarket_loop import run_loop
            cfg = MagicMock()
            cfg.polymarket_max_position_usd = 100.0
            cfg.polymarket_max_daily_loss_usd = 200.0
            run_loop(config=cfg, mode="paper", max_iterations=5)

        assert len(calls) == 0


class TestSigtermGracefulShutdown:
    def test_sigterm_raises_graceful_stop(self):
        from core.polymarket_loop import _handle_sigterm
        with pytest.raises(_GracefulStop):
            _handle_sigterm(signal.SIGTERM, None)


class TestMaxIterationsExits:
    def test_loop_stops_at_max_iterations(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = [0]
        mock_conn.execute.return_value.fetchall.return_value = []

        healthy_wallet = MagicMock()
        healthy_wallet.is_healthy = True
        healthy_wallet.usdc_balance = 500.0

        discover_calls = []

        def mock_discover(**kwargs):
            discover_calls.append(1)
            return []

        with (
            patch("core.polymarket_loop._is_killed", return_value=False),
            patch("core.polymarket_ledger.init_db", return_value=mock_conn),
            patch("core.polymarket_client.get_wallet_health", return_value=healthy_wallet),
            patch("core.polymarket_client.discover_markets", side_effect=mock_discover),
            patch("core.polymarket_decision_engine.generate_trade_decisions", return_value=[]),
            patch("core.polymarket_monitor.monitor_positions", return_value=[]),
            patch("core.polymarket_loop._write_pnl_snapshot"),
            patch("core.polymarket_loop._cancel_all_pending"),
            patch("core.polymarket_loop.time") as mock_time,
        ):
            mock_time.time.return_value = 0.0
            mock_time.sleep = MagicMock()

            from core.polymarket_loop import run_loop
            cfg = MagicMock()
            cfg.polymarket_max_position_usd = 100.0
            cfg.polymarket_max_daily_loss_usd = 200.0
            run_loop(config=cfg, mode="paper", max_iterations=3)

        assert len(discover_calls) <= 3
