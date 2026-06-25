"""
tests.test_mechanical_replay — tests for the Tier 0 mechanical replayer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from shellstory.models import Runbook, RunbookStep
from trident.execute.mechanical import MechanicalReplayer, ReplayResult, StepResult


def _make_runbook(steps: list[tuple[str, str | None]]) -> Runbook:
    """Create a minimal Runbook from (title, command) pairs."""
    return Runbook(
        id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        title="Test Runbook",
        description="Test",
        created_at=datetime.now(timezone.utc),
        variables=[],
        prerequisites=[],
        steps=[
            RunbookStep(
                step_number=i + 1,
                title=title,
                command=command,
                explanation=f"Explanation for {title}",
            )
            for i, (title, command) in enumerate(steps)
        ],
        errors_and_fixes=[],
        raw_signal_commands=[cmd for _, cmd in steps if cmd],
    )


# ── Happy path ────────────────────────────────────────────────────────────────


def test_all_steps_succeed():
    config = {"execution": {"confirm_destructive": False}}
    replayer = MechanicalReplayer(config)
    runbook = _make_runbook([
        ("Install deps", "echo install"),
        ("Build", "echo build"),
        ("Deploy", "echo deploy"),
    ])

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "ok\n"
    mock_proc.stderr = ""

    with patch("subprocess.run", return_value=mock_proc) as mock_run:
        result = replayer.run(runbook)

    assert result.success
    assert result.steps_run == 3
    assert result.failed_step is None
    assert mock_run.call_count == 3


def test_stops_on_first_failure():
    config = {"execution": {"confirm_destructive": False}}
    replayer = MechanicalReplayer(config)
    runbook = _make_runbook([
        ("Step 1", "echo ok"),
        ("Step 2 fail", "false"),   # fails
        ("Step 3", "echo never"),
    ])

    def side_effect(cmd, **kwargs):
        proc = MagicMock()
        if "false" in cmd:
            proc.returncode = 1
            proc.stdout = ""
            proc.stderr = "error"
        else:
            proc.returncode = 0
            proc.stdout = "ok"
            proc.stderr = ""
        return proc

    with patch("subprocess.run", side_effect=side_effect):
        result = replayer.run(runbook)

    assert not result.success
    assert result.steps_run == 2  # step 1 + step 2 (failed)
    assert result.failed_step is not None
    assert result.failed_step.step_number == 2


def test_skips_steps_without_commands():
    config = {"execution": {"confirm_destructive": False}}
    replayer = MechanicalReplayer(config)
    runbook = _make_runbook([
        ("Note", None),             # no command — skip
        ("Build", "echo build"),    # has command
    ])

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "built\n"
    mock_proc.stderr = ""

    with patch("subprocess.run", return_value=mock_proc) as mock_run:
        result = replayer.run(runbook)

    assert result.success
    assert mock_run.call_count == 1  # only the step with a command ran


# ── Destructive command handling ──────────────────────────────────────────────


def test_prompts_for_destructive_when_enabled(monkeypatch):
    config = {"execution": {"confirm_destructive": True}}
    replayer = MechanicalReplayer(config)
    runbook = _make_runbook([("Danger", "rm -rf /tmp/test_dir")])

    # User declines
    monkeypatch.setattr("builtins.input", lambda _: "n")

    with patch("subprocess.run") as mock_run:
        result = replayer.run(runbook)

    assert result.success  # skip is not a failure
    assert result.steps_skipped == 1
    mock_run.assert_not_called()


def test_destructive_skipped_does_not_count_as_failure(monkeypatch):
    config = {"execution": {"confirm_destructive": True}}
    replayer = MechanicalReplayer(config)
    runbook = _make_runbook([
        ("Safe", "echo safe"),
        ("Danger", "kubectl delete namespace prod"),
    ])

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "safe\n"
    mock_proc.stderr = ""

    monkeypatch.setattr("builtins.input", lambda _: "n")  # decline destructive

    with patch("subprocess.run", return_value=mock_proc):
        result = replayer.run(runbook)

    assert result.success
    assert result.steps_run == 1
    assert result.steps_skipped == 1


def test_no_prompt_when_destructive_confirmation_disabled(monkeypatch):
    config = {"execution": {"confirm_destructive": False}}
    replayer = MechanicalReplayer(config)
    runbook = _make_runbook([("Danger", "rm -rf /tmp/test")])

    prompt_called = []
    monkeypatch.setattr("builtins.input", lambda _: prompt_called.append(1) or "y")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = ""
    mock_proc.stderr = ""

    with patch("subprocess.run", return_value=mock_proc):
        result = replayer.run(runbook)

    assert result.success
    assert not prompt_called  # never prompted


# ── Timeout handling ──────────────────────────────────────────────────────────


def test_timeout_returns_exit_code_124():
    import subprocess
    config = {"execution": {"confirm_destructive": False}}
    replayer = MechanicalReplayer(config)
    runbook = _make_runbook([("Hang", "sleep 9999")])

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("sleep", 300)):
        result = replayer.run(runbook)

    assert not result.success
    assert result.failed_step.returncode == 124


# ── ReplayResult ──────────────────────────────────────────────────────────────


def test_replay_result_success_property():
    r = ReplayResult(steps_run=3, steps_total=3)
    assert r.success

    r2 = ReplayResult(
        steps_run=2,
        steps_total=3,
        failed_step=StepResult(2, "fail", "cmd", 1, "", "err"),
    )
    assert not r2.success
