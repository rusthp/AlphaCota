"""tests/test_polymarket_ledger.py — Tests for polymarket_ledger module."""

import sqlite3
import time
from unittest.mock import MagicMock

import pytest

from core.polymarket_ledger import init_db, insert_order_if_new, reconcile_pending_orders


@pytest.fixture
def conn(tmp_path):
    """In-memory-style connection via tmp_path for isolation."""
    db_file = str(tmp_path / "test_ledger.db")
    c = init_db(db_file)
    yield c
    c.close()


class TestInitDb:
    def test_creates_all_tables(self, conn):
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {row["name"] for row in tables}
        assert "pm_markets" in names
        assert "pm_orders" in names
        assert "pm_positions" in names
        assert "pm_trades" in names
        assert "pm_pnl_snapshots" in names

    def test_wal_mode(self, conn):
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_idempotent(self, tmp_path):
        db_file = str(tmp_path / "idempotent.db")
        c1 = init_db(db_file)
        c1.close()
        c2 = init_db(db_file)
        tables = c2.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        assert len(tables) >= 5
        c2.close()


class TestInsertOrderIfNew:
    def test_insert_new_order(self, conn):
        result = insert_order_if_new(
            conn,
            client_order_id="ord-001",
            condition_id="cid1",
            token_id="tok1",
            direction="yes",
            size_usd=50.0,
            limit_price=0.55,
            mode="paper",
        )
        assert result is True

    def test_idempotent_duplicate(self, conn):
        kwargs = dict(
            client_order_id="ord-002",
            condition_id="cid1",
            token_id="tok1",
            direction="yes",
            size_usd=50.0,
            limit_price=0.55,
            mode="paper",
        )
        insert_order_if_new(conn, **kwargs)
        result2 = insert_order_if_new(conn, **kwargs)
        assert result2 is False

    def test_order_persisted_with_pending_status(self, conn):
        insert_order_if_new(
            conn,
            client_order_id="ord-003",
            condition_id="cid2",
            token_id="tok2",
            direction="no",
            size_usd=75.0,
            limit_price=0.42,
            mode="live",
        )
        row = conn.execute(
            "SELECT * FROM pm_orders WHERE client_order_id = ?", ("ord-003",)
        ).fetchone()
        assert row is not None
        assert row["status"] == "pending"
        assert row["direction"] == "no"
        assert row["mode"] == "live"
        assert float(row["size_usd"]) == pytest.approx(75.0)

    def test_created_at_set(self, conn):
        before = time.time()
        insert_order_if_new(
            conn,
            client_order_id="ord-004",
            condition_id="cid1",
            token_id="tok1",
            direction="yes",
            size_usd=10.0,
            limit_price=0.5,
        )
        after = time.time()
        row = conn.execute(
            "SELECT created_at FROM pm_orders WHERE client_order_id = ?", ("ord-004",)
        ).fetchone()
        assert before <= float(row["created_at"]) <= after

    def test_multiple_orders_different_ids(self, conn):
        for i in range(5):
            insert_order_if_new(
                conn,
                client_order_id=f"ord-{i:03d}",
                condition_id="cid1",
                token_id="tok1",
                direction="yes",
                size_usd=10.0,
                limit_price=0.5,
            )
        count = conn.execute("SELECT COUNT(*) FROM pm_orders").fetchone()[0]
        assert count == 5


class TestReconcilePendingOrders:
    def _insert_pending(self, conn, oid: str, mode: str = "paper") -> None:
        insert_order_if_new(
            conn,
            client_order_id=oid,
            condition_id="cid1",
            token_id="tok1",
            direction="yes",
            size_usd=25.0,
            limit_price=0.55,
            mode=mode,
        )

    def test_paper_mode_auto_fills(self, conn):
        self._insert_pending(conn, "ord-p1", mode="paper")
        self._insert_pending(conn, "ord-p2", mode="paper")
        updated = reconcile_pending_orders(conn, client=None)
        assert updated == 2
        rows = conn.execute("SELECT status FROM pm_orders").fetchall()
        assert all(row["status"] == "filled" for row in rows)

    def test_no_pending_returns_zero(self, conn):
        updated = reconcile_pending_orders(conn, client=None)
        assert updated == 0

    def test_live_mode_filled_by_client(self, conn):
        self._insert_pending(conn, "ord-l1", mode="live")
        mock_client = MagicMock()
        mock_client.get_order.return_value = {"status": "filled", "avgPrice": "0.56"}
        updated = reconcile_pending_orders(conn, client=mock_client)
        assert updated == 1
        row = conn.execute(
            "SELECT status, fill_price FROM pm_orders WHERE client_order_id = ?",
            ("ord-l1",),
        ).fetchone()
        assert row["status"] == "filled"
        assert float(row["fill_price"]) == pytest.approx(0.56)

    def test_live_mode_cancelled_by_client(self, conn):
        self._insert_pending(conn, "ord-l2", mode="live")
        mock_client = MagicMock()
        mock_client.get_order.return_value = {"status": "cancelled"}
        reconcile_pending_orders(conn, client=mock_client)
        row = conn.execute(
            "SELECT status FROM pm_orders WHERE client_order_id = ?", ("ord-l2",)
        ).fetchone()
        assert row["status"] == "cancelled"

    def test_live_mode_client_error_skips_order(self, conn):
        self._insert_pending(conn, "ord-l3", mode="live")
        mock_client = MagicMock()
        mock_client.get_order.side_effect = RuntimeError("network error")
        updated = reconcile_pending_orders(conn, client=mock_client)
        assert updated == 0
        row = conn.execute(
            "SELECT status FROM pm_orders WHERE client_order_id = ?", ("ord-l3",)
        ).fetchone()
        assert row["status"] == "pending"

    def test_mixed_modes_paper_only_auto_filled(self, conn):
        self._insert_pending(conn, "ord-mix-p", mode="paper")
        self._insert_pending(conn, "ord-mix-l", mode="live")
        mock_client = MagicMock()
        mock_client.get_order.return_value = {"status": "pending"}
        reconcile_pending_orders(conn, client=mock_client)
        paper_row = conn.execute(
            "SELECT status FROM pm_orders WHERE client_order_id = ?", ("ord-mix-p",)
        ).fetchone()
        live_row = conn.execute(
            "SELECT status FROM pm_orders WHERE client_order_id = ?", ("ord-mix-l",)
        ).fetchone()
        assert paper_row["status"] == "filled"
        assert live_row["status"] == "pending"
