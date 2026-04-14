"""Tests for core/polymarket_alpha_detector.py"""

import time
import pytest
from unittest.mock import patch

from core.polymarket_wallet_tracker import WalletHistory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_history(address: str, win_rate: float, total_trades: int, last_active_days_ago: float = 1.0) -> WalletHistory:
    wins = int(total_trades * win_rate)
    losses = total_trades - wins
    return WalletHistory(
        address=address,
        total_trades=total_trades,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        avg_size_usd=50.0,
        preferred_categories=["politics", "crypto", "sports"],
        last_active_ts=time.time() - last_active_days_ago * 86400,
    )


# ---------------------------------------------------------------------------
# rank_wallets
# ---------------------------------------------------------------------------


def test_rank_wallets_filters_by_min_trades():
    from core.polymarket_alpha_detector import rank_wallets

    histories = {
        "0xlow": _make_history("0xlow", 0.9, 5),    # below min_trades=20
        "0xhigh": _make_history("0xhigh", 0.7, 25),  # qualifies
    }

    def mock_get(address, force_refresh=False):
        return histories[address]

    with patch("core.polymarket_alpha_detector.get_wallet_history", side_effect=mock_get):
        scores = rank_wallets(["0xlow", "0xhigh"], min_trades=20)

    assert len(scores) == 1
    assert scores[0].address == "0xhigh"


def test_rank_wallets_sorted_descending():
    from core.polymarket_alpha_detector import rank_wallets

    histories = {
        "0xa": _make_history("0xa", 0.80, 30, last_active_days_ago=1),
        "0xb": _make_history("0xb", 0.60, 30, last_active_days_ago=1),
        "0xc": _make_history("0xc", 0.70, 30, last_active_days_ago=1),
    }

    def mock_get(address, force_refresh=False):
        return histories[address]

    with patch("core.polymarket_alpha_detector.get_wallet_history", side_effect=mock_get):
        scores = rank_wallets(list(histories.keys()), min_trades=20)

    alpha_scores = [s.alpha_score for s in scores]
    assert alpha_scores == sorted(alpha_scores, reverse=True)


def test_rank_wallets_empty_list():
    from core.polymarket_alpha_detector import rank_wallets
    scores = rank_wallets([])
    assert scores == []


def test_rank_wallets_all_below_min_trades():
    from core.polymarket_alpha_detector import rank_wallets

    def mock_get(address, force_refresh=False):
        return _make_history(address, 0.9, 5)  # always below min=20

    with patch("core.polymarket_alpha_detector.get_wallet_history", side_effect=mock_get):
        scores = rank_wallets(["0xa", "0xb"], min_trades=20)

    assert scores == []


def test_rank_wallets_exception_skips_wallet():
    from core.polymarket_alpha_detector import rank_wallets

    def mock_get(address, force_refresh=False):
        if address == "0xbad":
            raise ConnectionError("network error")
        return _make_history(address, 0.7, 25)

    with patch("core.polymarket_alpha_detector.get_wallet_history", side_effect=mock_get):
        scores = rank_wallets(["0xbad", "0xgood"], min_trades=20)

    assert len(scores) == 1
    assert scores[0].address == "0xgood"


# ---------------------------------------------------------------------------
# Alpha score components
# ---------------------------------------------------------------------------


def test_alpha_score_bounded_0_to_1():
    from core.polymarket_alpha_detector import rank_wallets

    histories = {"0xperfect": _make_history("0xperfect", 1.0, 50, last_active_days_ago=0.1)}

    def mock_get(address, force_refresh=False):
        return histories[address]

    with patch("core.polymarket_alpha_detector.get_wallet_history", side_effect=mock_get):
        scores = rank_wallets(["0xperfect"], min_trades=20)

    assert 0.0 <= scores[0].alpha_score <= 1.0


def test_recency_weight_decays_over_time():
    from core.polymarket_alpha_detector import _recency_weight
    recent = _recency_weight(time.time() - 86400)     # 1 day ago
    old = _recency_weight(time.time() - 30 * 86400)   # 30 days ago (half-life)
    very_old = _recency_weight(time.time() - 90 * 86400)  # 90 days ago

    assert recent > old > very_old
    assert abs(old - 0.5) < 0.05  # ~0.5 at half-life


def test_recency_weight_zero_timestamp():
    from core.polymarket_alpha_detector import _recency_weight
    assert _recency_weight(0.0) == 0.0


def test_diversity_score_capped_at_1():
    from core.polymarket_alpha_detector import _diversity_score
    many_categories = ["a", "b", "c", "d", "e", "f", "g"]
    assert _diversity_score(many_categories) == 1.0


def test_diversity_score_empty():
    from core.polymarket_alpha_detector import _diversity_score
    assert _diversity_score([]) == 0.0


# ---------------------------------------------------------------------------
# detect_top_alpha_wallets
# ---------------------------------------------------------------------------


def test_detect_top_alpha_wallets_empty_env(monkeypatch):
    from core.polymarket_alpha_detector import detect_top_alpha_wallets
    monkeypatch.delenv("POLYMARKET_WATCH_WALLETS", raising=False)
    result = detect_top_alpha_wallets()
    assert result == []


def test_detect_top_alpha_wallets_reads_env(monkeypatch):
    from core.polymarket_alpha_detector import detect_top_alpha_wallets

    monkeypatch.setenv("POLYMARKET_WATCH_WALLETS", "0xaaa,0xbbb")

    def mock_get(address, force_refresh=False):
        return _make_history(address, 0.7, 25)

    with patch("core.polymarket_alpha_detector.get_wallet_history", side_effect=mock_get):
        scores = detect_top_alpha_wallets(limit=10)

    assert len(scores) == 2


def test_detect_top_alpha_wallets_respects_limit(monkeypatch):
    from core.polymarket_alpha_detector import detect_top_alpha_wallets

    monkeypatch.setenv("POLYMARKET_WATCH_WALLETS", "0xa,0xb,0xc,0xd,0xe")

    def mock_get(address, force_refresh=False):
        return _make_history(address, 0.7, 25)

    with patch("core.polymarket_alpha_detector.get_wallet_history", side_effect=mock_get):
        scores = detect_top_alpha_wallets(limit=2)

    assert len(scores) == 2
