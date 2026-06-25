"""
trident.synthesize.swarm — Tier 2/3: wraps ShellStory's SwarmOrchestrator.

The 5-agent swarm (Signal → Failure+Prereq → Sequence → Annotation → Merger)
runs via ShellStory's existing orchestration.  Trident injects its LLM config
into the format ShellStory expects.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Union

from shellstory.agents.swarm import SwarmOrchestrator
from shellstory.models import RawEvent, RedactedEvent, Runbook, Session


class SwarmSynthesizer:
    """
    Wraps ShellStory's SwarmOrchestrator for Tier 2 (BYOK) and Tier 3 (Smaran).

    ShellStory's swarm expects a config dict with a 'llm' key matching its own
    schema.  We translate Trident's config into that format here.
    """

    def __init__(self, config: dict) -> None:
        llm_cfg = config.get("llm", {})

        # Build the ShellStory-compatible config block
        self._shellstory_config = {
            "llm": {
                "provider": llm_cfg.get("provider", "openrouter"),
                "api_key": llm_cfg.get("api_key", ""),
                "model": llm_cfg.get("model", "anthropic/claude-sonnet-4"),
                "site_url": llm_cfg.get("site_url", ""),
                "app_name": "trident",
                "model_overrides": llm_cfg.get("model_overrides", {}),
            },
            "default_connector": "markdown",
            "sessions_dir": config.get("capture", {}).get("sessions_dir", "~/.trident/sessions"),
        }

    def synthesize(
        self,
        events: list[Union[RawEvent, RedactedEvent]],
        title: str,
        session_id: str = "",
    ) -> Runbook:
        session = Session(
            id=session_id or str(uuid.uuid4()),
            title=title,
            started_at=datetime.now(timezone.utc),
            capture_file="",
            status="processing",
        )

        # SwarmOrchestrator.run() accepts RawEvent or RedactedEvent (duck-typed)
        orchestrator = SwarmOrchestrator(config=self._shellstory_config)
        try:
            return asyncio.run(orchestrator.run(session, list(events)))
        except Exception:
            # If the swarm fails (API key invalid, rate limit, etc.), fall back
            from trident.synthesize.deterministic import DeterministicSynthesizer
            return DeterministicSynthesizer().synthesize(events, title, session_id)
