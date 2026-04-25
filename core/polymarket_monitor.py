"""
core/polymarket_monitor.py — Position monitoring and PnL refresh.

Public API:
    monitor_positions(conn, client) -> list[PositionStatus]
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from core.logger import logger

_TAKE_PROFIT_PCT = 0.50   # +50% on position value
_STOP_LOSS_PCT = -0.30    # -30% on position value


@dataclass(frozen=True)
class PositionStatus:
    position_id: str
    condition_id: str
    direction: str
    size_usd: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pct: float
    should_take_profit: bool
    should_stop_loss: bool
    days_to_resolution: float


def monitor_positions(
    conn: object,
    client: object | None = None,
) -> list[PositionStatus]:
    """Refresh mid-price for all open positions and flag exit conditions.

    For each open position in pm_positions:
    - Fetches current mid-price (falls back to last recorded price).
    - Computes unrealized PnL and PnL%.
    - Flags take-profit (unrealized_pct ≥ +50%) or stop-loss (≤ -30%).
    - Updates pm_positions with current_price and unrealized_pnl.

    Args:
        conn: Open sqlite3 ledger connection.
        client: Optional CLOB client for live price lookup.

    Returns:
        List of PositionStatus for each open position.
    """
    rows = conn.execute("SELECT * FROM pm_positions").fetchall()  # type: ignore[union-attr]
    if not rows:
        return []

    statuses: list[PositionStatus] = []
    now = time.time()

    for row in rows:
        position_id = row["position_id"]
        token_id = row["token_id"]
        direction = row["direction"]
        size_usd = float(row["size_usd"])
        entry_price = float(row["entry_price"])
        current_stored = float(row["current_price"])

        current_price = _fetch_price(token_id, current_stored, client)

        if direction == "yes":
            unrealized_pnl = (current_price - entry_price) * size_usd
        else:
            unrealized_pnl = (entry_price - current_price) * size_usd

        unrealized_pct = unrealized_pnl / (entry_price * size_usd) if entry_price > 0 else 0.0

        take_profit = unrealized_pct >= _TAKE_PROFIT_PCT
        stop_loss = unrealized_pct <= _STOP_LOSS_PCT

        try:
            conn.execute(  # type: ignore[union-attr]
                """
                UPDATE pm_positions
                SET current_price = ?, unrealized_pnl = ?, updated_at = ?
                WHERE position_id = ?
                """,
                (current_price, unrealized_pnl, now, position_id),
            )
        except Exception as exc:
            logger.warning("monitor_positions: update failed for %s: %s", position_id, exc)

        days = _days_remaining(row)

        statuses.append(
            PositionStatus(
                position_id=position_id,
                condition_id=row["condition_id"],
                direction=direction,
                size_usd=size_usd,
                entry_price=entry_price,
                current_price=current_price,
                unrealized_pnl=round(unrealized_pnl, 4),
                unrealized_pct=round(unrealized_pct, 4),
                should_take_profit=take_profit,
                should_stop_loss=stop_loss,
                days_to_resolution=days,
            )
        )

    conn.commit()  # type: ignore[union-attr]
    return statuses


def _fetch_price(token_id: str, fallback: float, client: object | None) -> float:
    """Get current mid-price, falling back to stored price on error."""
    try:
        from core.polymarket_client import get_mid_price
        return get_mid_price(token_id)
    except Exception as exc:
        logger.debug("monitor_positions: price fetch failed for %s: %s", token_id, exc)
        return fallback


def _days_remaining(row: object) -> float:
    """Compute days to resolution from pm_positions row."""
    return 0.0
