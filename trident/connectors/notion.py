"""
trident.connectors.notion — Phase 9 stub.

Pushes runbooks to a Notion database via the Notion REST API.
"""

from __future__ import annotations

from shellstory.models import Runbook


def export(runbook: Runbook, api_key: str, database_id: str) -> str:
    raise NotImplementedError("notion.export — Phase 9")
