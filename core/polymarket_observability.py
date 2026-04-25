"""
core/polymarket_observability.py — Structured JSON event logging for Polymarket.

Rotates daily to logs/polymarket_YYYY-MM-DD.jsonl.

Event types:
    order_attempt, order_filled, order_rejected,
    position_closed, preflight_failed, hard_limit_hit

Public API:
    log_order_event(event_type, payload, mode)
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from core.logger import logger

_LOG_DIR = Path("logs")

_VALID_EVENTS = frozenset({
    "order_attempt",
    "order_filled",
    "order_rejected",
    "position_closed",
    "preflight_failed",
    "hard_limit_hit",
})


def _log_path(today: str | None = None) -> Path:
    """Return the path for today's JSONL log file."""
    d = today or date.today().isoformat()
    return _LOG_DIR / f"polymarket_{d}.jsonl"


def log_order_event(
    event_type: str,
    payload: dict,
    mode: str = "paper",
    today: str | None = None,
) -> None:
    """Append a structured JSON event to today's Polymarket log file.

    Creates the log directory and file if they don't exist.
    Rotates automatically — each day gets its own file.

    Args:
        event_type: One of the valid event type strings.
        payload: Arbitrary dict of event data to record.
        mode: "paper" or "live".
        today: ISO date string override (for testing); defaults to today.
    """
    if event_type not in _VALID_EVENTS:
        logger.warning("log_order_event: unknown event_type '%s'", event_type)

    record = {
        "ts": time.time(),
        "event": event_type,
        "mode": mode,
        **payload,
    }

    log_path = _log_path(today)
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception as exc:
        logger.error("log_order_event: write failed: %s", exc)
