"""
trident.capture.ndjson — thin wrappers around shellstory NDJSON utilities.

Re-exports the core helpers and adds Trident-specific conveniences.
"""

from pathlib import Path

from shellstory.utils.ndjson import append_event, count_events, load_events  # noqa: F401
from shellstory.models import RawEvent


def load_command_events(capture_file: Path) -> list[RawEvent]:
    """Load only command-type events from a capture file."""
    return [e for e in load_events(capture_file) if e.event_type == "command"]


def event_count(capture_file: Path) -> int:
    """Number of valid NDJSON lines in the capture file (for status display)."""
    return count_events(capture_file)
