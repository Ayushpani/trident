"""
trident.capture.redact — PII redaction layer wrapping ShellStory's pipeline.

ShellStory ships 16 regex patterns covering AWS keys, DB connection strings,
bearer tokens, SSH keys, etc.  Trident adds config-driven on/off control.
"""

from __future__ import annotations

from shellstory.models import RawEvent, RedactionResult
from shellstory.redact import redact_events as _redact_events


def redact(events: list[RawEvent], mode: str = "strict") -> RedactionResult:
    """
    Apply PII redaction to a list of raw events.

    Args:
        events: Raw events from a capture session.
        mode:   "strict" (default) — apply all 16 patterns + AI scan stub;
                "standard" — regex only, skip AI;
                "off" — return events unchanged (not recommended for BYOK/managed tiers).

    Returns:
        RedactionResult with redacted events and a list of discovered variables.
    """
    if mode == "off":
        from shellstory.models import RedactedEvent
        redacted = [
            RedactedEvent(
                original_sequence=e.sequence,
                event_type=e.event_type,
                timestamp=e.timestamp,
                command=e.command,
                working_dir=e.working_dir,
                exit_code=e.exit_code,
                duration_ms=e.duration_ms,
                stream=e.stream,
                text=e.text,
                shell=e.shell,
                os=e.os,
            )
            for e in events
        ]
        return RedactionResult(
            events=redacted,
            variables=[],
            redaction_count=0,
            original_event_count=len(events),
        )

    return _redact_events(events)
