"""Tests for core/polymarket_copy_signal.py"""

import pytest
from unittest.mock import patch

from core.polymarket_alpha_detector import WalletScore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wallet(address: str, alpha_score: float = 0.7) -> WalletScore:
    return WalletScore(
        address=address,
        alpha_score=alpha_score,
        win_rate=0.7,
        total_trades=30,
        recency_weight=0.8,
        diversity_score=0.6,
        preferred_categories=["politics"],
        last_active_ts=0.0,
    )


def _position(outcome: str, question: str = "Will Fed cut rates in 2025?") -> dict:
    return {
        "outcome": outcome,
        "market": {"question": question, "tags": []},
        "side": outcome.lower(),
    }


# ---------------------------------------------------------------------------
# No positions
# ---------------------------------------------------------------------------


def test_no_wallets_returns_none_direction():
    from core.polymarket_copy_signal import get_copy_signal
    signal = get_copy_signal("Will Fed cut rates?", [])
    assert signal.direction == "none"
    assert signal.confidence == 0.0
    assert signal.wallet_count == 0


def test_no_matching_positions_returns_none():
    from core.polymarket_copy_signal import get_copy_signal

    with patch("core.polymarket_copy_signal._fetch_open_positions", return_value=[]):
        signal = get_copy_signal("Will Fed cut rates?", [_wallet("0xa")])

    assert signal.direction == "none"
    assert signal.wallet_count == 0


# ---------------------------------------------------------------------------
# Consensus — YES majority
# ---------------------------------------------------------------------------


def test_all_yes_positions_returns_yes():
    from core.polymarket_copy_signal import get_copy_signal

    positions = [_position("Yes")]

    with patch("core.polymarket_copy_signal._fetch_open_positions", return_value=positions):
        signal = get_copy_signal("Will Fed cut rates", [_wallet("0xa"), _wallet("0xb")])

    assert signal.direction == "yes"
    assert signal.confidence == 1.0


def test_all_no_positions_returns_no():
    from core.polymarket_copy_signal import get_copy_signal

    positions = [_position("No")]

    with patch("core.polymarket_copy_signal._fetch_open_positions", return_value=positions):
        signal = get_copy_signal("Will Fed cut rates", [_wallet("0xa")])

    assert signal.direction == "no"


def test_majority_yes_wins():
    from core.polymarket_copy_signal import get_copy_signal

    def mock_positions(address):
        if address in ("0xa", "0xb"):
            return [_position("Yes")]
        return [_position("No")]

    wallets = [_wallet("0xa", 0.8), _wallet("0xb", 0.7), _wallet("0xc", 0.6)]

    with patch("core.polymarket_copy_signal._fetch_open_positions", side_effect=mock_positions):
        signal = get_copy_signal("Will Fed cut rates", wallets)

    assert signal.direction == "yes"
    assert signal.confidence > 0.5


# ---------------------------------------------------------------------------
# Weighted consensus
# ---------------------------------------------------------------------------


def test_higher_alpha_wallet_has_more_influence():
    from core.polymarket_copy_signal import get_copy_signal

    def mock_positions(address):
        if address == "0xhigh_alpha":
            return [_position("Yes")]
        return [_position("No")]

    # 0xhigh_alpha has much higher score
    wallets = [_wallet("0xhigh_alpha", 0.95), _wallet("0xlow1", 0.1), _wallet("0xlow2", 0.1)]

    with patch("core.polymarket_copy_signal._fetch_open_positions", side_effect=mock_positions):
        signal = get_copy_signal("Will Fed cut rates", wallets)

    # YES should win because 0xhigh_alpha has 0.95 vs 0.1+0.1=0.2 for NO
    assert signal.direction == "yes"


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------


def test_question_matches_partial_words():
    from core.polymarket_copy_signal import _question_matches

    position = {"market": {"question": "Will the Federal Reserve cut interest rates in 2025?"}}
    assert _question_matches("Fed cut rates 2025", position) is True


def test_question_no_match_unrelated():
    from core.polymarket_copy_signal import _question_matches

    position = {"market": {"question": "Will Barcelona win the Champions League?"}}
    assert _question_matches("Fed cut rates 2025", position) is False


def test_empty_query_returns_false():
    from core.polymarket_copy_signal import _question_matches

    position = {"market": {"question": "Will Fed cut rates?"}}
    assert _question_matches("", position) is False


# ---------------------------------------------------------------------------
# CopySignal fields
# ---------------------------------------------------------------------------


def test_copy_signal_confidence_bounded():
    from core.polymarket_copy_signal import get_copy_signal

    positions = [_position("Yes")]
    with patch("core.polymarket_copy_signal._fetch_open_positions", return_value=positions):
        signal = get_copy_signal("Will Fed cut rates", [_wallet("0xa")])

    assert 0.0 <= signal.confidence <= 1.0


def test_copy_signal_wallet_count():
    from core.polymarket_copy_signal import get_copy_signal

    positions = [_position("Yes")]
    wallets = [_wallet("0xa"), _wallet("0xb"), _wallet("0xc")]

    with patch("core.polymarket_copy_signal._fetch_open_positions", return_value=positions):
        signal = get_copy_signal("Will Fed cut rates", wallets)

    assert signal.wallet_count == 3
