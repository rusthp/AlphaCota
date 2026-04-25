#!/usr/bin/env python3
"""
scripts/remote_seeder.py — Remote wallet seeder worker for the VM.

Runs on the Contabo VM (75.119.138.179). Discovers wallets from Polymarket,
fetches resolved positions, and saves to a local SQLite file on the VM.

The local machine then syncs with:
    python scripts/sync_vm_wallets.py

Usage on the VM:
    python3 remote_seeder.py --wallets 150 --offset 150
    python3 remote_seeder.py --wallets 300 --offset 0 --min-size 5

Cron on VM (every 6h):
    0 */6 * * * python3 /root/remote_seeder.py --wallets 150 --offset 150 >> /var/log/alphacota/seeder.log 2>&1
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests

_DATA_API = "https://data-api.polymarket.com"
_REQUEST_TIMEOUT = 20
_HEADERS = {
    "User-Agent": "AlphaCota/1.0 RemoteWorker",
    "Accept": "application/json",
}
_SLEEP_BETWEEN_WALLETS = 0.35
_MAX_POSITIONS_PER_WALLET = 500
_DB_PATH = Path("/root/alphacota_wallet_cache.db")


@dataclass
class WorkerResult:
    wallets_discovered: int = 0
    wallets_processed: int = 0
    positions_saved: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# DB (same schema as local wallet_cache.db)
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
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


def _upsert(conn: sqlite3.Connection, address: str, market_id: str,
            outcome: str, side: str, size_usd: float, pnl: float, closed_at: float) -> bool:
    cur = conn.execute("""
        INSERT INTO wallet_positions
            (address, market_id, outcome, side, size_usd, pnl, resolved, closed_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(address, market_id) DO UPDATE SET
            pnl=excluded.pnl, size_usd=excluded.size_usd, resolved=1
    """, (address.lower(), market_id, outcome, side,
          round(size_usd, 4), round(pnl, 4), closed_at))
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def _discover_wallets(limit: int, offset_skip: int) -> list[str]:
    seen: set[str] = set()
    api_offset = 0
    batch = 100
    target = offset_skip + limit

    while len(seen) < target:
        try:
            resp = requests.get(f"{_DATA_API}/trades",
                                params={"limit": batch, "offset": api_offset},
                                headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
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
            api_offset += batch
            time.sleep(0.2)
        except Exception as exc:
            print(f"[WARN] _discover_wallets: {exc}")
            break

    all_wallets = list(seen)
    return all_wallets[offset_skip: offset_skip + limit]


def _fetch_positions(address: str) -> list[dict]:
    results: list[dict] = []
    offset = 0
    batch = 100

    while offset < _MAX_POSITIONS_PER_WALLET:
        try:
            resp = requests.get(f"{_DATA_API}/positions",
                                params={"user": address, "limit": batch, "offset": offset},
                                headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
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
            print(f"[DEBUG] _fetch_positions({address[:12]}): {exc}")
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


def _process_wallet(address: str, conn: sqlite3.Connection,
                    min_size_usd: float, result: WorkerResult) -> int:
    positions = _fetch_positions(address)
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
        if cur_price not in (0.0, 1.0):
            continue

        cash_pnl_raw = pos.get("cashPnl")
        cash_pnl = float(cash_pnl_raw) if cash_pnl_raw is not None else 0.0

        outcome = str(pos.get("outcome") or "?")
        outcome_index = int(pos.get("outcomeIndex") or 0)
        side = "YES" if outcome_index == 0 else "NO"
        closed_at = _to_timestamp(pos.get("endDate"))

        if cash_pnl != 0:
            pnl = cash_pnl
        elif cur_price == 0.0:
            pnl = -initial_value
        else:
            avg_price = float(pos.get("avgPrice") or 0.5)
            pnl = initial_value * (1.0 / avg_price - 1.0) if avg_price > 0 else initial_value

        if _upsert(conn, address, condition_id, outcome, side, initial_value, pnl, closed_at):
            new_rows += 1

    result.positions_saved += new_rows
    return new_rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(wallets: int, offset: int, min_size: float, worker_id: str) -> WorkerResult:
    result = WorkerResult()
    conn = _get_conn()

    print(f"[INFO] Worker={worker_id} target={wallets} offset={offset} min_size=${min_size}")
    print(f"[INFO] Saving to {_DB_PATH}")

    addresses = _discover_wallets(limit=wallets, offset_skip=offset)
    result.wallets_discovered = len(addresses)
    print(f"[INFO] Discovered {len(addresses)} wallets")

    for i, address in enumerate(addresses, 1):
        try:
            new_rows = _process_wallet(address, conn, min_size, result)
            if new_rows > 0:
                result.wallets_processed += 1
        except Exception as exc:
            result.errors.append(f"{address[:12]}: {exc}")
            print(f"[WARN] {address[:12]}: {exc}")

        if i % 25 == 0:
            print(f"[INFO] Progress: {i}/{len(addresses)} wallets, {result.positions_saved} positions saved")

        time.sleep(_SLEEP_BETWEEN_WALLETS)

    # Stats
    try:
        row = conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT address FROM wallet_positions WHERE resolved=1
                GROUP BY address HAVING COUNT(*) >= 5
            )
        """).fetchone()
        eligible = int(row[0]) if row else 0
    except Exception:
        eligible = 0

    conn.close()

    print(f"\n{'='*52}")
    print(f"  Worker          : {worker_id}")
    print(f"  Discovered      : {result.wallets_discovered}")
    print(f"  Processed       : {result.wallets_processed}")
    print(f"  Positions saved : {result.positions_saved}")
    print(f"  Eligible (>=5)  : {eligible}")
    if result.errors:
        print(f"  Errors          : {len(result.errors)}")
    print(f"{'='*52}")
    print(f"[INFO] DB ready at {_DB_PATH} — run sync_vm_wallets.py locally to merge")

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AlphaCota remote wallet seeder")
    parser.add_argument("--wallets", type=int, default=150)
    parser.add_argument("--offset", type=int, default=150,
                        help="Skip first N wallets (local takes 0-149, VM takes 150+)")
    parser.add_argument("--min-size", type=float, default=5.0)
    parser.add_argument("--worker-id", default="vm-worker")
    args = parser.parse_args()

    run(wallets=args.wallets, offset=args.offset,
        min_size=args.min_size, worker_id=args.worker_id)
