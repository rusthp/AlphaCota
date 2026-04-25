"""tests/test_polymarket_observability.py — Tests for observability logging."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core.polymarket_observability import _log_path, _VALID_EVENTS, log_order_event


class TestLogPath:
    def test_contains_date(self):
        p = _log_path("2026-04-14")
        assert "2026-04-14" in str(p)
        assert p.suffix == ".jsonl"

    def test_defaults_to_today(self):
        from datetime import date
        today = date.today().isoformat()
        p = _log_path()
        assert today in str(p)


class TestLogOrderEvent:
    def test_creates_file_and_writes_json(self, tmp_path):
        log_dir = tmp_path / "logs"
        with patch("core.polymarket_observability._LOG_DIR", log_dir):
            log_order_event("order_filled", {"order_id": "o1", "fill": 0.55}, today="2026-04-14")

        log_file = log_dir / "polymarket_2026-04-14.jsonl"
        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event"] == "order_filled"
        assert record["order_id"] == "o1"
        assert record["fill"] == pytest.approx(0.55)

    def test_multiple_events_append(self, tmp_path):
        log_dir = tmp_path / "logs"
        with patch("core.polymarket_observability._LOG_DIR", log_dir):
            log_order_event("order_attempt", {"order_id": "o1"}, today="2026-04-14")
            log_order_event("order_filled", {"order_id": "o1"}, today="2026-04-14")

        log_file = log_dir / "polymarket_2026-04-14.jsonl"
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_daily_rotation_creates_new_file(self, tmp_path):
        log_dir = tmp_path / "logs"
        with patch("core.polymarket_observability._LOG_DIR", log_dir):
            log_order_event("order_attempt", {}, today="2026-04-13")
            log_order_event("order_filled", {}, today="2026-04-14")

        assert (log_dir / "polymarket_2026-04-13.jsonl").exists()
        assert (log_dir / "polymarket_2026-04-14.jsonl").exists()

    def test_json_lines_parseable(self, tmp_path):
        log_dir = tmp_path / "logs"
        with patch("core.polymarket_observability._LOG_DIR", log_dir):
            for event in _VALID_EVENTS:
                log_order_event(event, {"x": 1}, today="2026-04-14")

        log_file = log_dir / "polymarket_2026-04-14.jsonl"
        for line in log_file.read_text().strip().split("\n"):
            record = json.loads(line)
            assert "event" in record
            assert "ts" in record
            assert "mode" in record

    def test_mode_recorded(self, tmp_path):
        log_dir = tmp_path / "logs"
        with patch("core.polymarket_observability._LOG_DIR", log_dir):
            log_order_event("hard_limit_hit", {"reason": "size"}, mode="live", today="2026-04-14")

        log_file = log_dir / "polymarket_2026-04-14.jsonl"
        record = json.loads(log_file.read_text().strip())
        assert record["mode"] == "live"

    def test_unknown_event_type_logs_warning_but_writes(self, tmp_path):
        log_dir = tmp_path / "logs"
        with patch("core.polymarket_observability._LOG_DIR", log_dir):
            log_order_event("unknown_event", {"x": 1}, today="2026-04-14")

        log_file = log_dir / "polymarket_2026-04-14.jsonl"
        assert log_file.exists()
        record = json.loads(log_file.read_text().strip())
        assert record["event"] == "unknown_event"

    def test_payload_extra_fields_included(self, tmp_path):
        log_dir = tmp_path / "logs"
        with patch("core.polymarket_observability._LOG_DIR", log_dir):
            log_order_event("position_closed", {
                "condition_id": "cid1",
                "realized_pnl": 12.5,
                "direction": "yes",
            }, today="2026-04-14")

        record = json.loads((log_dir / "polymarket_2026-04-14.jsonl").read_text().strip())
        assert record["condition_id"] == "cid1"
        assert record["realized_pnl"] == pytest.approx(12.5)
