"""
trident.capture.adapter — central re-export hub for ShellStory library code.

All Trident modules import ShellStory symbols from here so that if we ever
need to swap or monkey-patch an import there is one place to change.
"""

from shellstory.capture import (  # noqa: F401
    create_hook_file,
    detect_shell,
    generate_bash_hook,
    generate_powershell_hook,
    generate_zsh_hook,
    write_session_start_event,
)
from shellstory.db import Database  # noqa: F401
from shellstory.models import (  # noqa: F401
    FailureRecord,
    PrereqItem,
    RawEvent,
    RedactedEvent,
    RedactionResult,
    Runbook,
    RunbookStep,
    Session,
    VariableDefinition,
)
from shellstory.redact import redact_events  # noqa: F401
from shellstory.utils.ndjson import append_event, count_events, load_events  # noqa: F401
