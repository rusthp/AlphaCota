"""Tests for core/state_repository.py — SQLite-backed portfolio state persistence."""

import sqlite3
from unittest.mock import patch

import pytest

from core.state_repository import (
    init_db,
    save_snapshot,
    save_allocations,
    save_scores,
    get_last_snapshot,
)


@pytest.fixture
def conn():
    """In-memory SQLite connection with schema initialized."""
    c = sqlite3.connect(":memory:")
    init_db(c)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------


class TestInitDb:
    def test_creates_tables(self, conn):
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = {row[0] for row in cursor.fetchall()}
        assert "portfolio_snapshots" in tables
        assert "asset_allocations" in tables
        assert "score_history" in tables

    def test_idempotent(self, conn):
        """Calling init_db twice should not raise."""
        init_db(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        assert len(cursor.fetchall()) >= 3


# ---------------------------------------------------------------------------
# save_snapshot / get_last_snapshot
# ---------------------------------------------------------------------------


class TestSaveSnapshot:
    def test_returns_row_id(self, conn):
        snap = {
            "timestamp": "2025-06-01T10:00:00",
            "investor_profile": "moderado",
            "expected_return": 0.12,
            "monte_carlo_median": 150000,
        }
        row_id = save_snapshot(conn, snap)
        assert isinstance(row_id, int)
        assert row_id >= 1

    def test_increments_id(self, conn):
        snap1 = {"timestamp": "2025-01-01", "investor_profile": "conservador"}
        snap2 = {"timestamp": "2025-02-01", "investor_profile": "agressivo"}
        id1 = save_snapshot(conn, snap1)
        id2 = save_snapshot(conn, snap2)
        assert id2 == id1 + 1

    def test_defaults_for_optional_fields(self, conn):
        snap = {"timestamp": "2025-03-01", "investor_profile": "moderado"}
        row_id = save_snapshot(conn, snap)
        cursor = conn.cursor()
        cursor.row_factory = sqlite3.Row
        cursor.execute("SELECT * FROM portfolio_snapshots WHERE id = ?", (row_id,))
        row = dict(cursor.fetchone())
        assert row["expected_return"] == 0.0
        assert row["monte_carlo_median"] == 0.0


class TestGetLastSnapshot:
    def test_returns_none_when_empty(self, conn):
        assert get_last_snapshot(conn) is None

    def test_returns_latest_by_timestamp(self, conn):
        save_snapshot(conn, {"timestamp": "2025-01-01", "investor_profile": "conservador"})
        save_snapshot(conn, {"timestamp": "2025-06-01", "investor_profile": "agressivo"})
        last = get_last_snapshot(conn)
        assert last is not None
        assert last["investor_profile"] == "agressivo"
        assert last["timestamp"] == "2025-06-01"

    def test_includes_allocations(self, conn):
        sid = save_snapshot(conn, {"timestamp": "2025-06-01", "investor_profile": "moderado"})
        allocs = [
            {"ticker": "HGLG11", "asset_class": "FII", "weight": 0.5, "score": 80},
            {"ticker": "MXRF11", "asset_class": "FII", "weight": 0.5, "score": 75},
        ]
        save_allocations(conn, sid, allocs)
        last = get_last_snapshot(conn)
        assert len(last["allocations"]) == 2
        tickers = {a["ticker"] for a in last["allocations"]}
        assert tickers == {"HGLG11", "MXRF11"}

    def test_empty_allocations_list(self, conn):
        save_snapshot(conn, {"timestamp": "2025-06-01", "investor_profile": "moderado"})
        last = get_last_snapshot(conn)
        assert last["allocations"] == []


# ---------------------------------------------------------------------------
# save_allocations
# ---------------------------------------------------------------------------


class TestSaveAllocations:
    def test_saves_multiple(self, conn):
        sid = save_snapshot(conn, {"timestamp": "2025-01-01", "investor_profile": "moderado"})
        allocs = [
            {"ticker": "HGLG11", "weight": 0.4, "asset_class": "Logística", "score": 85},
            {"ticker": "XPML11", "weight": 0.3, "asset_class": "Shopping", "score": 78},
            {"ticker": "MXRF11", "weight": 0.3, "asset_class": "Papel", "score": 72},
        ]
        save_allocations(conn, sid, allocs)

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM asset_allocations WHERE snapshot_id = ?", (sid,))
        assert cursor.fetchone()[0] == 3

    def test_defaults_asset_class_to_unknown(self, conn):
        sid = save_snapshot(conn, {"timestamp": "2025-01-01", "investor_profile": "moderado"})
        allocs = [{"ticker": "TEST11", "weight": 1.0}]
        save_allocations(conn, sid, allocs)

        cursor = conn.cursor()
        cursor.row_factory = sqlite3.Row
        cursor.execute("SELECT * FROM asset_allocations WHERE snapshot_id = ?", (sid,))
        row = dict(cursor.fetchone())
        assert row["asset_class"] == "UNKNOWN"
        assert row["score"] == 0.0

    def test_empty_list(self, conn):
        sid = save_snapshot(conn, {"timestamp": "2025-01-01", "investor_profile": "moderado"})
        save_allocations(conn, sid, [])
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM asset_allocations WHERE snapshot_id = ?", (sid,))
        assert cursor.fetchone()[0] == 0


# ---------------------------------------------------------------------------
# save_scores
# ---------------------------------------------------------------------------


class TestSaveScores:
    def test_saves_multiple(self, conn):
        scores = [
            {
                "timestamp": "2025-06-01",
                "ticker": "HGLG11",
                "fundamental_score": 80,
                "momentum_score": 70,
                "final_score": 75,
                "altman_z": 3.5,
            },
            {
                "timestamp": "2025-06-01",
                "ticker": "MXRF11",
                "fundamental_score": 65,
                "momentum_score": 55,
                "final_score": 60,
                "altman_z": 2.8,
            },
        ]
        save_scores(conn, scores)

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM score_history")
        assert cursor.fetchone()[0] == 2

    def test_defaults_for_optional_fields(self, conn):
        scores = [{"timestamp": "2025-06-01", "ticker": "TEST11"}]
        save_scores(conn, scores)

        cursor = conn.cursor()
        cursor.row_factory = sqlite3.Row
        cursor.execute("SELECT * FROM score_history WHERE ticker = 'TEST11'")
        row = dict(cursor.fetchone())
        assert row["fundamental_score"] == 0.0
        assert row["momentum_score"] == 0.0
        assert row["final_score"] == 0.0
        assert row["altman_z"] == 0.0

    def test_empty_list(self, conn):
        save_scores(conn, [])
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM score_history")
        assert cursor.fetchone()[0] == 0

    def test_preserves_values(self, conn):
        scores = [
            {
                "timestamp": "2025-06-01",
                "ticker": "HGLG11",
                "fundamental_score": 82.5,
                "momentum_score": 71.3,
                "final_score": 76.9,
                "altman_z": 3.14,
            }
        ]
        save_scores(conn, scores)

        cursor = conn.cursor()
        cursor.row_factory = sqlite3.Row
        cursor.execute("SELECT * FROM score_history WHERE ticker = 'HGLG11'")
        row = dict(cursor.fetchone())
        assert row["fundamental_score"] == 82.5
        assert row["momentum_score"] == 71.3
        assert row["final_score"] == 76.9
        assert abs(row["altman_z"] - 3.14) < 0.001
