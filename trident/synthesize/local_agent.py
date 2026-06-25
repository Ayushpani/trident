"""
trident.synthesize.local_agent — Tier 1: single-agent Ollama synthesis.

One prompt to a local Ollama instance; falls back to DeterministicSynthesizer
if Ollama is unreachable.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Union

from shellstory.models import (
    RawEvent,
    RedactedEvent,
    Runbook,
    RunbookStep,
    VariableDefinition,
)


_SYSTEM_PROMPT = """\
You are a senior DevOps engineer writing runbooks.
Given a list of shell commands from a terminal session, extract the signal
commands (skip navigation, probing, history) and group them into ordered
runbook steps with clear titles and brief explanations.

Respond with valid JSON only:
{
  "description": "<one sentence summary>",
  "steps": [
    {"title": "...", "command": "...", "explanation": "..."},
    ...
  ]
}
"""


class LocalAgentSynthesizer:
    """
    Single-agent synthesis via Ollama HTTP API.

    Falls back to DeterministicSynthesizer if Ollama is unreachable or
    returns unparseable output.
    """

    def __init__(self, config: dict) -> None:
        self._model = config.get("llm", {}).get("model", "llama3:8b")
        self._base_url = "http://localhost:11434"

    def synthesize(
        self,
        events: list[Union[RawEvent, RedactedEvent]],
        title: str,
        session_id: str = "",
    ) -> Runbook:
        cmd_events = [e for e in events if e.event_type == "command" and e.command]
        if not cmd_events:
            return self._fallback(events, title, session_id)

        commands_text = "\n".join(
            f"[exit:{e.exit_code}] {e.command}" for e in cmd_events
        )
        user_prompt = f"Session title: {title}\n\nCommands:\n{commands_text}"

        try:
            result = self._call_ollama(user_prompt)
            return self._parse_response(result, title, session_id, cmd_events)
        except Exception:
            return self._fallback(events, title, session_id)

    def _call_ollama(self, user_prompt: str) -> str:
        import httpx

        response = httpx.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "format": "json",
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]

    def _parse_response(
        self,
        content: str,
        title: str,
        session_id: str,
        cmd_events: list,
    ) -> Runbook:
        # Extract JSON from response (may have surrounding text)
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError("No JSON found in Ollama response")

        data = json.loads(match.group())
        raw_steps = data.get("steps", [])
        description = data.get("description", f"Runbook for '{title}'.")

        steps = []
        for i, s in enumerate(raw_steps, 1):
            steps.append(
                RunbookStep(
                    step_number=i,
                    title=s.get("title", f"Step {i}"),
                    command=s.get("command"),
                    explanation=s.get("explanation", ""),
                )
            )

        return Runbook(
            id=str(uuid.uuid4()),
            session_id=session_id or str(uuid.uuid4()),
            title=title,
            description=description,
            created_at=datetime.now(timezone.utc),
            variables=[],
            prerequisites=[],
            steps=steps,
            errors_and_fixes=[],
            raw_signal_commands=[e.command for e in cmd_events if e.command],
        )

    def _fallback(
        self,
        events: list[Union[RawEvent, RedactedEvent]],
        title: str,
        session_id: str,
    ) -> Runbook:
        from trident.synthesize.deterministic import DeterministicSynthesizer
        return DeterministicSynthesizer().synthesize(events, title, session_id)
