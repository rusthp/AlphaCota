"""
core/polymarket_paper_executor.py — Paper trading execution layer.

Simulates order fills at mid-price + half-spread slippage, writes to ledger.

Public API:
    execute_paper(decision, conn, client) -> Order
    close_paper_position(position_id, conn, client) -> Trade
"""

from __future__ import annotations

import time
import uuid

from core.logger import logger
from core.polymarket_ledger import insert_order_if_new, reconcile_pending_orders
from core.polymarket_types import Order, Trade, TradeDecision


def execute_paper(
    decision: TradeDecision,
    conn: object,
    client: object | None = None,
) -> Order:
    """Execute a paper trade for the given TradeDecision.

    Fetches the real mid-price from the CLOB, applies half-spread slippage
    (pessimistic: pays more for YES, less for NO), inserts the order into the
    ledger as 'pending', then immediately reconciles to 'filled'.

    Args:
        decision: TradeDecision with condition_id, token_id, direction, size_usd.
        conn: Open sqlite3 ledger connection (from init_db).
        client: Optional CLOB client — used to get real mid-price when available.

    Returns:
        Order dataclass with status='filled' and actual fill_price.
    """

    fill_price = _get_fill_price(decision.token_id, decision.direction, client)

    client_order_id = str(uuid.uuid4())
    now = time.time()

    insert_order_if_new(
        conn,  # type: ignore[arg-type]
        client_order_id=client_order_id,
        condition_id=decision.condition_id,
        token_id=decision.token_id,
        direction=decision.direction,
        size_usd=decision.size_usd,
        limit_price=fill_price,
        mode="paper",
    )

    reconcile_pending_orders(conn, client=None)  # type: ignore[arg-type]

    row = conn.execute(  # type: ignore[union-attr]
        "SELECT * FROM pm_orders WHERE client_order_id = ?", (client_order_id,)
    ).fetchone()
    actual_fill = float(row["fill_price"] or fill_price)

    _upsert_position(conn, client_order_id, decision, actual_fill, now)  # type: ignore[arg-type]

    logger.info(
        "execute_paper: filled %s %s %.2f USDC @ %.4f",
        decision.direction.upper(),
        decision.condition_id[:12],
        decision.size_usd,
        actual_fill,
    )

    return Order(
        client_order_id=client_order_id,
        condition_id=decision.condition_id,
        token_id=decision.token_id,
        direction=decision.direction,
        size_usd=decision.size_usd,
        fill_price=actual_fill,
        status="filled",
        mode="paper",
        created_at=now,
    )


def _get_fill_price(token_id: str, direction: str, client: object | None) -> float:
    """Determine fill price using mid-price + half-spread slippage."""
    if client is not None:
        try:
            from core.polymarket_client import get_order_book
            book = get_order_book(token_id)
            half_spread = book.spread_pct / 2.0
            if direction == "yes":
                return round(min(book.mid_price + half_spread, 0.99), 6)
            return round(max(book.mid_price - half_spread, 0.01), 6)
        except Exception as exc:
            logger.warning("_get_fill_price: order book unavailable: %s", exc)

    return 0.50


def _upsert_position(
    conn: object,
    order_id: str,
    decision: TradeDecision,
    fill_price: float,
    opened_at: float,
) -> None:
    """Insert a new open position record into pm_positions."""

    position_id = str(uuid.uuid4())
    conn.execute(  # type: ignore[union-attr]
        """
        INSERT OR IGNORE INTO pm_positions
            (position_id, condition_id, token_id, direction, size_usd,
             entry_price, current_price, unrealized_pnl, mode, opened_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, 'paper', ?, ?)
        """,
        (
            position_id,
            decision.condition_id,
            decision.token_id,
            decision.direction,
            decision.size_usd,
            fill_price,
            fill_price,
            opened_at,
            opened_at,
        ),
    )
    conn.commit()  # type: ignore[union-attr]


def close_paper_position(
    position_id: str,
    conn: object,
    client: object | None = None,
) -> Trade:
    """Close an open paper position and record realized PnL.

    Reads the current mid-price for the position's token, computes realized
    PnL = (exit_price - entry_price) * size_usd (for YES; inverted for NO),
    inserts a Trade record, and removes the Position row.

    Args:
        position_id: UUID of the pm_positions row to close.
        conn: Open sqlite3 ledger connection.
        client: Optional CLOB client for live mid-price lookup.

    Returns:
        Trade dataclass with realized_pnl.

    Raises:
        ValueError: If position_id not found in the ledger.
    """
    row = conn.execute(  # type: ignore[union-attr]
        "SELECT * FROM pm_positions WHERE position_id = ?", (position_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Position {position_id} not found")

    token_id = row["token_id"]
    direction = row["direction"]
    size_usd = float(row["size_usd"])
    entry_price = float(row["entry_price"])
    opened_at = float(row["opened_at"])
    condition_id = row["condition_id"]

    exit_price = _get_fill_price(token_id, "no" if direction == "yes" else "yes", client)

    if direction == "yes":
        realized_pnl = (exit_price - entry_price) * size_usd
    else:
        realized_pnl = (entry_price - exit_price) * size_usd

    trade_id = str(uuid.uuid4())
    now = time.time()

    conn.execute(  # type: ignore[union-attr]
        """
        INSERT INTO pm_trades
            (trade_id, condition_id, direction, size_usd,
             entry_price, exit_price, realized_pnl, mode, opened_at, closed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'paper', ?, ?)
        """,
        (trade_id, condition_id, direction, size_usd,
         entry_price, exit_price, realized_pnl, opened_at, now),
    )

    conn.execute(  # type: ignore[union-attr]
        "DELETE FROM pm_positions WHERE position_id = ?", (position_id,)
    )
    conn.commit()  # type: ignore[union-attr]

    logger.info(
        "close_paper_position: %s %s PnL=%.2f",
        direction.upper(),
        condition_id[:12],
        realized_pnl,
    )

    return Trade(
        trade_id=trade_id,
        condition_id=condition_id,
        direction=direction,
        size_usd=size_usd,
        entry_price=entry_price,
        exit_price=exit_price,
        realized_pnl=realized_pnl,
        mode="paper",
        opened_at=opened_at,
        closed_at=now,
    )
