"""
core/crypto_risk_engine.py — Risk gating for the crypto trading loop.

Three layers of protection:
    1. check_risk_limits — pre-trade: daily loss cap, concurrent-position cap.
    2. validate_signal_risk — per-signal: SL existence, min reward/risk, min confidence.
    3. should_exit_position — per-tick: SL/TP touch, or signal flip vs open side.

All functions accept connections / dataclasses as parameters; no globals read.

Public API:
    MAX_POSITION_USD, MAX_DAILY_LOSS_USD, MAX_OPEN_POSITIONS constants
    check_risk_limits(conn, mode) -> (ok, reason)
    should_exit_position(position, current_price, current_signal) -> (exit, reason)
    validate_signal_risk(signal, balance_usd) -> bool
"""

from __future__ import annotations

import sqlite3
from datetime import date

from core.crypto_types import CryptoPosition, CryptoSignal
from core.logger import logger

MAX_POSITION_USD: float = 100.0
MAX_DAILY_LOSS_USD: float = 30.0
MAX_OPEN_POSITIONS: int = 3

_MIN_RR_RATIO: float = 1.5
_MIN_CONFIDENCE: float = 0.65
_MIN_BALANCE_USD: float = 20.0


def check_risk_limits(
    conn: sqlite3.Connection,
    mode: str,
) -> tuple[bool, str]:
    """Verify that the loop is allowed to open a new position right now.

    Checks (in order):
        1. Realised PnL for today (mode-filtered) must be > -MAX_DAILY_LOSS_USD.
        2. Open-position count (mode-filtered) must be < MAX_OPEN_POSITIONS.

    Args:
        conn: Open sqlite3 connection with the crypto_* schema installed.
        mode: "paper" or "live".

    Returns:
        (ok, reason). `reason` is "" when `ok` is True, or a human-readable
        diagnostic string when False.
    """
    if mode not in ("paper", "live"):
        return (False, f"invalid_mode={mode}")

    try:
        today = date.today().isoformat()
        row = conn.execute(
            """
            SELECT COALESCE(SUM(realized_pnl), 0.0) AS pnl
              FROM crypto_trades
             WHERE mode = ?
               AND date(closed_at, 'unixepoch') = ?
            """,
            (mode, today),
        ).fetchone()
        daily_pnl = float(row["pnl"]) if row is not None else 0.0
    except sqlite3.Error as exc:
        logger.error("check_risk_limits: pnl query failed: %s", exc)
        return (False, f"db_error:{exc}")

    if daily_pnl <= -abs(MAX_DAILY_LOSS_USD):
        return (
            False,
            f"daily_loss_cap_hit pnl={daily_pnl:.2f} cap={-MAX_DAILY_LOSS_USD:.2f}",
        )

    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM crypto_positions WHERE mode = ?",
            (mode,),
        ).fetchone()
        open_count = int(row["c"]) if row is not None else 0
    except sqlite3.Error as exc:
        logger.error("check_risk_limits: position count failed: %s", exc)
        return (False, f"db_error:{exc}")

    if open_count >= MAX_OPEN_POSITIONS:
        return (
            False,
            f"max_open_positions_reached open={open_count} cap={MAX_OPEN_POSITIONS}",
        )

    return (True, "")


def should_exit_position(
    position: CryptoPosition,
    current_price: float,
    current_signal: CryptoSignal,
) -> tuple[bool, str]:
    """Decide whether an open position should be closed this tick.

    Exit rules (first match wins):
        1. Long position and current_price <= stop_loss  -> ("sl_hit")
        2. Long position and current_price >= take_profit -> ("tp_hit")
        3. Short position and current_price >= stop_loss  -> ("sl_hit")
        4. Short position and current_price <= take_profit -> ("tp_hit")
        5. Non-flat current_signal with opposite direction and
           confidence >= 0.65                             -> ("signal_flip")

    Args:
        position: Open position being evaluated.
        current_price: Latest mid/last price.
        current_signal: Fresh signal from this tick.

    Returns:
        (should_exit, reason). `reason` is "" when should_exit is False.
    """
    if current_price <= 0.0:
        return (False, "")

    if position.side == "long":
        if current_price <= position.stop_loss:
            return (True, "sl_hit")
        if current_price >= position.take_profit:
            return (True, "tp_hit")
    elif position.side == "short":
        if current_price >= position.stop_loss:
            return (True, "sl_hit")
        if current_price <= position.take_profit:
            return (True, "tp_hit")

    # Signal flip — only considered when the new signal is non-flat, confident,
    # and points the OPPOSITE direction from our open position.
    if current_signal.direction != "flat" and current_signal.confidence >= _MIN_CONFIDENCE:
        if position.side == "long" and current_signal.direction == "short":
            return (True, "signal_flip")
        if position.side == "short" and current_signal.direction == "long":
            return (True, "signal_flip")

    return (False, "")


def validate_signal_risk(signal: CryptoSignal, balance_usd: float) -> bool:
    """Final per-signal sanity check before sizing & execution.

    Rules:
        1. Direction must be "long" or "short" (reject flat).
        2. Confidence >= 0.65.
        3. Stop-loss must be strictly positive.
        4. Entry, SL, and TP must all be positive and consistent with direction.
        5. Reward/risk >= 1.5 (abs(TP - entry) / abs(entry - SL)).
        6. Wallet balance >= _MIN_BALANCE_USD.

    Args:
        signal: The CryptoSignal produced by generate_signal().
        balance_usd: Available trading balance (paper or live).

    Returns:
        True when all gates pass, False otherwise. Reasons are logged at debug.
    """
    if signal.direction == "flat":
        logger.debug("validate_signal_risk: flat direction rejected")
        return False
    if signal.confidence < _MIN_CONFIDENCE:
        logger.debug(
            "validate_signal_risk: confidence %.3f < %.2f",
            signal.confidence, _MIN_CONFIDENCE,
        )
        return False
    if signal.entry_price <= 0.0 or signal.stop_loss <= 0.0 or signal.take_profit <= 0.0:
        logger.debug("validate_signal_risk: non-positive price level(s)")
        return False
    if balance_usd < _MIN_BALANCE_USD:
        logger.debug(
            "validate_signal_risk: balance %.2f below min %.2f",
            balance_usd, _MIN_BALANCE_USD,
        )
        return False

    # Direction consistency: long wants SL < entry < TP; short wants TP < entry < SL.
    if signal.direction == "long":
        if not (signal.stop_loss < signal.entry_price < signal.take_profit):
            logger.debug("validate_signal_risk: long SL/TP ordering invalid")
            return False
        risk = signal.entry_price - signal.stop_loss
        reward = signal.take_profit - signal.entry_price
    else:  # short
        if not (signal.take_profit < signal.entry_price < signal.stop_loss):
            logger.debug("validate_signal_risk: short SL/TP ordering invalid")
            return False
        risk = signal.stop_loss - signal.entry_price
        reward = signal.entry_price - signal.take_profit

    if risk <= 0.0:
        return False
    rr = reward / risk
    if rr < _MIN_RR_RATIO:
        logger.debug("validate_signal_risk: R/R %.2f < %.2f", rr, _MIN_RR_RATIO)
        return False

    return True
