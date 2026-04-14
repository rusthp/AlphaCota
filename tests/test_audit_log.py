"""Tests for core/audit_log.py"""

import json
import sqlite3
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def tmp_audit_db(tmp_path, monkeypatch):
    """Redirect audit DB to a temp directory for each test."""
    import core.audit_log as al
    db_path = tmp_path / "data" / "audit.db"
    monkeypatch.setattr(al, "_DB_PATH", db_path)
    yield db_path


# ---------------------------------------------------------------------------
# log_event basics
# ---------------------------------------------------------------------------


def test_log_event_returns_row_id():
    from core.audit_log import log_event, EventType
    row_id = log_event(EventType.VAULT_UNLOCKED, {"user": "system"})
    assert isinstance(row_id, int)
    assert row_id >= 1


def test_log_event_stores_payload():
    from core.audit_log import log_event, get_recent_events, EventType
    log_event(EventType.ORDER_SIGNED, {"condition_id": "0xabc", "size_usd": 25.0})
    events = get_recent_events(limit=1)
    assert events[0]["event_type"] == "ORDER_SIGNED"
    assert events[0]["payload"]["condition_id"] == "0xabc"
    assert events[0]["payload"]["size_usd"] == 25.0


def test_all_event_types_accepted():
    from core.audit_log import log_event, EventType
    for et in EventType:
        row_id = log_event(et, {"test": True})
        assert row_id >= 1


def test_multiple_events_ordered():
    from core.audit_log import log_event, get_recent_events, EventType
    log_event(EventType.ORDER_SIGNED, {"seq": 1})
    log_event(EventType.ORDER_SUBMITTED, {"seq": 2})
    log_event(EventType.ORDER_CANCELLED, {"seq": 3})
    events = get_recent_events(limit=10)
    # get_recent_events returns descending order
    seqs = [e["payload"]["seq"] for e in events]
    assert seqs == [3, 2, 1]


# ---------------------------------------------------------------------------
# Chain integrity
# ---------------------------------------------------------------------------


def test_verify_chain_empty_db():
    from core.audit_log import verify_chain
    ok, broken_at = verify_chain()
    assert ok is True
    assert broken_at is None


def test_verify_chain_intact():
    from core.audit_log import log_event, verify_chain, EventType
    log_event(EventType.VAULT_UNLOCKED, {})
    log_event(EventType.ORDER_SIGNED, {"a": 1})
    log_event(EventType.KILL_SWITCH, {"reason": "test"})
    ok, broken_at = verify_chain()
    assert ok is True
    assert broken_at is None


def test_verify_chain_detects_payload_tamper(tmp_audit_db):
    from core.audit_log import log_event, verify_chain, EventType
    log_event(EventType.ORDER_SIGNED, {"size_usd": 10.0})
    log_event(EventType.ORDER_SUBMITTED, {"order_id": "abc"})

    # Directly tamper with the payload of row 1
    conn = sqlite3.connect(str(tmp_audit_db))
    conn.execute(
        "UPDATE audit_log SET payload = ? WHERE id = 1",
        (json.dumps({"size_usd": 999.0}),),
    )
    conn.commit()
    conn.close()

    ok, broken_at = verify_chain()
    assert ok is False
    assert broken_at == 1


def test_verify_chain_detects_prev_hash_tamper(tmp_audit_db):
    from core.audit_log import log_event, verify_chain, EventType
    log_event(EventType.VAULT_UNLOCKED, {})
    log_event(EventType.CONFIG_CHANGED, {"key": "val"})

    # Tamper with prev_hash of row 2
    conn = sqlite3.connect(str(tmp_audit_db))
    conn.execute(
        "UPDATE audit_log SET prev_hash = 'deadbeef' WHERE id = 2"
    )
    conn.commit()
    conn.close()

    ok, broken_at = verify_chain()
    assert ok is False
    assert broken_at == 2


def test_verify_chain_detects_row_hash_tamper(tmp_audit_db):
    from core.audit_log import log_event, verify_chain, EventType
    log_event(EventType.KILL_SWITCH, {"source": "api"})

    conn = sqlite3.connect(str(tmp_audit_db))
    conn.execute(
        "UPDATE audit_log SET row_hash = 'fakehash' WHERE id = 1"
    )
    conn.commit()
    conn.close()

    ok, broken_at = verify_chain()
    assert ok is False
    assert broken_at == 1


# ---------------------------------------------------------------------------
# get_recent_events
# ---------------------------------------------------------------------------


def test_get_recent_events_limit():
    from core.audit_log import log_event, get_recent_events, EventType
    for i in range(10):
        log_event(EventType.ORDER_SIGNED, {"i": i})
    events = get_recent_events(limit=3)
    assert len(events) == 3


def test_get_recent_events_structure():
    from core.audit_log import log_event, get_recent_events, EventType
    log_event(EventType.VAULT_UNLOCKED, {"user": "system"})
    events = get_recent_events()
    e = events[0]
    assert "id" in e
    assert "event_type" in e
    assert "payload" in e
    assert "created_at" in e
    assert isinstance(e["payload"], dict)
    assert isinstance(e["created_at"], float)
