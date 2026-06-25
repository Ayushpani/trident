"""
trident.execute.mechanical — Tier 0 mechanical replay.

Reads a Runbook and executes its steps in order using subprocess.
No AI, no magic — blind execution with log watching and error stops.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

from shellstory.models import Runbook, RunbookStep

_DESTRUCTIVE_RE = re.compile(
    r"\b(rm\s+-rf?|drop\s+(?:table|database|schema|index)|"
    r"truncate\s+|delete\s+from\s+|kill\s+-9|"
    r"kubectl\s+delete|helm\s+uninstall|"
    r"format\s+|mkfs\.|dd\s+if=)\b",
    re.IGNORECASE,
)

_MAX_OUTPUT_LINES = 50
_STEP_TIMEOUT = 300  # seconds


@dataclass
class StepResult:
    step_number: int
    title: str
    command: str
    returncode: int
    stdout: str
    stderr: str
    skipped: bool = False


@dataclass
class ReplayResult:
    steps_run: int = 0
    steps_total: int = 0
    steps_skipped: int = 0
    failed_step: StepResult | None = None
    step_results: list[StepResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.failed_step is None


class MechanicalReplayer:
    """
    Executes runbook steps sequentially in a subprocess.

    Behaviour:
    - Stops immediately on the first non-zero exit code.
    - Prompts for confirmation before destructive commands when
      config['execution']['confirm_destructive'] is True.
    - Truncates output to _MAX_OUTPUT_LINES to prevent console flooding.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._confirm_destructive = (
            self._config.get("execution", {}).get("confirm_destructive", True)
        )

    def run(self, runbook: Runbook) -> ReplayResult:
        """Execute all steps in the runbook.  Returns a ReplayResult."""
        steps_with_commands = [s for s in runbook.steps if s.command]
        result = ReplayResult(steps_total=len(steps_with_commands))

        _print_header(runbook)

        for step in runbook.steps:
            if not step.command:
                continue

            _print_step_header(step)

            if step.warning:
                _warn(step.warning)

            if self._confirm_destructive and _DESTRUCTIVE_RE.search(step.command):
                if not _prompt_confirm(step.command):
                    step_res = StepResult(
                        step_number=step.step_number,
                        title=step.title,
                        command=step.command,
                        returncode=0,
                        stdout="",
                        stderr="",
                        skipped=True,
                    )
                    result.step_results.append(step_res)
                    result.steps_skipped += 1
                    _info("  Skipped.")
                    continue

            step_res = self._run_step(step)
            result.step_results.append(step_res)
            result.steps_run += 1

            if step_res.returncode != 0:
                result.failed_step = step_res
                _error(
                    f"\nStep {step.step_number} failed (exit code {step_res.returncode})."
                )
                if step_res.stderr.strip():
                    _error("stderr:\n" + _truncate(step_res.stderr, 20))
                break

        _print_summary(result)
        return result

    def _run_step(self, step: RunbookStep) -> StepResult:
        try:
            proc = subprocess.run(
                step.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=_STEP_TIMEOUT,
            )
            stdout = _truncate(proc.stdout, _MAX_OUTPUT_LINES)
            if stdout.strip():
                print(stdout)

            return StepResult(
                step_number=step.step_number,
                title=step.title,
                command=step.command,
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )
        except subprocess.TimeoutExpired:
            _error(f"  Step {step.step_number} timed out after {_STEP_TIMEOUT}s.")
            return StepResult(
                step_number=step.step_number,
                title=step.title,
                command=step.command,
                returncode=124,
                stdout="",
                stderr=f"Timed out after {_STEP_TIMEOUT}s",
            )
        except Exception as exc:
            _error(f"  Step {step.step_number} error: {exc}")
            return StepResult(
                step_number=step.step_number,
                title=step.title,
                command=step.command,
                returncode=1,
                stdout="",
                stderr=str(exc),
            )


class StepFailedError(Exception):
    def __init__(self, result: StepResult) -> None:
        self.result = result
        super().__init__(
            f"Step {result.step_number} '{result.title}' failed "
            f"(exit {result.returncode})"
        )


# ── Console helpers ───────────────────────────────────────────────────────────


def _print_header(runbook: Runbook) -> None:
    steps_with_cmd = sum(1 for s in runbook.steps if s.command)
    print(f"\n{'=' * 60}")
    print(f"  Trident Replay: {runbook.title}")
    print(f"  {steps_with_cmd} step(s) to execute")
    print(f"{'=' * 60}\n")


def _print_step_header(step: RunbookStep) -> None:
    print(f"[Step {step.step_number}] {step.title}")
    print(f"  $ {step.command}")
    if step.explanation:
        print(f"  {step.explanation}")


def _print_summary(result: ReplayResult) -> None:
    print(f"\n{'─' * 60}")
    if result.success:
        print(f"  Replay complete: {result.steps_run} step(s) run successfully.")
    else:
        fs = result.failed_step
        print(
            f"  Replay stopped at step {fs.step_number}: {fs.title}"
            if fs else "  Replay failed."
        )
    if result.steps_skipped:
        print(f"  {result.steps_skipped} step(s) skipped (user declined).")
    print(f"{'─' * 60}\n")


def _prompt_confirm(command: str) -> bool:
    try:
        answer = input(
            f"  [!] Destructive command detected:\n"
            f"      $ {command[:120]}\n"
            f"  Proceed? [y/N] "
        ).strip().lower()
        return answer in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def _truncate(text: str, max_lines: int) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    kept = lines[:max_lines]
    kept.append(f"... ({len(lines) - max_lines} more lines truncated)")
    return "\n".join(kept)


def _warn(msg: str) -> None:
    print(f"  [!] {msg}", file=sys.stderr)


def _error(msg: str) -> None:
    print(msg, file=sys.stderr)


def _info(msg: str) -> None:
    print(msg)
