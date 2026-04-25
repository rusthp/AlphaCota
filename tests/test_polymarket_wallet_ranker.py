"""tests/test_polymarket_wallet_ranker.py — Tests for wallet alpha ranking."""

import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.polymarket_wallet_ranker import (
    _MIN_RESOLVED,
    _WIN_RATE_DEMOTE,
    _WIN_RATE_PROMOTE,
    WalletRank,
    rerank_wallets,
    update_wallet_alpha_scores,
)
from core.polymarket_ledger import init_db


@pytest.fixture
def ledger_conn(tmp_path):
    db_file = str(tmp_path / "rank_test.db")
    c = init_db(db_file)
    yield c
    c.close()


@pytest.fixture
def cache_db(tmp_path):
    """Create a minimal wallet_cache.db with wallet_positions table."""
    db_path = tmp_path / "wallet_cache.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE wallet_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            address TEXT NOT NULL,
            condition_id TEXT NOT NULL,
            resolved INTEGER NOT NULL DEFAULT 0,
            pnl REAL NOT NULL DEFAULT 0.0,
            closed_at REAL NOT NULL
        )"""
    )
    conn.commit()
    conn.close()
    return db_path


def _insert_positions(db_path: Path, address: str, wins: int, losses: int) -> None:
    """Insert resolved position rows for a wallet."""
    conn = sqlite3.connect(str(db_path))
    now = time.time()
    for i in range(wins):
        conn.execute(
            "INSERT INTO wallet_positions (address, condition_id, resolved, pnl, closed_at) VALUES (?,?,1,?,?)",
            (address, f"cid-win-{address}-{i}", 5.0, now - i * 3600),
        )
    for i in range(losses):
        conn.execute(
            "INSERT INTO wallet_positions (address, condition_id, resolved, pnl, closed_at) VALUES (?,?,1,?,?)",
            (address, f"cid-loss-{address}-{i}", -3.0, now - i * 7200),
        )
    conn.commit()
    conn.close()


def _tracker(addresses: list[str]) -> MagicMock:
    t = MagicMock()
    t.watchlist = addresses
    return t


class TestRerankWallets:
    def test_excludes_wallet_with_few_resolved(self, ledger_conn, cache_db):
        addr = "0xABCD"
        _insert_positions(cache_db, addr, wins=2, losses=1)  # only 3 < MIN_RESOLVED
        tracker = _tracker([addr])
        rankings = rerank_wallets(ledger_conn, tracker, db_path=cache_db)
        assert len(rankings) == 0

    def test_promotes_wallet_above_65_pct(self, ledger_conn, cache_db):
        addr = "0xPROMO"
        _insert_positions(cache_db, addr, wins=8, losses=2)  # 80% win rate
        tracker = _tracker([addr])
        rankings = rerank_wallets(ledger_conn, tracker, db_path=cache_db)
        assert len(rankings) == 1
        assert rankings[0].rank_change == "promoted"
        assert rankings[0].win_rate >= _WIN_RATE_PROMOTE

    def test_demotes_wallet_below_55_pct(self, ledger_conn, cache_db):
        addr = "0xDEMO"
        _insert_positions(cache_db, addr, wins=2, losses=8)  # 20% win rate
        tracker = _tracker([addr])
        rankings = rerank_wallets(ledger_conn, tracker, db_path=cache_db)
        assert len(rankings) == 1
        assert rankings[0].rank_change == "demoted"
        assert rankings[0].win_rate < _WIN_RATE_DEMOTE

    def test_stable_wallet_in_middle_range(self, ledger_conn, cache_db):
        addr = "0xSTBL"
        _insert_positions(cache_db, addr, wins=6, losses=4)  # 60% — stable
        tracker = _tracker([addr])
        rankings = rerank_wallets(ledger_conn, tracker, db_path=cache_db)
        assert len(rankings) == 1
        assert rankings[0].rank_change == "stable"

    def test_sorted_by_alpha_score_descending(self, ledger_conn, cache_db):
        for addr, wins, losses in [
            ("0xA", 8, 2),   # 80% — promoted
            ("0xB", 6, 4),   # 60% — stable
            ("0xC", 2, 8),   # 20% — demoted
        ]:
            _insert_positions(cache_db, addr, wins=wins, losses=losses)
        tracker = _tracker(["0xA", "0xB", "0xC"])
        rankings = rerank_wallets(ledger_conn, tracker, db_path=cache_db)
        scores = [r.alpha_score for r in rankings]
        assert scores == sorted(scores, reverse=True)

    def test_empty_watchlist_returns_empty(self, ledger_conn, cache_db):
        tracker = _tracker([])
        assert rerank_wallets(ledger_conn, tracker, db_path=cache_db) == []

    def test_min_resolved_threshold(self, ledger_conn, cache_db):
        addr = "0xBORDER"
        # exactly _MIN_RESOLVED wins — should qualify
        _insert_positions(cache_db, addr, wins=_MIN_RESOLVED, losses=0)
        tracker = _tracker([addr])
        rankings = rerank_wallets(ledger_conn, tracker, db_path=cache_db)
        assert len(rankings) == 1


class TestUpdateWalletAlphaScores:
    def test_creates_wallet_scores_table_if_missing(self, tmp_path):
        # cache_db with no wallet_scores table
        db_path = tmp_path / "empty_cache.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE wallet_positions (address TEXT, condition_id TEXT, resolved INTEGER, pnl REAL, closed_at REAL)"
        )
        conn.commit()
        conn.close()

        rankings = [
            WalletRank(
                address="0xABC",
                win_rate=0.70,
                resolved_count=10,
                rank_change="promoted",
                alpha_score=0.65,
                last_active=time.time(),
            )
        ]
        update_wallet_alpha_scores(rankings, db_path=db_path)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT alpha_score FROM wallet_scores WHERE address='0xABC'").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == pytest.approx(0.65)

    def test_skips_when_db_missing(self, tmp_path):
        missing = tmp_path / "nonexistent.db"
        rankings = [
            WalletRank("0xABC", 0.7, 10, "promoted", 0.65, time.time())
        ]
        # Should not raise
        update_wallet_alpha_scores(rankings, db_path=missing)
