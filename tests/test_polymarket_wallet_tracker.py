"""Tests for core/polymarket_wallet_tracker.py"""

import json
import time
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def tmp_cache_db(tmp_path, monkeypatch):
    import core.polymarket_wallet_tracker as wt
    monkeypatch.setattr(wt, "_CACHE_DB", tmp_path / "wallet_cache.db")
    yield


MOCK_POSITIONS = [
    {
        "outcome": "Yes",
        "resolvedValue": 1.0,
        "initialValue": 50.0,
        "amountUSD": 50.0,
        "endDate": time.time() - 86400,
        "market": {"question": "Will Fed cut rates?", "tags": [{"label": "politics"}]},
    },
    {
        "outcome": "No",
        "resolvedValue": 0.0,
        "initialValue": 30.0,
        "amountUSD": 30.0,
        "endDate": time.time() - 172800,
        "market": {"question": "Will BTC reach 100k?", "tags": [{"label": "crypto"}]},
    },
    {
        "outcome": "Yes",
        "resolvedValue": 1.0,
        "initialValue": 20.0,
        "amountUSD": 20.0,
        "endDate": time.time() - 259200,
        "market": {"question": "Will inflation drop?", "tags": [{"label": "economics"}]},
    },
]


# ---------------------------------------------------------------------------
# _fetch_positions mock
# ---------------------------------------------------------------------------


def test_get_wallet_history_parses_positions():
    from core.polymarket_wallet_tracker import get_wallet_history
    with patch("core.polymarket_wallet_tracker._fetch_positions", return_value=MOCK_POSITIONS):
        history = get_wallet_history("0xabc123")
    assert history.total_trades == 3
    assert history.wins == 2
    assert history.losses == 1
    assert abs(history.win_rate - 2 / 3) < 0.01
    assert history.avg_size_usd == pytest.approx(100 / 3, abs=0.1)


def test_get_wallet_history_categories_extracted():
    from core.polymarket_wallet_tracker import get_wallet_history
    with patch("core.polymarket_wallet_tracker._fetch_positions", return_value=MOCK_POSITIONS):
        history = get_wallet_history("0xabc123")
    assert "politics" in history.preferred_categories
    assert "crypto" in history.preferred_categories


def test_get_wallet_history_empty_positions():
    from core.polymarket_wallet_tracker import get_wallet_history
    with patch("core.polymarket_wallet_tracker._fetch_positions", return_value=[]):
        history = get_wallet_history("0xempty")
    assert history.total_trades == 0
    assert history.win_rate == 0.0
    assert history.avg_size_usd == 0.0


# ---------------------------------------------------------------------------
# Cache hit / miss
# ---------------------------------------------------------------------------


def test_cache_miss_fetches_api():
    from core.polymarket_wallet_tracker import get_wallet_history
    with patch("core.polymarket_wallet_tracker._fetch_positions", return_value=MOCK_POSITIONS) as mock_fetch:
        get_wallet_history("0xcache1")
        get_wallet_history("0xcache1")  # second call — should hit cache
    # API should only be called once
    assert mock_fetch.call_count == 1


def test_cache_hit_returns_cached():
    from core.polymarket_wallet_tracker import get_wallet_history, load_cached_history
    with patch("core.polymarket_wallet_tracker._fetch_positions", return_value=MOCK_POSITIONS):
        original = get_wallet_history("0xcache2")
    cached = load_cached_history("0xcache2")
    assert cached is not None
    assert cached.total_trades == original.total_trades
    assert cached.win_rate == original.win_rate


def test_force_refresh_bypasses_cache():
    from core.polymarket_wallet_tracker import get_wallet_history
    with patch("core.polymarket_wallet_tracker._fetch_positions", return_value=MOCK_POSITIONS) as mock_fetch:
        get_wallet_history("0xcache3")
        get_wallet_history("0xcache3", force_refresh=True)
    assert mock_fetch.call_count == 2


def test_cache_ttl_expiry(monkeypatch):
    from core.polymarket_wallet_tracker import get_wallet_history, load_cached_history, save_history, WalletHistory
    # Save a history with old fetched_at
    old_history = WalletHistory(
        address="0xold",
        total_trades=5,
        wins=3,
        losses=2,
        win_rate=0.6,
        avg_size_usd=10.0,
        fetched_at=time.time() - 7200,  # 2h ago — past TTL
    )
    save_history("0xold", old_history)
    cached = load_cached_history("0xold")
    assert cached is None  # TTL expired


def test_stale_cache_triggers_api_call():
    from core.polymarket_wallet_tracker import get_wallet_history, save_history, WalletHistory
    old = WalletHistory(
        address="0xstale",
        total_trades=1,
        wins=1,
        losses=0,
        win_rate=1.0,
        avg_size_usd=5.0,
        fetched_at=time.time() - 7200,
    )
    save_history("0xstale", old)
    with patch("core.polymarket_wallet_tracker._fetch_positions", return_value=MOCK_POSITIONS) as mock_fetch:
        get_wallet_history("0xstale")
    assert mock_fetch.call_count == 1


# ---------------------------------------------------------------------------
# WalletHistory fields
# ---------------------------------------------------------------------------


def test_wallet_history_address_normalized():
    from core.polymarket_wallet_tracker import get_wallet_history
    with patch("core.polymarket_wallet_tracker._fetch_positions", return_value=MOCK_POSITIONS):
        history = get_wallet_history("0xABC123UPPER")
    assert history.address == "0xabc123upper"
