"""
trident.capture.daemon — background event processor wrapping ShellStory's daemon.

The daemon tails the NDJSON capture file every 30 seconds and runs
incremental agent processing.  Trident runs this as a subprocess so it
doesn't block the user's shell.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from shellstory.models import Session


def start_daemon(session: Session, config: dict) -> subprocess.Popen:
    """
    Launch the ShellStory daemon as a background subprocess.

    The daemon processes events in 30-second rolling windows and writes
    incremental state to {sessions_dir}/{session_id}.state.json.

    Returns the Popen handle; the caller is responsible for tracking it.
    """
    session_json = session.model_dump_json()
    config_json = json.dumps(config)

    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import json, sys; "
                "from shellstory.daemon import run_daemon_sync; "
                f"run_daemon_sync({repr(session_json)}, {repr(config_json)})"
            ),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


def stop_daemon(proc: subprocess.Popen) -> None:
    """Terminate the daemon subprocess gracefully."""
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
