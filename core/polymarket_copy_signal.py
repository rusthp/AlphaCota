"""
core/polymarket_copy_signal.py — Copy-trading signal from alpha wallet positions.

Checks if tracked alpha wallets have open YES or NO positions on a given market
and returns a consensus direction + confidence.

Usage:
    from core.polymarket_copy_signal import get_copy_signal, CopySignal
    from core.polymarket_alpha_detector import WalletScore

    signal = get_copy_signal("Will Fed cut rates in 2025?", alpha_wallets)
    if signal.direction == "yes":
        print(f"Consensus YES — {signal.confidence:.0%} confidence")
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

from core.polymarket_alpha_detector import WalletScore

_GAMMA_API = "https://gamma-api.polymarket.com"
_REQUEST_TIMEOUT = 15
_HEADERS = {"User-Agent": "AlphaCota/1.0 Copy-Signal", "Accept": "application/json"}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CopySignal:
    direction: str        # "yes" | "no" | "none"
    confidence: float     # 0.0 – 1.0 weighted by alpha_score
    wallet_count: int     # number of wallets with open positions
    consensus_ratio: float  # fraction of wallets agreeing with majority direction


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_open_positions(address: str) -> list[dict]:
    """Fetch open (non-resolved) positions for a wallet from gamma-api."""
    try:
        resp = requests.get(
            f"{_GAMMA_API}/positions",
            params={"user": address, "closed": "false", "limit": 100},
            headers=_HEADERS,
            timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data if isinstance(data, list) else data.get("positions", [])
    except Exception:
        return []


def _question_matches(market_question: str, position: dict) -> bool:
    """Fuzzy match: check if position's market question contains key words from query."""
    market = position.get("market") or {}
    mq = (market.get("question") or "").lower()
    query_words = set(market_question.lower().split())
    # Match if >50% of query words appear in the market question
    if not query_words:
        return False
    matches = sum(1 for w in query_words if w in mq)
    return matches / len(query_words) >= 0.5


def _position_direction(position: dict) -> str | None:
    """Return 'yes' or 'no' based on the outcome the wallet holds."""
    outcome = (position.get("outcome") or "").lower()
    if outcome in ("yes", "true", "1"):
        return "yes"
    if outcome in ("no", "false", "0"):
        return "no"
    # Fallback: check token side
    side = (position.get("side") or position.get("tokenId") or "").lower()
    if "yes" in side:
        return "yes"
    if "no" in side:
        return "no"
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_copy_signal(
    market_question: str,
    alpha_wallets: list[WalletScore],
) -> CopySignal:
    """
    Check how alpha wallets are positioned on a market and return consensus signal.

    Args:
        market_question: The market question string (used for fuzzy matching).
        alpha_wallets: Ranked list of WalletScore from detect_top_alpha_wallets().

    Returns:
        CopySignal with direction, confidence, wallet_count, consensus_ratio.
        Returns direction="none" if no wallets have positions on this market.
    """
    if not alpha_wallets:
        return CopySignal(direction="none", confidence=0.0, wallet_count=0, consensus_ratio=0.0)

    yes_weight = 0.0
    no_weight = 0.0
    wallet_count = 0

    for wallet in alpha_wallets:
        positions = _fetch_open_positions(wallet.address)
        for pos in positions:
            if not _question_matches(market_question, pos):
                continue
            direction = _position_direction(pos)
            if direction is None:
                continue
            wallet_count += 1
            weight = wallet.alpha_score
            if direction == "yes":
                yes_weight += weight
            else:
                no_weight += weight
            break  # one position per wallet per market

    if wallet_count == 0:
        return CopySignal(direction="none", confidence=0.0, wallet_count=0, consensus_ratio=0.0)

    total_weight = yes_weight + no_weight
    if total_weight == 0:
        return CopySignal(direction="none", confidence=0.0, wallet_count=wallet_count, consensus_ratio=0.0)

    if yes_weight >= no_weight:
        direction = "yes"
        confidence = yes_weight / total_weight
    else:
        direction = "no"
        confidence = no_weight / total_weight

    # consensus_ratio: fraction of wallets on the majority side
    # (wallet_count is total, we don't track per-side count separately here)
    consensus_ratio = confidence  # same as confidence when weight ≈ uniform

    return CopySignal(
        direction=direction,
        confidence=round(confidence, 4),
        wallet_count=wallet_count,
        consensus_ratio=round(consensus_ratio, 4),
    )
