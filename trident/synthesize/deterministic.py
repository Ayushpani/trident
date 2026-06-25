"""
trident.synthesize.deterministic — Tier 0 heuristic synthesis.

No LLM is called.  Pure rule-based signal extraction produces a usable
Runbook from raw shell events.  This is the product floor — it must work
for any engineer regardless of API keys, GPU, or internet access.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Union

from shellstory.models import (
    RawEvent,
    RedactedEvent,
    Runbook,
    RunbookStep,
    VariableDefinition,
)

# Commands that carry no procedural value in a runbook.
_NOISE_COMMANDS: frozenset[str] = frozenset(
    [
        "cd", "ls", "ll", "la", "l", "ls -la", "ls -l", "ls -a",
        "pwd", "clear", "cls", "reset",
        "history", "fc", "h",
        "man", "less", "more", "most",
        "echo", "printf",
        "which", "type", "where", "whereis",
        "exit", "logout", "quit", "q",
        "help", "?",
        "cat",   # reading files — useful sometimes, but mostly noise in replays
        "head", "tail",
        "date", "time", "uptime",
        "whoami", "id", "uname",
        "env", "set", "printenv",
    ]
)

# Regex patterns for metadata extraction.
_ENV_VAR_RE = re.compile(
    r"(?:export\s+|set\s+)?([A-Z][A-Z0-9_]{2,})\s*=",
    re.IGNORECASE,
)
_PORT_RE = re.compile(
    r"(?:listen|bind|port|--port|-p)\s*[=:]?\s*(\d{2,5})|"
    r"-p\s+(\d{2,5}):\d{2,5}|"
    r":(\d{2,5})\b",
)
_FILE_CREATED_RE = re.compile(
    r"(?:>\s*|tee\s+|touch\s+)([\w./~-]+\.\w+)",
)
_DESTRUCTIVE_RE = re.compile(
    r"\b(rm\s+-rf?|drop\s+(?:table|database|schema|index)|"
    r"truncate\s+|delete\s+from\s+|kill\s+-9|"
    r"kubectl\s+delete|helm\s+uninstall|"
    r"format\s+|mkfs\.|dd\s+if=)\b",
    re.IGNORECASE,
)


class DeterministicSynthesizer:
    """
    Rule-based synthesis — produces a Runbook without any LLM calls.

    Heuristic pipeline:
      1. Filter to command events only.
      2. Drop noise commands (navigation, introspection, etc.).
      3. Collapse error→fix pairs (failed command + successful retry).
      4. Drop lone cd commands not followed by meaningful work.
      5. Group consecutive commands by working directory.
      6. Extract environment variables, ports, and created files.
      7. Assemble Runbook.
    """

    def synthesize(
        self,
        events: list[Union[RawEvent, RedactedEvent]],
        title: str,
        session_id: str = "",
    ) -> Runbook:
        cmd_events = [e for e in events if e.event_type == "command" and e.command]
        cmd_events = self._drop_noise(cmd_events)
        cmd_events = self._collapse_error_recovery(cmd_events)
        cmd_events = self._drop_orphan_cds(cmd_events)

        variables = self._extract_env_vars(cmd_events)
        steps = self._group_into_steps(cmd_events)
        description = self._make_description(title, steps)

        return Runbook(
            id=str(uuid.uuid4()),
            session_id=session_id or str(uuid.uuid4()),
            title=title,
            description=description,
            created_at=datetime.now(timezone.utc),
            variables=variables,
            prerequisites=[],
            steps=steps,
            errors_and_fixes=[],
            raw_signal_commands=[e.command for e in cmd_events if e.command],
        )

    # ── Step 1: noise filter ──────────────────────────────────────────────────

    def _drop_noise(
        self, events: list[Union[RawEvent, RedactedEvent]]
    ) -> list[Union[RawEvent, RedactedEvent]]:
        result = []
        for ev in events:
            if not ev.command:
                continue
            first_token = ev.command.strip().lstrip("./").split()[0].lower()
            if first_token not in _NOISE_COMMANDS:
                result.append(ev)
        return result

    # ── Step 2: collapse error→fix pairs ─────────────────────────────────────

    def _collapse_error_recovery(
        self, events: list[Union[RawEvent, RedactedEvent]]
    ) -> list[Union[RawEvent, RedactedEvent]]:
        """
        If command[i] failed (exit_code != 0) and command[i+1] succeeded
        (exit_code == 0) in the same working directory, drop command[i].
        The fix is what matters, not the failed attempt.
        """
        if len(events) < 2:
            return events

        to_drop: set[int] = set()
        for i in range(len(events) - 1):
            curr = events[i]
            nxt = events[i + 1]

            curr_code = curr.exit_code if curr.exit_code is not None else 0
            nxt_code = nxt.exit_code if nxt.exit_code is not None else 0

            if curr_code != 0 and nxt_code == 0:
                curr_dir = getattr(curr, "working_dir", None)
                nxt_dir = getattr(nxt, "working_dir", None)
                if curr_dir == nxt_dir or (not curr_dir and not nxt_dir):
                    to_drop.add(i)

        return [ev for idx, ev in enumerate(events) if idx not in to_drop]

    # ── Step 3: drop orphan cd commands ──────────────────────────────────────

    def _drop_orphan_cds(
        self, events: list[Union[RawEvent, RedactedEvent]]
    ) -> list[Union[RawEvent, RedactedEvent]]:
        """
        A lone 'cd <path>' with no subsequent command in that directory
        is navigation noise; drop it.
        """
        result = []
        for i, ev in enumerate(events):
            if ev.command and ev.command.strip().startswith("cd "):
                # Keep it only if the next event is in a different dir
                # (i.e. it was a meaningful navigation step)
                if i + 1 < len(events):
                    nxt = events[i + 1]
                    curr_dir = getattr(ev, "working_dir", None)
                    nxt_dir = getattr(nxt, "working_dir", None)
                    if curr_dir == nxt_dir:
                        continue  # drop — they stayed; cd was implicit
                # Last event or moving to a new dir — keep
                result.append(ev)
            else:
                result.append(ev)
        return result

    # ── Step 4: group by working directory into RunbookSteps ─────────────────

    def _group_into_steps(
        self, events: list[Union[RawEvent, RedactedEvent]]
    ) -> list[RunbookStep]:
        """
        Consecutive commands in the same working directory → one RunbookStep.
        Each step gets a synthetic title derived from the directory name and
        a brief explanation derived from the commands themselves.
        """
        if not events:
            return []

        groups: list[tuple[str | None, list]] = []
        current_dir: str | None = getattr(events[0], "working_dir", None)
        current_group: list = [events[0]]

        for ev in events[1:]:
            ev_dir = getattr(ev, "working_dir", None)
            if ev_dir == current_dir:
                current_group.append(ev)
            else:
                groups.append((current_dir, current_group))
                current_dir = ev_dir
                current_group = [ev]
        groups.append((current_dir, current_group))

        steps: list[RunbookStep] = []
        for step_num, (work_dir, group_events) in enumerate(groups, start=1):
            cmds = [e.command for e in group_events if e.command]
            dir_label = _dir_label(work_dir)
            title = f"Commands in {dir_label}" if dir_label else f"Step {step_num}"

            # One command → use it directly; multiple → join with &&
            if len(cmds) == 1:
                command = cmds[0]
                explanation = _explain_command(cmds[0])
            else:
                command = " && \\\n  ".join(cmds)
                explanation = f"Run {len(cmds)} commands: " + ", ".join(
                    _short_label(c) for c in cmds[:3]
                ) + ("..." if len(cmds) > 3 else "")

            warning = None
            for c in cmds:
                if _DESTRUCTIVE_RE.search(c or ""):
                    warning = "This step contains a destructive operation. Verify before running."
                    break

            steps.append(
                RunbookStep(
                    step_number=step_num,
                    title=title,
                    command=command,
                    explanation=explanation,
                    warning=warning,
                )
            )

        return steps

    # ── Step 5: extract metadata ──────────────────────────────────────────────

    def _extract_env_vars(
        self, events: list[Union[RawEvent, RedactedEvent]]
    ) -> list[VariableDefinition]:
        seen: set[str] = set()
        variables: list[VariableDefinition] = []

        for ev in events:
            if not ev.command:
                continue
            for match in _ENV_VAR_RE.finditer(ev.command):
                name = match.group(1).upper()
                if name not in seen and len(name) > 2:
                    seen.add(name)
                    variables.append(
                        VariableDefinition(
                            variable_name=name,
                            original_pattern="environment variable assignment",
                            how_to_set=f"export {name}=<value>",
                        )
                    )

        return variables

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_description(self, title: str, steps: list[RunbookStep]) -> str:
        n = len(steps)
        if n == 0:
            return f"Runbook for '{title}' (no signal commands captured)."
        return (
            f"Runbook for '{title}'. "
            f"Contains {n} step{'s' if n != 1 else ''} extracted by deterministic analysis "
            f"(Tier 0 — no AI used)."
        )


# ── Module-level helpers ──────────────────────────────────────────────────────


def _dir_label(working_dir: str | None) -> str:
    if not working_dir:
        return ""
    import os
    return os.path.basename(working_dir.rstrip("/\\")) or working_dir


def _explain_command(cmd: str) -> str:
    """Generate a one-line explanation from common command patterns."""
    cmd = cmd.strip()
    patterns = [
        (r"^git\s+", "Git operation"),
        (r"^docker\s+", "Docker operation"),
        (r"^kubectl\s+", "Kubernetes operation"),
        (r"^helm\s+", "Helm chart operation"),
        (r"^npm\s+|^yarn\s+|^pnpm\s+", "Node.js package operation"),
        (r"^pip\s+|^pip3\s+", "Python package operation"),
        (r"^apt\s+|^apt-get\s+|^brew\s+|^yum\s+|^dnf\s+", "Package installation"),
        (r"^make\s+", "Build step"),
        (r"^python\s+|^python3\s+", "Python script execution"),
        (r"^node\s+", "Node.js script execution"),
        (r"^curl\s+|^wget\s+", "HTTP request"),
        (r"^ssh\s+", "SSH connection"),
        (r"^scp\s+|^rsync\s+", "File transfer"),
        (r"^systemctl\s+", "System service operation"),
        (r"^terraform\s+", "Terraform operation"),
        (r"^ansible\s+", "Ansible operation"),
    ]
    for pattern, label in patterns:
        if re.match(pattern, cmd, re.IGNORECASE):
            return label
    return f"Run: {cmd[:80]}{'...' if len(cmd) > 80 else ''}"


def _short_label(cmd: str) -> str:
    tokens = cmd.strip().split()
    return " ".join(tokens[:3]) if tokens else cmd
