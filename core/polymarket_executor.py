"""
core/polymarket_executor.py — Live order execution via Polymarket CLOB.

Hard limits (non-configurable):
    MAX_POSITION_USD = 50.0   — maximum single position size
    MAX_DAILY_LOSS_USD = 10.0 — maximum realized loss per day

Public API:
    execute_live(decision, conn, client) -> Order
    close_live_position(position_id, conn, client) -> Trade
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from core.logger import logger
from core.polymarket_ledger import insert_order_if_new
from core.polymarket_types import Order, Trade, TradeDecision

MAX_POSITION_USD = 50.0
MAX_DAILY_LOSS_USD = 10.0
_KILL_FILE = Path("data/POLYMARKET_KILL")
_POLL_INTERVAL = 2.0
_POLL_TIMEOUT = 60.0


class HardLimitExceeded(Exception):
    pass


def _check_daily_loss(conn: object) -> float:
    """Return today's realized loss (negative value means loss)."""
    from datetime import date
    today = date.today().isoformat()
    try:
        result = conn.execute(  # type: ignore[union-attr]
            "SELECT COALESCE(SUM(realized_pnl), 0) FROM pm_trades "
            "WHERE mode='live' AND date(closed_at, 'unixepoch') = ?",
            (today,),
        ).fetchone()[0]
        return float(result)
    except Exception:
        return 0.0


def execute_live(
    decision: TradeDecision,
    conn: object,
    client: object,
) -> Order:
    """Execute a live GTC limit order on the Polymarket CLOB.

    Hard limits are enforced before signing:
    - decision.size_usd must be ≤ MAX_POSITION_USD (50 USD)
    - daily realized loss must not exceed MAX_DAILY_LOSS_USD (10 USD)

    Flow:
    1. Enforce hard limits.
    2. Get mid-price from order book.
    3. Build and sign GTC limit order via py-clob-client.
    4. Submit to CLOB /order endpoint.
    5. Poll /order/{id} until filled or 60s timeout.
    6. Record in ledger with mode='live'.

    Args:
        decision: TradeDecision from the decision engine.
        conn: Open sqlite3 ledger connection.
        client: Authenticated py-clob-client ClobClient instance.

    Returns:
        Order dataclass with fill_price and status.

    Raises:
        HardLimitExceeded: If any hard limit would be breached.
        RuntimeError: If the CLOB order submission or polling fails.
    """
    if decision.size_usd > MAX_POSITION_USD:
        raise HardLimitExceeded(
            f"Position size ${decision.size_usd:.2f} exceeds hard limit ${MAX_POSITION_USD:.2f}"
        )

    daily_pnl = _check_daily_loss(conn)
    if daily_pnl < -MAX_DAILY_LOSS_USD:
        raise HardLimitExceeded(
            f"Daily loss ${abs(daily_pnl):.2f} exceeds hard limit ${MAX_DAILY_LOSS_USD:.2f}"
        )

    from core.polymarket_client import get_order_book

    book = get_order_book(decision.token_id)
    if decision.direction == "yes":
        limit_price = round(min(book.mid_price + book.spread_pct / 2.0, 0.99), 4)
    else:
        limit_price = round(max(book.mid_price - book.spread_pct / 2.0, 0.01), 4)

    client_order_id = str(uuid.uuid4())
    now = time.time()

    try:
        order_args = {
            "token_id": decision.token_id,
            "price": limit_price,
            "size": decision.size_usd,
            "side": "BUY" if decision.direction == "yes" else "SELL",
            "time_in_force": "GTC",
        }
        response = client.create_and_post_order(order_args)  # type: ignore[union-attr]
        exchange_order_id = response.get("orderID") or response.get("id") or client_order_id
    except Exception as exc:
        raise RuntimeError(f"CLOB order submission failed: {exc}") from exc

    insert_order_if_new(
        conn,  # type: ignore[arg-type]
        client_order_id=exchange_order_id,
        condition_id=decision.condition_id,
        token_id=decision.token_id,
        direction=decision.direction,
        size_usd=decision.size_usd,
        limit_price=limit_price,
        mode="live",
    )

    fill_price = limit_price
    status = "pending"
    deadline = now + _POLL_TIMEOUT

    while time.time() < deadline:
        try:
            order_info = client.get_order(exchange_order_id)  # type: ignore[union-attr]
            clob_status = (order_info.get("status") or "").lower()
            if clob_status in ("filled", "matched"):
                status = "filled"
                fill_price = float(order_info.get("avgPrice") or limit_price)
                break
            if clob_status in ("cancelled", "rejected"):
                status = clob_status
                break
        except Exception as exc:
            logger.warning("execute_live: poll error: %s", exc)
        time.sleep(_POLL_INTERVAL)

    conn.execute(  # type: ignore[union-attr]
        "UPDATE pm_orders SET status=?, fill_price=?, updated_at=? WHERE client_order_id=?",
        (status, fill_price, time.time(), exchange_order_id),
    )
    conn.commit()  # type: ignore[union-attr]

    logger.info(
        "execute_live: %s %s %.2f USDC @ %.4f status=%s",
        decision.direction.upper(), decision.condition_id[:12],
        decision.size_usd, fill_price, status,
    )

    return Order(
        client_order_id=exchange_order_id,
        condition_id=decision.condition_id,
        token_id=decision.token_id,
        direction=decision.direction,
        size_usd=decision.size_usd,
        fill_price=fill_price,
        status=status,
        mode="live",
        created_at=now,
    )


def close_live_position(
    position_id: str,
    conn: object,
    client: object,
) -> Trade:
    """Close a live position with a market sell order.

    Refuses to execute if the kill-switch file is present.

    Args:
        position_id: UUID of the pm_positions row to close.
        conn: Open sqlite3 ledger connection.
        client: Authenticated py-clob-client ClobClient instance.

    Returns:
        Trade dataclass with realized_pnl.

    Raises:
        RuntimeError: If kill-switch is active or CLOB call fails.
        ValueError: If position_id not found.
    """
    if _KILL_FILE.exists():
        raise RuntimeError("Kill-switch active — refusing to close live position")

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

    exit_direction = "SELL" if direction == "yes" else "BUY"
    try:
        from core.polymarket_client import get_order_book
        book = get_order_book(token_id)
        exit_price = book.bids[0].price if book.bids else book.mid_price
    except Exception as exc:
        logger.warning("close_live_position: price fetch failed: %s", exc)
        exit_price = entry_price

    try:
        client.create_and_post_order({  # type: ignore[union-attr]
            "token_id": token_id,
            "price": exit_price,
            "size": size_usd,
            "side": exit_direction,
            "time_in_force": "FOK",
        })
    except Exception as exc:
        raise RuntimeError(f"CLOB close order failed: {exc}") from exc

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
        VALUES (?, ?, ?, ?, ?, ?, ?, 'live', ?, ?)
        """,
        (trade_id, condition_id, direction, size_usd,
         entry_price, exit_price, realized_pnl, opened_at, now),
    )
    conn.execute(  # type: ignore[union-attr]
        "DELETE FROM pm_positions WHERE position_id = ?", (position_id,)
    )
    conn.commit()  # type: ignore[union-attr]

    logger.info(
        "close_live_position: %s PnL=%.2f", condition_id[:12], realized_pnl
    )

    return Trade(
        trade_id=trade_id,
        condition_id=condition_id,
        direction=direction,
        size_usd=size_usd,
        entry_price=entry_price,
        exit_price=exit_price,
        realized_pnl=realized_pnl,
        mode="live",
        opened_at=opened_at,
        closed_at=now,
    )
