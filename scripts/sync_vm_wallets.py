#!/usr/bin/env python3
"""
scripts/sync_vm_wallets.py — Download and merge VM wallet DB into local wallet_cache.db.

Run locally after the VM seeder finishes:
    python scripts/sync_vm_wallets.py

Or schedule locally every 6h (after VM cron runs):
    # Windows Task Scheduler or manual
    python scripts/sync_vm_wallets.py --vm-host root@75.119.138.179
"""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import tempfile
from pathlib import Path

_LOCAL_DB = Path("data/wallet_cache.db")
_VM_DB_PATH = "/root/alphacota_wallet_cache.db"
_SSH_KEY = "~/.ssh/id_ed25519"


def download_vm_db(vm_host: str, ssh_key: str) -> Path:
    """SCP the VM database to a temp file. Returns local temp path."""
    tmp = Path(tempfile.mktemp(suffix=".db", prefix="vm_wallet_"))
    cmd = [
        "scp", "-i", ssh_key, "-o", "ConnectTimeout=10",
        f"{vm_host}:{_VM_DB_PATH}",
        str(tmp),
    ]
    print(f"[INFO] Downloading {vm_host}:{_VM_DB_PATH} ...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"scp failed: {result.stderr.strip()}")
    print(f"[INFO] Downloaded to {tmp} ({tmp.stat().st_size:,} bytes)")
    return tmp


def merge_dbs(vm_db_path: Path, local_db_path: Path) -> tuple[int, int]:
    """Merge all rows from vm_db into local_db using UPSERT. Returns (merged, skipped)."""
    vm_conn = sqlite3.connect(str(vm_db_path))
    vm_conn.row_factory = sqlite3.Row

    local_db_path.parent.mkdir(parents=True, exist_ok=True)
    local_conn = sqlite3.connect(str(local_db_path))
    local_conn.execute("PRAGMA journal_mode=WAL")

    # Ensure table exists in local DB
    local_conn.execute("""
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
    local_conn.commit()

    rows = vm_conn.execute("SELECT * FROM wallet_positions WHERE resolved=1").fetchall()
    print(f"[INFO] VM DB has {len(rows)} resolved positions to merge")

    merged = 0
    skipped = 0
    for row in rows:
        try:
            cur = local_conn.execute("""
                INSERT INTO wallet_positions
                    (address, market_id, outcome, side, size_usd, pnl, resolved, closed_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(address, market_id) DO UPDATE SET
                    pnl=excluded.pnl,
                    size_usd=excluded.size_usd,
                    resolved=1
            """, (row["address"], row["market_id"], row["outcome"], row["side"],
                  row["size_usd"], row["pnl"], row["closed_at"]))
            if cur.rowcount > 0:
                merged += 1
            else:
                skipped += 1
        except Exception as exc:
            print(f"[WARN] row {row['address'][:12]}/{row['market_id'][:12]}: {exc}")
            skipped += 1

    local_conn.commit()

    # Final stats
    total = local_conn.execute("SELECT COUNT(*) FROM wallet_positions").fetchone()[0]
    wins = local_conn.execute("SELECT COUNT(*) FROM wallet_positions WHERE pnl > 0").fetchone()[0]
    losses = local_conn.execute("SELECT COUNT(*) FROM wallet_positions WHERE pnl < 0").fetchone()[0]
    eligible = local_conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT address FROM wallet_positions WHERE resolved=1
            GROUP BY address HAVING COUNT(*) >= 5
        )
    """).fetchone()[0]

    vm_conn.close()
    local_conn.close()

    print(f"\n{'='*52}")
    print(f"  Merged (new/updated) : {merged}")
    print(f"  Skipped (unchanged)  : {skipped}")
    print(f"  Total no DB local    : {total}")
    print(f"  Wins / Losses        : {wins} / {losses}")
    if total > 0:
        print(f"  Win rate             : {wins/total:.1%}")
    print(f"  Elegiveis (>=5)      : {eligible}")
    print(f"{'='*52}")

    return merged, skipped


def main():
    parser = argparse.ArgumentParser(description="Merge VM wallet DB into local DB")
    parser.add_argument("--vm-host", default="root@75.119.138.179")
    parser.add_argument("--ssh-key", default=_SSH_KEY)
    parser.add_argument("--local-db", default=str(_LOCAL_DB))
    parser.add_argument("--vm-db", default=_VM_DB_PATH)
    args = parser.parse_args()

    try:
        vm_tmp = download_vm_db(args.vm_host, args.ssh_key)
        merged, skipped = merge_dbs(vm_tmp, Path(args.local_db))
        vm_tmp.unlink(missing_ok=True)
        print(f"\n[OK] Sync complete — {merged} positions merged from VM")
    except Exception as exc:
        print(f"[ERR] Sync failed: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
