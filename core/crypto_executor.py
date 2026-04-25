"""
core/crypto_executor.py — Paper-trading executor for crypto signals.

Writes rows to crypto_orders / crypto_positions / crypto_trades in the
local SQLite ledger. A separate live-Binance executor will live in a
follow-up file; this module is paper-only and deterministic.

Public API:
    execute_paper(signal, size_usd, conn) -> CryptoOrder
    close_paper_position(position_id, current_price, reason, conn) -> CryptoTrade
"""

from __future__ import annotations

import sqlite3
import time
import uuid

from core.crypto_types import CryptoOrder, CryptoPosition, CryptoSignal, CryptoTrade
from core.logger import logger


def execute_paper(
    signal: CryptoSignal,
    size_usd: float,
    conn: sqlite3.Connection,
) -> CryptoOrder:
    """Simulate an immediate market fill for a CryptoSignal in paper mode.

    Creates two ledger records atomically:
        1. A row in `crypto_orders` with status='filled' at `entry_price`.
        2. A row in `crypto_positions` tracking the open position.

    Args:
        signal: A non-flat CryptoSignal to act on.
        size_usd: USD notional to deploy (already sized by size_position()).
        conn: Open sqlite3 connection with init_crypto_db applied.

    Returns:
        The created CryptoOrder record (paper, filled).

    Raises:
        ValueError: If signal.direction is "flat" or size_usd <= 0.
    """
    if signal.direction == "flat":
        raise ValueError("execute_paper: cannot execute a flat signal")
    if size_usd <= 0.0:
        raise ValueError(f"execute_paper: size_usd must be > 0 (got {size_usd})")
    if signal.entry_price <= 0.0:
        raise ValueError("execute_paper: signal.entry_price must be > 0")

    order_id = str(uuid.uuid4())
    position_id = str(uuid.uuid4())
    now = time.time()

    side = "buy" if signal.direction == "long" else "sell"
    pos_side = "long" if signal.direction == "long" else "short"

    try:
        conn.execute(
            """
            INSERT INTO crypto_orders
                (id, symbol, side, qty_usd, entry_price, status, mode, created_at)
            VALUES (?, ?, ?, ?, ?, 'filled', 'paper', ?)
            """,
            (order_id, signal.symbol, side, size_usd, signal.entry_price, now),
        )
        conn.execute(
            """
            INSERT INTO crypto_positions
                (id, symbol, side, entry_price, qty_usd, stop_loss, take_profit,
                 opened_at, mode, signal_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'paper', ?)
            """,
            (
                position_id,
                signal.symbol,
                pos_side,
                signal.entry_price,
                size_usd,
                signal.stop_loss,
                signal.take_profit,
                now,
                float(signal.confidence),
            ),
        )
        conn.commit()
    except sqlite3.Error as exc:
        logger.error("execute_paper: db error %s", exc)
        raise

    logger.info(
        "execute_paper: %s %s %.2f USD @ %.8f (sl=%.8f tp=%.8f conf=%.3f)",
        pos_side.upper(),
        signal.symbol,
        size_usd,
        signal.entry_price,
        signal.stop_loss,
        signal.take_profit,
        signal.confidence,
    )

    return CryptoOrder(
        id=order_id,
        symbol=signal.symbol,
        side=side,
        qty=round(size_usd, 2),
        price=signal.entry_price,
        status="filled",
        mode="paper",
        created_at=now,
    )


def close_paper_position(
    position_id: str,
    current_price: float,
    reason: str,
    conn: sqlite3.Connection,
) -> CryptoTrade:
    """Close an open paper position and emit a realised CryptoTrade.

    PnL formulas (qty_usd is USD notional at entry):
        long  : pnl = qty_usd * (exit - entry) / entry
        short : pnl = qty_usd * (entry - exit) / entry
        pnl_pct = pnl / qty_usd (signed fraction)

    Steps:
        1. Load the position row by id.
        2. Compute PnL from entry and `current_price`.
        3. Insert into crypto_trades (closed round-trip).
        4. Delete the position row.

    Args:
        position_id: UUID of the crypto_positions row to close.
        current_price: Exit price (must be > 0).
        reason: Free-form exit reason (e.g. "sl_hit", "tp_hit", "signal_flip").
        conn: Open sqlite3 connection.

    Returns:
        The CryptoTrade record.

    Raises:
        ValueError: If the position_id does not exist or price is non-positive.
    """
    if current_price <= 0.0:
        raise ValueError(f"close_paper_position: bad current_price {current_price}")

    row = conn.execute(
        "SELECT * FROM crypto_positions WHERE id = ?", (position_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"close_paper_position: position {position_id} not found")

    symbol = row["symbol"]
    side = row["side"]
    entry_price = float(row["entry_price"])
    qty_usd = float(row["qty_usd"])
    opened_at = float(row["opened_at"])

    if entry_price <= 0.0 or qty_usd <= 0.0:
        raise ValueError(
            f"close_paper_position: corrupt position {position_id} "
            f"entry={entry_price} qty={qty_usd}"
        )

    if side == "long":
        pnl = qty_usd * (current_price - entry_price) / entry_price
    elif side == "short":
        pnl = qty_usd * (entry_price - current_price) / entry_price
    else:
        raise ValueError(f"close_paper_position: unknown side '{side}'")

    pnl_pct = pnl / qty_usd
    now = time.time()
    trade_id = str(uuid.uuid4())

    try:
        conn.execute(
            """
            INSERT INTO crypto_trades
                (id, symbol, side, entry_price, exit_price, qty_usd,
                 realized_pnl, pnl_pct, opened_at, closed_at, exit_reason, mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'paper')
            """,
            (
                trade_id,
                symbol,
                side,
                entry_price,
                current_price,
                qty_usd,
                pnl,
                pnl_pct,
                opened_at,
                now,
                reason,
            ),
        )
        conn.execute("DELETE FROM crypto_positions WHERE id = ?", (position_id,))
        conn.commit()
    except sqlite3.Error as exc:
        logger.error("close_paper_position: db error %s", exc)
        raise

    logger.info(
        "close_paper_position: %s %s exit=%.8f pnl=%.2f (%.2f%%) reason=%s",
        side.upper(),
        symbol,
        current_price,
        pnl,
        pnl_pct * 100.0,
        reason,
    )

    return CryptoTrade(
        id=trade_id,
        symbol=symbol,
        side="long" if side == "long" else "short",
        entry_price=entry_price,
        exit_price=current_price,
        qty=qty_usd,
        pnl=round(pnl, 6),
        pnl_pct=round(pnl_pct, 6),
        opened_at=opened_at,
        closed_at=now,
        reason=reason,
    )


def _position_from_row(row: sqlite3.Row) -> CryptoPosition:
    """Adapter: DB row -> CryptoPosition dataclass (kept here for test convenience)."""
    return CryptoPosition(
        id=row["id"],
        symbol=row["symbol"],
        side=row["side"],
        entry_price=float(row["entry_price"]),
        qty=float(row["qty_usd"]),
        stop_loss=float(row["stop_loss"]),
        take_profit=float(row["take_profit"]),
        opened_at=float(row["opened_at"]),
        mode=row["mode"],
    )
