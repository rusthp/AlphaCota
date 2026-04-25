"""
core/crypto_sizing_engine.py — Kelly-criterion position sizing for crypto.

Pure functions — given probability/reward/risk inputs and a balance, returns
the USD notional to commit. No I/O.

Public API:
    kelly_fraction(win_prob, win_return, loss_return) -> float
    size_position(signal, balance_usd, max_position_usd) -> float
"""

from __future__ import annotations

from core.crypto_types import CryptoSignal

# Cap Kelly aggression at 25% — industry-standard safeguard against the
# formula's sensitivity to mis-estimated edge.
_MAX_KELLY_CAP = 0.25

# Minimum USD notional to open a position (anything smaller is skipped to
# avoid fee-dominated trades on most exchanges).
_MIN_POSITION_USD = 10.0


def kelly_fraction(
    win_prob: float,
    win_return: float,
    loss_return: float,
) -> float:
    """Kelly fraction for an asymmetric payoff trade.

    Using the generalised Kelly formula:

        f* = (p * b - q) / b
        where:
            p = win_prob
            q = 1 - win_prob
            b = win_return / loss_return   (odds received on win vs risk)

    Both `win_return` and `loss_return` are expressed as *positive* fractions
    (e.g. 0.04 for a 4% move). If `loss_return` is <= 0 the function returns
    0.0 because risk is undefined.

    Result is clamped to [0.0, _MAX_KELLY_CAP] to cap position sizing even in
    the face of extreme confidence + favourable R/R.

    Args:
        win_prob: Probability of winning, in [0, 1].
        win_return: Fractional gain if the trade wins (positive).
        loss_return: Fractional loss if the trade loses (positive).

    Returns:
        Kelly fraction in [0.0, 0.25], rounded to 6 decimals.
    """
    if win_prob <= 0.0 or win_prob >= 1.0:
        return 0.0
    if win_return <= 0.0 or loss_return <= 0.0:
        return 0.0

    b = win_return / loss_return
    q = 1.0 - win_prob
    f_star = (win_prob * b - q) / b

    if f_star <= 0.0:
        return 0.0
    return round(min(f_star, _MAX_KELLY_CAP), 6)


def size_position(
    signal: CryptoSignal,
    balance_usd: float,
    max_position_usd: float = 100.0,
) -> float:
    """Convert a CryptoSignal + balance into a USD notional size.

    Steps:
        1. Reject immediately if the signal is flat or missing levels.
        2. Compute fractional win/loss returns from entry / SL / TP.
        3. Kelly-fraction = kelly_fraction(confidence, win_return, loss_return).
        4. Raw USD size = kelly_fraction * balance_usd.
        5. Clamp to [_MIN_POSITION_USD, max_position_usd]. If the clamped
           size would exceed the balance, return balance_usd instead.
        6. Return 0.0 when the raw size is below _MIN_POSITION_USD — the
           loop should then skip the trade.

    Args:
        signal: A non-flat CryptoSignal produced by generate_signal().
        balance_usd: Available trading balance in USD.
        max_position_usd: Hard per-position cap (default 100 USD).

    Returns:
        USD notional size, rounded to 2 decimals. 0.0 when the trade is too
        small or has no positive Kelly edge.
    """
    if signal.direction == "flat":
        return 0.0
    if balance_usd <= 0.0 or max_position_usd <= 0.0:
        return 0.0
    if signal.entry_price <= 0.0:
        return 0.0

    if signal.direction == "long":
        win_return = (signal.take_profit - signal.entry_price) / signal.entry_price
        loss_return = (signal.entry_price - signal.stop_loss) / signal.entry_price
    else:  # short
        win_return = (signal.entry_price - signal.take_profit) / signal.entry_price
        loss_return = (signal.stop_loss - signal.entry_price) / signal.entry_price

    if win_return <= 0.0 or loss_return <= 0.0:
        return 0.0

    k = kelly_fraction(signal.confidence, win_return, loss_return)
    if k <= 0.0:
        return 0.0

    raw = k * balance_usd
    if raw < _MIN_POSITION_USD:
        return 0.0

    capped = min(raw, max_position_usd, balance_usd)
    if capped < _MIN_POSITION_USD:
        return 0.0
    return round(capped, 2)
