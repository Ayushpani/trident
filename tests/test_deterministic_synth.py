"""
tests.test_deterministic_synth — the critical Tier 0 test.

The DeterministicSynthesizer must produce useful runbooks from raw shell
events with zero LLM calls.  These tests mock nothing — they are pure
function tests verifying the heuristic pipeline.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from shellstory.models import RawEvent, Runbook
from trident.synthesize.deterministic import DeterministicSynthesizer


SESSION_ID = "test-session-001"


def _event(
    command: str,
    exit_code: int = 0,
    working_dir: str = "/home/user/project",
    seq: int = 1,
) -> RawEvent:
    return RawEvent(
        event_type="command",
        timestamp=datetime.now(timezone.utc),
        session_id=SESSION_ID,
        sequence=seq,
        command=command,
        working_dir=working_dir,
        exit_code=exit_code,
        duration_ms=100,
    )


# ── Noise filtering ──────────────────────────────────────────────────────────


def test_drops_navigation_commands():
    synth = DeterministicSynthesizer()
    events = [
        _event("cd /tmp", seq=1),
        _event("ls -la", seq=2),
        _event("pwd", seq=3),
        _event("clear", seq=4),
        _event("git status", seq=5),  # signal
    ]
    runbook = synth.synthesize(events, title="Test")
    commands = [s.command for s in runbook.steps if s.command]
    flat = " ".join(commands)
    assert "git status" in flat
    assert "ls -la" not in flat
    assert "pwd" not in flat
    assert "clear" not in flat


def test_drops_history_commands():
    synth = DeterministicSynthesizer()
    events = [
        _event("history", seq=1),
        _event("man git", seq=2),
        _event("npm install", seq=3),  # signal
    ]
    runbook = synth.synthesize(events, title="Test")
    commands = " ".join(s.command or "" for s in runbook.steps)
    assert "npm install" in commands
    assert "history" not in commands
    assert "man git" not in commands


def test_keeps_meaningful_echo_free():
    """echo is noise; git commit is signal."""
    synth = DeterministicSynthesizer()
    events = [
        _event("echo hello", seq=1),
        _event("git commit -m 'fix'", seq=2),
    ]
    runbook = synth.synthesize(events, title="Test")
    commands = " ".join(s.command or "" for s in runbook.steps)
    assert "git commit" in commands
    assert "echo hello" not in commands


# ── Error recovery collapse ───────────────────────────────────────────────────


def test_collapses_failed_then_fixed():
    """A failed command followed by its fix in the same dir → keep only the fix."""
    synth = DeterministicSynthesizer()
    events = [
        _event("git pus origin main", exit_code=1, seq=1),   # typo, failed
        _event("git push origin main", exit_code=0, seq=2),  # fixed
    ]
    runbook = synth.synthesize(events, title="Test")
    raw_cmds = runbook.raw_signal_commands
    assert "git push origin main" in raw_cmds
    assert "git pus origin main" not in raw_cmds


def test_keeps_both_when_different_dirs():
    """Error recovery only applies within the same working directory."""
    synth = DeterministicSynthesizer()
    events = [
        _event("npm build", exit_code=1, working_dir="/app", seq=1),
        _event("npm start", exit_code=0, working_dir="/srv", seq=2),
    ]
    runbook = synth.synthesize(events, title="Test")
    raw_cmds = runbook.raw_signal_commands
    assert "npm build" in raw_cmds
    assert "npm start" in raw_cmds


def test_keeps_all_failures_without_fix():
    """A failed command with no follow-up fix must be kept."""
    synth = DeterministicSynthesizer()
    events = [
        _event("docker build .", exit_code=1, seq=1),
        _event("ls", exit_code=0, seq=2),  # noise
    ]
    runbook = synth.synthesize(events, title="Test")
    # docker build stays; ls is noise
    raw_cmds = runbook.raw_signal_commands
    assert "docker build ." in raw_cmds


# ── Grouping by directory ─────────────────────────────────────────────────────


def test_groups_by_working_dir():
    synth = DeterministicSynthesizer()
    events = [
        _event("git pull", working_dir="/app", seq=1),
        _event("npm install", working_dir="/app", seq=2),
        _event("python manage.py migrate", working_dir="/app/backend", seq=3),
        _event("python manage.py runserver", working_dir="/app/backend", seq=4),
    ]
    runbook = synth.synthesize(events, title="Test")
    # Should produce 2 steps (one per directory)
    assert len(runbook.steps) == 2
    assert "app" in runbook.steps[0].title.lower() or "Commands" in runbook.steps[0].title


def test_single_command_no_join():
    synth = DeterministicSynthesizer()
    events = [_event("helm upgrade myapp ./chart", seq=1)]
    runbook = synth.synthesize(events, title="Test")
    assert runbook.steps[0].command == "helm upgrade myapp ./chart"


def test_multi_command_joined_with_ampersand():
    synth = DeterministicSynthesizer()
    events = [
        _event("git fetch origin", seq=1),
        _event("git rebase origin/main", seq=2),
        _event("git push origin HEAD", seq=3),
    ]
    runbook = synth.synthesize(events, title="Test")
    # All in same dir → one step, joined
    assert len(runbook.steps) == 1
    assert "&&" in runbook.steps[0].command


# ── Variable extraction ───────────────────────────────────────────────────────


def test_extracts_env_vars():
    synth = DeterministicSynthesizer()
    events = [
        _event("export DATABASE_URL=postgres://localhost/mydb", seq=1),
        _event("export JWT_SECRET=supersecret123", seq=2),
        _event("npm start", seq=3),
    ]
    runbook = synth.synthesize(events, title="Test")
    var_names = {v.variable_name for v in runbook.variables}
    assert "DATABASE_URL" in var_names
    assert "JWT_SECRET" in var_names


def test_no_env_vars_when_none_set():
    synth = DeterministicSynthesizer()
    events = [_event("npm install", seq=1), _event("npm run build", seq=2)]
    runbook = synth.synthesize(events, title="Test")
    assert runbook.variables == []


# ── Destructive warning ───────────────────────────────────────────────────────


def test_marks_destructive_command_with_warning():
    synth = DeterministicSynthesizer()
    events = [_event("rm -rf ./dist", seq=1)]
    runbook = synth.synthesize(events, title="Test")
    step = runbook.steps[0]
    assert step.warning is not None
    assert "destructive" in step.warning.lower()


def test_no_warning_for_safe_command():
    synth = DeterministicSynthesizer()
    events = [_event("git status", seq=1)]
    runbook = synth.synthesize(events, title="Test")
    assert runbook.steps[0].warning is None


# ── Runbook structure ─────────────────────────────────────────────────────────


def test_empty_events_produces_empty_runbook():
    synth = DeterministicSynthesizer()
    runbook = synth.synthesize([], title="Empty Session")
    assert runbook.steps == []
    assert runbook.variables == []
    assert runbook.raw_signal_commands == []
    assert "no signal" in runbook.description.lower()


def test_runbook_is_pydantic_model():
    synth = DeterministicSynthesizer()
    events = [_event("docker-compose up -d", seq=1)]
    runbook = synth.synthesize(events, title="Deploy")
    assert isinstance(runbook, Runbook)
    assert runbook.id
    assert runbook.title == "Deploy"
    # Tier 0 — no LLM prerequisites inferred
    assert runbook.prerequisites == []
    assert runbook.errors_and_fixes == []


def test_all_noise_produces_empty_steps():
    synth = DeterministicSynthesizer()
    events = [
        _event("ls", seq=1),
        _event("pwd", seq=2),
        _event("clear", seq=3),
        _event("history", seq=4),
    ]
    runbook = synth.synthesize(events, title="Test")
    assert runbook.steps == []


def test_no_llm_calls_made(monkeypatch):
    """Verify that DeterministicSynthesizer makes zero outbound HTTP calls."""
    import httpx

    def fail(*args, **kwargs):
        raise AssertionError("DeterministicSynthesizer must not make network calls")

    monkeypatch.setattr(httpx, "post", fail)
    monkeypatch.setattr(httpx, "get", fail)

    synth = DeterministicSynthesizer()
    events = [_event("docker build -t myapp .", seq=1)]
    runbook = synth.synthesize(events, title="Test")
    assert runbook.steps  # produced output without any HTTP call
