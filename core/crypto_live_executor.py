"""
core/crypto_live_executor.py — Live Binance executor for crypto signals.

Sends real orders to Binance Spot via HMAC-signed REST calls (no third-party
SDK — raw httpx, same pattern as crypto_data_engine.py).

Environment variables required:
    BINANCE_API_KEY    — API key (read + spot trading)
    BINANCE_API_SECRET — HMAC-SHA256 secret

Public API:
    execute_live(signal, size_usd, conn) -> CryptoOrder
    close_live_position(position_id, current_price, reason, conn) -> CryptoTrade
    get_account_balance(asset) -> float
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import time
import urllib.parse
import uuid
from typing import Any

import httpx

from core.crypto_types import CryptoOrder, CryptoPosition, CryptoSignal, CryptoTrade
from core.logger import logger

_BASE = "https://api.binance.com"
_TIMEOUT = 10.0

# Minimum order sizes (USD notional) per symbol — Binance enforces MIN_NOTIONAL
_MIN_NOTIONAL: dict[str, float] = {
    "BTCUSDT": 5.0,
    "ETHUSDT": 5.0,
    "SOLUSDT": 5.0,
    "BNBUSDT": 5.0,
}
_DEFAULT_MIN_NOTIONAL = 5.0


def _api_key() -> str:
    key = os.getenv("BINANCE_API_KEY", "")
    if not key:
        raise RuntimeError("BINANCE_API_KEY is not set in environment")
    return key


def _api_secret() -> str:
    secret = os.getenv("BINANCE_API_SECRET", "")
    if not secret:
        raise RuntimeError("BINANCE_API_SECRET is not set in environment")
    return secret


def _sign(params: dict[str, Any]) -> str:
    """Return HMAC-SHA256 signature for the given query parameters."""
    query = urllib.parse.urlencode(params)
    return hmac.new(
        _api_secret().encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _signed_get(path: str, params: dict[str, Any] | None = None) -> Any:
    p = dict(params or {})
    p["timestamp"] = int(time.time() * 1000)
    p["signature"] = _sign(p)
    headers = {"X-MBX-APIKEY": _api_key()}
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(f"{_BASE}{path}", params=p, headers=headers)
        resp.raise_for_status()
        return resp.json()


def _signed_post(path: str, params: dict[str, Any]) -> Any:
    p = dict(params)
    p["timestamp"] = int(time.time() * 1000)
    p["signature"] = _sign(p)
    headers = {"X-MBX-APIKEY": _api_key()}
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(f"{_BASE}{path}", params=p, headers=headers)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_account_balance(asset: str = "USDT") -> float:
    """Return available balance for *asset* from Binance account.

    Args:
        asset: e.g. "USDT", "BTC", "ETH"

    Returns:
        Free (available) balance as float. Returns 0.0 if asset not found.
    """
    data = _signed_get("/api/v3/account")
    for b in data.get("balances", []):
        if b["asset"] == asset:
            return float(b["free"])
    return 0.0


def _usdt_qty_to_asset_qty(symbol: str, size_usd: float, price: float) -> str:
    """Convert a USD notional to asset quantity string for Binance.

    Binance requires quantity in base asset (e.g. BTC for BTCUSDT).
    Uses 6 decimal places — Binance filters will reject if < stepSize but
    this is conservative enough for major pairs.
    """
    qty = size_usd / price
    # Use 5 significant decimal places — works for BTC (0.00001 step)
    return f"{qty:.5f}"


def execute_live(
    signal: CryptoSignal,
    size_usd: float,
    conn: sqlite3.Connection,
) -> CryptoOrder:
    """Submit a real MARKET order to Binance and record it in the ledger.

    Args:
        signal: A non-flat CryptoSignal to act on.
        size_usd: USD notional. Must exceed MIN_NOTIONAL for the symbol.
        conn: Open sqlite3 connection with init_crypto_db applied.

    Returns:
        A CryptoOrder with status='filled' and the actual fill price.

    Raises:
        ValueError: If signal is flat or size_usd is below minimum.
        RuntimeError: If BINANCE_API_KEY / BINANCE_API_SECRET are missing.
        httpx.HTTPError: On Binance API errors (propagated for caller to handle).
    """
    if signal.direction == "flat":
        raise ValueError("execute_live: cannot execute a flat signal")

    min_notional = _MIN_NOTIONAL.get(signal.symbol, _DEFAULT_MIN_NOTIONAL)
    if size_usd < min_notional:
        raise ValueError(
            f"execute_live: size_usd={size_usd:.2f} < MIN_NOTIONAL={min_notional} "
            f"for {signal.symbol}"
        )

    side = "BUY" if signal.direction == "long" else "SELL"
    qty_str = _usdt_qty_to_asset_qty(signal.symbol, size_usd, signal.entry_price)

    logger.info(
        "execute_live: placing %s MARKET %s qty=%s (~$%.2f)",
        side, signal.symbol, qty_str, size_usd,
    )

    result = _signed_post("/api/v3/order", {
        "symbol": signal.symbol,
        "side": side,
        "type": "MARKET",
        "quantity": qty_str,
        "newOrderRespType": "FULL",
    })

    binance_order_id = str(result.get("orderId", ""))
    # Average fill price from fills (weighted)
    fills = result.get("fills", [])
    if fills:
        total_qty = sum(float(f["qty"]) for f in fills)
        fill_price = sum(float(f["price"]) * float(f["qty"]) for f in fills) / total_qty
    else:
        fill_price = signal.entry_price  # fallback — should not happen for MARKET

    order_id = str(uuid.uuid4())
    position_id = str(uuid.uuid4())
    now = time.time()
    pos_side = "long" if signal.direction == "long" else "short"

    try:
        conn.execute(
            """
            INSERT INTO crypto_orders
                (id, symbol, side, qty, price, status, mode, created_at)
            VALUES (?, ?, ?, ?, ?, 'filled', 'live', ?)
            """,
            (order_id, signal.symbol, side.lower(), size_usd, fill_price, now),
        )
        conn.execute(
            """
            INSERT INTO crypto_positions
                (id, symbol, side, entry_price, qty_usd, stop_loss, take_profit,
                 opened_at, mode, exchange_order_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'live', ?)
            """,
            (
                position_id,
                signal.symbol,
                pos_side,
                fill_price,
                size_usd,
                signal.stop_loss,
                signal.take_profit,
                now,
                binance_order_id,
            ),
        )
        conn.commit()
    except sqlite3.Error as exc:
        logger.error("execute_live: db error after fill — %s", exc)
        raise

    logger.info(
        "execute_live: filled %s %s @ %.8f (order=%s)",
        side, signal.symbol, fill_price, binance_order_id,
    )

    return CryptoOrder(
        id=order_id,
        symbol=signal.symbol,
        side="buy" if side == "BUY" else "sell",
        qty=size_usd,
        price=fill_price,
        status="filled",
        mode="live",
        created_at=now,
    )


def close_live_position(
    position_id: str,
    current_price: float,
    reason: str,
    conn: sqlite3.Connection,
) -> CryptoTrade:
    """Send a closing MARKET order and record the realised trade in the ledger.

    Args:
        position_id: UUID of the open position in crypto_positions.
        current_price: Latest market price (used for PnL calc if fills unavailable).
        reason: Exit reason string (e.g. 'sl_hit', 'tp_hit', 'signal_flip').
        conn: Open sqlite3 connection.

    Returns:
        A CryptoTrade with realised PnL.

    Raises:
        ValueError: If position_id not found or price is invalid.
        httpx.HTTPError: On Binance API errors.
    """
    if current_price <= 0.0:
        raise ValueError(f"close_live_position: bad current_price {current_price}")

    row = conn.execute(
        "SELECT * FROM crypto_positions WHERE id = ?", (position_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"close_live_position: position {position_id} not found")

    symbol = row["symbol"]
    side = row["side"]
    entry_price = float(row["entry_price"])
    qty_usd = float(row["qty_usd"])
    opened_at = float(row["opened_at"])

    # Closing side is opposite of position side
    close_side = "SELL" if side == "long" else "BUY"
    qty_str = _usdt_qty_to_asset_qty(symbol, qty_usd, entry_price)

    logger.info(
        "close_live_position: placing %s MARKET %s qty=%s reason=%s",
        close_side, symbol, qty_str, reason,
    )

    result = _signed_post("/api/v3/order", {
        "symbol": symbol,
        "side": close_side,
        "type": "MARKET",
        "quantity": qty_str,
        "newOrderRespType": "FULL",
    })

    fills = result.get("fills", [])
    if fills:
        total_qty = sum(float(f["qty"]) for f in fills)
        exit_price = sum(float(f["price"]) * float(f["qty"]) for f in fills) / total_qty
    else:
        exit_price = current_price

    if side == "long":
        pnl = qty_usd * (exit_price - entry_price) / entry_price
    else:
        pnl = qty_usd * (entry_price - exit_price) / entry_price

    pnl_pct = pnl / qty_usd
    now = time.time()
    trade_id = str(uuid.uuid4())

    try:
        conn.execute(
            """
            INSERT INTO crypto_trades
                (id, symbol, side, entry_price, exit_price, qty_usd,
                 realized_pnl, pnl_pct, opened_at, closed_at, exit_reason, mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'live')
            """,
            (
                trade_id, symbol, side, entry_price, exit_price, qty_usd,
                pnl, pnl_pct, opened_at, now, reason,
            ),
        )
        conn.execute("DELETE FROM crypto_positions WHERE id = ?", (position_id,))
        conn.commit()
    except sqlite3.Error as exc:
        logger.error("close_live_position: db error — %s", exc)
        raise

    logger.info(
        "close_live_position: %s %s exit=%.8f pnl=%.2f (%.2f%%) reason=%s",
        side.upper(), symbol, exit_price, pnl, pnl_pct * 100.0, reason,
    )

    return CryptoTrade(
        id=trade_id,
        symbol=symbol,
        side="long" if side == "long" else "short",
        entry_price=entry_price,
        exit_price=exit_price,
        qty=qty_usd,
        pnl=round(pnl, 6),
        pnl_pct=round(pnl_pct, 6),
        opened_at=opened_at,
        closed_at=now,
        reason=reason,
    )
