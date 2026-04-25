"""Tests for infra/database.py — SQLite operations with temp file DB."""

import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import infra.database as db


class _FakeSettings:
    def __init__(self, db_path: str):
        self.database_path = db_path


@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    """Use a temporary file-based SQLite database for each test."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db, "settings", _FakeSettings(db_path))
    db.init_db()
    yield db_path


class TestInitDb:
    def test_creates_tables(self):
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in cursor.fetchall()}
        conn.close()
        assert "users" in tables
        assert "operations" in tables
        assert "proventos" in tables
        assert "portfolio_snapshots" in tables


class TestCreateUser:
    def test_create_returns_id(self):
        user_id = db.create_user("test@example.com", "hashed123")
        assert user_id is not None
        assert isinstance(user_id, int)

    def test_duplicate_email_returns_none(self):
        db.create_user("dup@example.com", "hash1")
        result = db.create_user("dup@example.com", "hash2")
        assert result is None


class TestGetUserByEmail:
    def test_existing_user(self):
        db.create_user("find@test.com", "hashed_pw")
        user = db.get_user_by_email("find@test.com")
        assert user is not None
        assert user["email"] == "find@test.com"
        assert user["hashed_password"] == "hashed_pw"

    def test_nonexistent_user(self):
        user = db.get_user_by_email("nobody@test.com")
        assert user is None


class TestOperations:
    def test_save_and_get_operations(self):
        uid = db.create_user("ops@test.com", "hash")
        db.save_operation(uid, "HGLG11", "compra", 10.0, 150.0)
        db.save_operation(uid, "XPML11", "compra", 5.0, 100.0)

        ops = db.get_operations(uid)
        assert len(ops) == 2
        assert ops[0]["ticker"] == "HGLG11"
        assert ops[1]["quantidade"] == 5.0

    def test_get_empty_operations(self):
        uid = db.create_user("empty@test.com", "hash")
        ops = db.get_operations(uid)
        assert ops == []


class TestProventos:
    def test_save_and_get_proventos(self):
        uid = db.create_user("prov@test.com", "hash")
        db.save_provento(uid, "HGLG11", 50.0)
        db.save_provento(uid, "HGLG11", 55.0)

        provs = db.get_proventos(uid)
        assert len(provs) == 2
        assert provs[0]["valor"] == 50.0

    def test_get_empty_proventos(self):
        uid = db.create_user("noprov@test.com", "hash")
        assert db.get_proventos(uid) == []


class TestPortfolioSnapshots:
    def test_save_and_get_snapshots(self):
        uid = db.create_user("snap@test.com", "hash")
        report = {
            "resumo_carteira": {
                "valor_total": 10000.0,
                "lucro_prejuizo_total": 500.0,
                "lucro_prejuizo_percentual_total": 5.0,
            },
            "renda_passiva": {"renda_total": 100.0, "yield_percentual": 1.0},
            "fogo_financeiro": {"patrimonio_necessario": 600000.0, "anos_estimados": 15.3},
        }
        db.save_portfolio_snapshot(uid, report)
        snaps = db.get_portfolio_snapshots(uid)
        assert len(snaps) == 1
        assert snaps[0]["valor_total"] == 10000.0
        assert snaps[0]["anos_estimados"] == 15.3

    def test_empty_report_defaults(self):
        uid = db.create_user("defaults@test.com", "hash")
        db.save_portfolio_snapshot(uid, {})
        snaps = db.get_portfolio_snapshots(uid)
        assert snaps[0]["valor_total"] == 0.0

    def test_get_empty_snapshots(self):
        uid = db.create_user("nosnap@test.com", "hash")
        assert db.get_portfolio_snapshots(uid) == []
