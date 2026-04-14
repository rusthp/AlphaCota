"""
core/audit_log.py — SHA-256 chained audit log stored in SQLite.

Every event row stores the SHA-256 hash of the previous row's content,
creating a tamper-evident chain. Modifying any past row breaks all
subsequent hashes, detectable via verify_chain().

Database: data/audit.db  (gitignored)

Usage:
    from core.audit_log import log_event, verify_chain, EventType

    log_event(EventType.VAULT_UNLOCKED, {"user": "system"})
    log_event(EventType.ORDER_SIGNED, {"condition_id": "0xabc", "size_usd": 25.0})
    ok, broken_at = verify_chain()
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from enum import StrEnum
from pathlib import Path

_DB_PATH = Path("data/audit.db")


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------


class EventType(StrEnum):
    ORDER_SIGNED = "ORDER_SIGNED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    KILL_SWITCH = "KILL_SWITCH"
    VAULT_UNLOCKED = "VAULT_UNLOCKED"
    CONFIG_CHANGED = "CONFIG_CHANGED"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type  TEXT    NOT NULL,
            payload     TEXT    NOT NULL,
            created_at  REAL    NOT NULL,
            prev_hash   TEXT    NOT NULL,
            row_hash    TEXT    NOT NULL
        )
    """)
    conn.commit()


def _compute_hash(event_type: str, payload: str, created_at: float, prev_hash: str) -> str:
    """SHA-256 over the canonical fields of a row (excluding id and row_hash)."""
    content = f"{event_type}|{payload}|{created_at}|{prev_hash}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _get_last_hash(conn: sqlite3.Connection) -> str:
    """Return the row_hash of the most recent row, or the genesis hash if table is empty."""
    row = conn.execute(
        "SELECT row_hash FROM audit_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        # Genesis hash: SHA-256 of a fixed sentinel string
        return hashlib.sha256(b"alphacota:audit:genesis").hexdigest()
    return row["row_hash"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def log_event(event_type: EventType | str, payload: dict) -> int:
    """
    Append an event to the audit log.

    Args:
        event_type: One of the EventType enum values (or raw string for forward compat).
        payload: Arbitrary dict of event data — serialised to JSON.

    Returns:
        The row id of the inserted event.
    """
    et = event_type.value if isinstance(event_type, EventType) else str(event_type)
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    created_at = time.time()

    conn = _get_conn()
    try:
        _init_db(conn)
        prev_hash = _get_last_hash(conn)
        row_hash = _compute_hash(et, payload_json, created_at, prev_hash)
        cursor = conn.execute(
            """
            INSERT INTO audit_log (event_type, payload, created_at, prev_hash, row_hash)
            VALUES (?, ?, ?, ?, ?)
            """,
            (et, payload_json, created_at, prev_hash, row_hash),
        )
        conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]
    finally:
        conn.close()


def verify_chain() -> tuple[bool, int | None]:
    """
    Walk the entire audit log and verify the SHA-256 chain.

    Returns:
        (True, None)         — chain intact.
        (False, broken_row_id) — first row where the chain is broken.
    """
    conn = _get_conn()
    try:
        _init_db(conn)
        rows = conn.execute(
            "SELECT id, event_type, payload, created_at, prev_hash, row_hash "
            "FROM audit_log ORDER BY id ASC"
        ).fetchall()

        if not rows:
            return True, None

        genesis = hashlib.sha256(b"alphacota:audit:genesis").hexdigest()
        expected_prev = genesis

        for row in rows:
            # Verify prev_hash matches what we expect
            if row["prev_hash"] != expected_prev:
                return False, row["id"]
            # Verify row_hash is consistent with row content
            computed = _compute_hash(
                row["event_type"],
                row["payload"],
                row["created_at"],
                row["prev_hash"],
            )
            if computed != row["row_hash"]:
                return False, row["id"]
            expected_prev = row["row_hash"]

        return True, None
    finally:
        conn.close()


def get_recent_events(limit: int = 50) -> list[dict]:
    """Return the most recent `limit` events in descending order."""
    conn = _get_conn()
    try:
        _init_db(conn)
        rows = conn.execute(
            "SELECT id, event_type, payload, created_at FROM audit_log "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "event_type": r["event_type"],
                "payload": json.loads(r["payload"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    finally:
        conn.close()
