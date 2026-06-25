"""
trident.connectors.notion — push runbooks to a Notion database.

Uses the Notion REST API (https://api.notion.com/v1) via httpx.
Creates a new page in the specified database for each runbook.

Requires:
  - A Notion integration token with write access to the database
  - The target database must have at least a "Name" title property

Config (optional):
  connectors:
    notion:
      api_key: "secret_..."
      database_id: "abc123..."
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from shellstory.models import Runbook

_NOTION_API = "https://api.notion.com/v1"
_API_VERSION = "2022-06-28"


def export(
    runbook: Runbook,
    api_key: str,
    database_id: str,
) -> str:
    """
    Create a Notion page for *runbook* in *database_id*.

    Returns the URL of the created Notion page.
    """
    import httpx

    client = httpx.Client(
        base_url=_NOTION_API,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": _API_VERSION,
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )

    page_payload = _build_page_payload(runbook, database_id)

    resp = client.post("/pages", json=page_payload)
    resp.raise_for_status()
    page = resp.json()
    return page.get("url", page.get("id", ""))


def export_from_config(runbook: Runbook, config: dict[str, Any]) -> str:
    """Export using api_key and database_id from the trident config."""
    notion_cfg = config.get("connectors", {}).get("notion", {})
    api_key = notion_cfg.get("api_key", "")
    database_id = notion_cfg.get("database_id", "")
    if not api_key:
        raise ValueError("connectors.notion.api_key must be set in config")
    if not database_id:
        raise ValueError("connectors.notion.database_id must be set in config")
    return export(runbook, api_key, database_id)


# ── Notion block builders ──────────────────────────────────────────────────────


def _build_page_payload(runbook: Runbook, database_id: str) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()

    blocks: list[dict] = []

    if runbook.description:
        blocks.append(_paragraph(runbook.description))

    if runbook.variables:
        blocks.append(_heading2("Variables"))
        for v in runbook.variables:
            example = f" — e.g. `{v.example}`" if v.example else ""
            blocks.append(_bullet(f"`{v.name}`{example}: {v.description or ''}"))

    if runbook.prerequisites:
        blocks.append(_heading2("Prerequisites"))
        for p in runbook.prerequisites:
            blocks.append(_bullet(p))

    if runbook.steps:
        blocks.append(_heading2("Steps"))
        for i, step in enumerate(runbook.steps, 1):
            blocks.append(_heading3(f"Step {i}: {step.title}"))
            if step.working_dir:
                blocks.append(_paragraph(f"Directory: {step.working_dir}"))
            if step.command:
                blocks.append(_code_block(step.command, language="bash"))
            if step.explanation:
                blocks.append(_paragraph(step.explanation))

    if runbook.errors_and_fixes:
        blocks.append(_heading2("Errors & Fixes"))
        for ef in runbook.errors_and_fixes:
            blocks.append(_bullet(ef))

    return {
        "parent": {"database_id": database_id},
        "properties": {
            "Name": {"title": [{"text": {"content": runbook.title}}]},
        },
        "children": blocks[:100],  # Notion page creation supports up to 100 blocks
    }


def _rich_text(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": text[:2000]}}]


def _paragraph(text: str) -> dict:
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": _rich_text(text)}}


def _heading2(text: str) -> dict:
    return {"object": "block", "type": "heading_2",
            "heading_2": {"rich_text": _rich_text(text)}}


def _heading3(text: str) -> dict:
    return {"object": "block", "type": "heading_3",
            "heading_3": {"rich_text": _rich_text(text)}}


def _bullet(text: str) -> dict:
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": _rich_text(text)}}


def _code_block(code: str, language: str = "plain text") -> dict:
    return {
        "object": "block",
        "type": "code",
        "code": {
            "rich_text": _rich_text(code[:2000]),
            "language": language,
        },
    }
