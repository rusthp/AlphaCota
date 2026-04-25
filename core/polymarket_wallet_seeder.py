"""
core/polymarket_wallet_seeder.py — Discover and seed alpha wallets from resolved markets.

Strategy:
  1. Fetch recent trades from data-api.polymarket.com/trades to discover active wallets
  2. For each wallet, fetch all positions from data-api/positions
  3. A position is resolved when curPrice is exactly 0.0 (lost) or 1.0 (won)
  4. Save resolved positions to wallet_cache.db for rerank_wallets() to consume

Run:
    python -m core.polymarket_wallet_seeder
    python -m core.polymarket_wallet_seeder --wallets 300 --min-size 5
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests

from core.logger import logger

_DATA_API = "https://data-api.polymarket.com"
_CACHE_DB = Path("data/wallet_cache.db")
_REQUEST_TIMEOUT = 20
_HEADERS = {
    "User-Agent": "AlphaCota/1.0 Wallet-Seeder",
    "Accept": "application/json",
}

_SLEEP_BETWEEN_WALLETS = 0.3
_MAX_POSITIONS_PER_WALLET = 500


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class SeedResult:
    wallets_discovered: int = 0
    wallets_processed: int = 0
    positions_saved: int = 0
    wallets_eligible: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------


def _get_cache_conn() -> sqlite3.Connection:
    _CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_CACHE_DB))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wallet_positions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            address     TEXT NOT NULL,
            market_id   TEXT NOT NULL,
            outcome     TEXT NOT NULL,
            side        TEXT NOT NULL,
            size_usd    REAL NOT NULL,
            pnl         REAL NOT NULL DEFAULT 0.0,
            resolved    INTEGER NOT NULL DEFAULT 0,
            closed_at   REAL NOT NULL DEFAULT 0.0,
            UNIQUE(address, market_id)
        )
    """)
    conn.commit()
    return conn


def _upsert_position(
    conn: sqlite3.Connection,
    address: str,
    market_id: str,
    outcome: str,
    side: str,
    size_usd: float,
    pnl: float,
    closed_at: float,
) -> bool:
    cur = conn.execute(
        """
        INSERT INTO wallet_positions
            (address, market_id, outcome, side, size_usd, pnl, resolved, closed_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(address, market_id) DO UPDATE SET
            pnl=excluded.pnl,
            size_usd=excluded.size_usd,
            resolved=1
        """,
        (address.lower(), market_id, outcome, side,
         round(size_usd, 4), round(pnl, 4), closed_at),
    )
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# API fetchers
# ---------------------------------------------------------------------------


def _discover_wallets(limit: int = 300) -> list[str]:
    """Return unique proxyWallet addresses from recent public trades."""
    seen: set[str] = set()
    offset = 0
    batch = 100

    while len(seen) < limit:
        try:
            resp = requests.get(
                f"{_DATA_API}/trades",
                params={"limit": batch, "offset": offset},
                headers=_HEADERS,
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                break
            trades = resp.json()
            if not trades:
                break
            for t in trades:
                addr = (t.get("proxyWallet") or "").lower()
                if addr.startswith("0x"):
                    seen.add(addr)
            if len(trades) < batch:
                break
            offset += batch
            time.sleep(0.2)
        except Exception as exc:
            logger.warning("_discover_wallets: %s", exc)
            break

    return list(seen)


def _fetch_wallet_positions(address: str) -> list[dict]:
    """Fetch all positions for a wallet from data-api."""
    results: list[dict] = []
    offset = 0
    batch = 100

    while offset < _MAX_POSITIONS_PER_WALLET:
        try:
            resp = requests.get(
                f"{_DATA_API}/positions",
                params={"user": address, "limit": batch, "offset": offset},
                headers=_HEADERS,
                timeout=_REQUEST_TIMEOUT,
            )
            if resp.status_code != 200:
                break
            chunk = resp.json()
            if not chunk:
                break
            results.extend(chunk)
            if len(chunk) < batch:
                break
            offset += batch
        except Exception as exc:
            logger.debug("_fetch_wallet_positions(%s): %s", address[:12], exc)
            break

    return results


def _to_timestamp(date_str: str | None) -> float:
    if not date_str:
        return time.time()
    try:
        s = str(date_str).strip()
        if "T" in s:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return time.time()


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def _process_wallet(
    address: str,
    conn: sqlite3.Connection,
    min_size_usd: float,
    result: SeedResult,
) -> int:
    positions = _fetch_wallet_positions(address)
    new_rows = 0

    for pos in positions:
        condition_id = pos.get("conditionId", "")
        if not condition_id:
            continue

        initial_value = float(pos.get("initialValue") or 0)
        if initial_value < min_size_usd:
            continue

        cur_price_raw = pos.get("curPrice")
        cur_price = float(cur_price_raw) if cur_price_raw is not None else -1.0

        # Only resolved positions: curPrice settled to exactly 0 (lost) or 1 (won)
        if cur_price not in (0.0, 1.0):
            continue

        cash_pnl_raw = pos.get("cashPnl")
        cash_pnl = float(cash_pnl_raw) if cash_pnl_raw is not None else 0.0

        outcome = str(pos.get("outcome") or "?")
        outcome_index = int(pos.get("outcomeIndex") or 0)
        side = "YES" if outcome_index == 0 else "NO"
        closed_at = _to_timestamp(pos.get("endDate"))

        # PnL: cashPnl from API is ground truth.
        # curPrice==1 → winner (pnl = size * (1/avgPrice - 1) approx, use cashPnl or size)
        # curPrice==0 → loser (pnl = -initialValue)
        if cash_pnl != 0:
            pnl = cash_pnl
        elif cur_price == 0.0:
            pnl = -initial_value
        else:
            # curPrice==1, cashPnl==0: not yet redeemed, estimate win
            avg_price = float(pos.get("avgPrice") or 0.5)
            pnl = initial_value * (1.0 / avg_price - 1.0) if avg_price > 0 else initial_value

        is_new = _upsert_position(
            conn,
            address=address,
            market_id=condition_id,
            outcome=outcome,
            side=side,
            size_usd=initial_value,
            pnl=pnl,
            closed_at=closed_at,
        )
        if is_new:
            new_rows += 1

    result.positions_saved += new_rows
    return new_rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def seed_wallets(wallets: int = 300, min_size_usd: float = 5.0) -> SeedResult:
    """Discover active wallets and persist their resolved positions.

    Args:
        wallets: Max unique wallets to process.
        min_size_usd: Minimum position initial value in USD.

    Returns:
        SeedResult with counts.
    """
    result = SeedResult()
    conn = _get_cache_conn()

    logger.info("Discovering wallets (target=%d, min_size=$%.0f)...", wallets, min_size_usd)
    addresses = _discover_wallets(limit=wallets)
    result.wallets_discovered = len(addresses)
    logger.info("Found %d unique wallets in recent trades", len(addresses))

    for i, address in enumerate(addresses[:wallets], 1):
        try:
            new_rows = _process_wallet(address, conn, min_size_usd, result)
            if new_rows > 0:
                result.wallets_processed += 1
        except Exception as exc:
            result.errors.append(f"{address[:12]}: {exc}")
            logger.warning("seed_wallets wallet=%s: %s", address[:12], exc)

        if i % 25 == 0:
            logger.info("Progress: %d/%d wallets, %d positions saved",
                        i, len(addresses), result.positions_saved)

        time.sleep(_SLEEP_BETWEEN_WALLETS)

    # Count eligible wallets
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT address FROM wallet_positions
                WHERE resolved = 1
                GROUP BY address HAVING COUNT(*) >= 5
            )
            """
        ).fetchone()
        result.wallets_eligible = int(row[0]) if row else 0
    except Exception:
        pass

    conn.close()
    logger.info(
        "Seed complete: %d wallets processed, %d positions, %d eligible",
        result.wallets_processed, result.positions_saved, result.wallets_eligible,
    )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed Polymarket alpha wallets")
    parser.add_argument("--wallets", type=int, default=300,
                        help="Max unique wallets to process (default: 300)")
    parser.add_argument("--min-size", type=float, default=5.0,
                        help="Minimum position size USD (default: 5.0)")
    args = parser.parse_args()

    res = seed_wallets(wallets=args.wallets, min_size_usd=args.min_size)

    sep = "=" * 52
    print(f"\n{sep}")
    print(f"  Wallets descobertas : {res.wallets_discovered}")
    print(f"  Wallets processadas : {res.wallets_processed}")
    print(f"  Posicoes salvas     : {res.positions_saved}")
    print(f"  Wallets elegiveis   : {res.wallets_eligible}  (>=5 resolvidos)")
    if res.errors:
        print(f"  Erros               : {len(res.errors)}")
    print(f"{sep}\n")
    if res.wallets_eligible > 0:
        print("Aba 'Copiar' no dashboard ja mostra o ranking.")
    else:
        print("Tente --wallets 500 para encontrar mais traders.")
