"""
trident.capture.hooks — session lifecycle management.

Bridges ShellStory's capture primitives with Trident's own database and
config, so Trident maintains its own session records independently of
the shellstory CLI.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from trident.capture.adapter import (
    Database,
    Session,
    create_hook_file,
    detect_shell,
    write_session_start_event,
)
from trident.config import db_path, sessions_dir


def start_session(title: str, config: dict) -> tuple[Session, Path]:
    """
    Create a new capture session.

    1. Allocates a UUID, creates the NDJSON capture file path.
    2. Persists the Session to Trident's own SQLite DB.
    3. Writes the session_start event to the capture file.
    4. Generates the shell hook script.

    Returns (session, hook_path).
    """
    session_id = str(uuid.uuid4())
    shell_type = detect_shell()

    s_dir = sessions_dir(config)
    s_dir.mkdir(parents=True, exist_ok=True)

    capture_file = s_dir / f"{session_id}.ndjson"
    capture_file.touch()

    session = Session(
        id=session_id,
        title=title,
        started_at=datetime.now(timezone.utc),
        capture_file=str(capture_file),
        status="capturing",
        shell_type=shell_type,
    )

    db = Database(db_path())
    try:
        db.create_session(session)
    finally:
        db.close()

    write_session_start_event(capture_file, session_id, shell_type)

    hook_path = create_hook_file(session_id, str(capture_file), shell_type, s_dir)

    return session, hook_path


def stop_session(session_id: str, config: dict | None = None) -> None:
    """Mark a session as ended in the DB."""
    db = Database(db_path())
    try:
        db.update_session_status(
            session_id,
            status="processing",
            ended_at=datetime.now(timezone.utc),
        )
    finally:
        db.close()


def get_active_session() -> Session | None:
    """Return the most recently started 'capturing' session."""
    db = Database(db_path())
    try:
        return db.get_active_session()
    finally:
        db.close()


def get_session(session_id: str) -> Session | None:
    """Fetch a session by full or prefix ID."""
    db = Database(db_path())
    try:
        return db.get_session(session_id)
    finally:
        db.close()


def list_sessions(limit: int = 50) -> list[Session]:
    """Return sessions most-recent-first."""
    db = Database(db_path())
    try:
        return db.list_sessions(limit=limit)
    finally:
        db.close()
