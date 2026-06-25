"""
tests.test_capture — tests for session lifecycle and NDJSON event loading.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from shellstory.models import RawEvent, Session
from trident.capture.ndjson import event_count, load_command_events
from shellstory.utils.ndjson import load_events, append_event


# ── NDJSON helpers ────────────────────────────────────────────────────────────


def test_load_events_round_trips(tmp_path):
    capture = tmp_path / "test.ndjson"
    event = RawEvent(
        event_type="command",
        timestamp=datetime.now(timezone.utc),
        session_id="s1",
        sequence=1,
        command="git status",
        working_dir="/tmp",
        exit_code=0,
    )
    append_event(capture, event.model_dump(mode="json"))

    events = load_events(capture)
    assert len(events) == 1
    assert events[0].command == "git status"
    assert events[0].exit_code == 0


def test_load_events_skips_malformed_lines(tmp_path):
    capture = tmp_path / "bad.ndjson"
    capture.write_text('{"bad": json here}\n{"event_type":"session_start","timestamp":"2024-01-01T00:00:00Z","session_id":"s1","sequence":0}\n', encoding="utf-8")
    events = load_events(capture)
    # Only one parseable event; malformed line silently skipped
    assert len(events) == 1


def test_load_events_raises_for_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_events(tmp_path / "nonexistent.ndjson")


def test_event_count(tmp_path):
    capture = tmp_path / "count.ndjson"
    for i in range(5):
        ev = RawEvent(
            event_type="command",
            timestamp=datetime.now(timezone.utc),
            session_id="s1",
            sequence=i,
            command=f"cmd{i}",
        )
        append_event(capture, ev.model_dump(mode="json"))
    assert event_count(capture) == 5


def test_event_count_missing_file_returns_zero(tmp_path):
    assert event_count(tmp_path / "nope.ndjson") == 0


def test_load_command_events_filters_types(tmp_path):
    capture = tmp_path / "mixed.ndjson"
    events_to_write = [
        RawEvent(event_type="session_start", timestamp=datetime.now(timezone.utc), session_id="s1", sequence=0, shell="bash"),
        RawEvent(event_type="command", timestamp=datetime.now(timezone.utc), session_id="s1", sequence=1, command="git log"),
        RawEvent(event_type="session_end", timestamp=datetime.now(timezone.utc), session_id="s1", sequence=2),
    ]
    for ev in events_to_write:
        append_event(capture, ev.model_dump(mode="json"))

    cmds = load_command_events(capture)
    assert len(cmds) == 1
    assert cmds[0].command == "git log"


# ── Session DB ────────────────────────────────────────────────────────────────


def test_database_create_and_retrieve_session(tmp_path):
    from shellstory.db import Database
    db = Database(tmp_path / "test.db")

    session = Session(
        id=str(uuid.uuid4()),
        title="Test Deploy",
        started_at=datetime.now(timezone.utc),
        capture_file=str(tmp_path / "cap.ndjson"),
        status="capturing",
    )
    db.create_session(session)
    retrieved = db.get_session(session.id)
    assert retrieved is not None
    assert retrieved.title == "Test Deploy"
    assert retrieved.status == "capturing"
    db.close()


def test_database_update_session_status(tmp_path):
    from shellstory.db import Database
    db = Database(tmp_path / "test.db")

    session = Session(
        id=str(uuid.uuid4()),
        title="Update Test",
        started_at=datetime.now(timezone.utc),
        capture_file="/tmp/cap.ndjson",
        status="capturing",
    )
    db.create_session(session)
    db.update_session_status(session.id, "complete", ended_at=datetime.now(timezone.utc))

    updated = db.get_session(session.id)
    assert updated.status == "complete"
    assert updated.ended_at is not None
    db.close()


def test_database_prefix_lookup(tmp_path):
    from shellstory.db import Database
    db = Database(tmp_path / "test.db")

    session = Session(
        id="abcdef12-1234-1234-1234-123456789abc",
        title="Prefix Test",
        started_at=datetime.now(timezone.utc),
        capture_file="/tmp/cap.ndjson",
        status="capturing",
    )
    db.create_session(session)
    retrieved = db.get_session("abcdef12")
    assert retrieved is not None
    assert retrieved.id == session.id
    db.close()


def test_get_active_session_returns_most_recent_capturing(tmp_path):
    from shellstory.db import Database
    db = Database(tmp_path / "test.db")

    s1 = Session(
        id=str(uuid.uuid4()),
        title="Old",
        started_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        capture_file="/tmp/s1.ndjson",
        status="complete",
    )
    s2 = Session(
        id=str(uuid.uuid4()),
        title="Active",
        started_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        capture_file="/tmp/s2.ndjson",
        status="capturing",
    )
    db.create_session(s1)
    db.create_session(s2)

    active = db.get_active_session()
    assert active is not None
    assert active.title == "Active"
    db.close()
