"""
trident.connectors.obsidian — write runbooks into an Obsidian vault.

Writes a Markdown file with YAML frontmatter (tags, date, session_id) into
the specified vault subfolder. No external dependencies required — plain
filesystem writes.

Config (optional):
  connectors:
    obsidian:
      vault_path: "~/Documents/MyVault"
      subfolder: "runbooks"
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shellstory.models import Runbook


def export(
    runbook: Runbook,
    vault_path: str,
    subfolder: str = "runbooks",
) -> str:
    """
    Write *runbook* as a Markdown file in the Obsidian vault.

    Returns the absolute path of the written file.
    """
    vault = Path(vault_path).expanduser()
    target_dir = vault / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(runbook.title)
    out_path = target_dir / f"{slug}.md"

    content = _render_markdown(runbook)
    out_path.write_text(content, encoding="utf-8")
    return str(out_path)


def export_from_config(runbook: Runbook, config: dict[str, Any]) -> str:
    """Export using vault_path and subfolder from the trident config."""
    obs_cfg = config.get("connectors", {}).get("obsidian", {})
    vault_path = obs_cfg.get("vault_path", "")
    if not vault_path:
        raise ValueError(
            "connectors.obsidian.vault_path must be set in config"
        )
    subfolder = obs_cfg.get("subfolder", "runbooks")
    return export(runbook, vault_path, subfolder)


# ── Rendering ─────────────────────────────────────────────────────────────────


def _render_markdown(runbook: Runbook) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tags = _extract_tags(runbook)
    tag_list = "\n".join(f"  - {t}" for t in tags)

    lines = [
        "---",
        f"title: {runbook.title}",
        f"date: {now}",
        f"session_id: {runbook.session_id or ''}",
        f"runbook_id: {runbook.id or ''}",
        "tags:",
        tag_list,
        "---",
        "",
        f"# {runbook.title}",
        "",
    ]

    if runbook.description:
        lines += [runbook.description, ""]

    if runbook.variables:
        lines += ["## Variables", ""]
        for v in runbook.variables:
            example = f" (e.g. `{v.example}`)" if v.example else ""
            lines.append(f"- `{v.name}`{example}: {v.description or ''}")
        lines.append("")

    if runbook.prerequisites:
        lines += ["## Prerequisites", ""]
        for p in runbook.prerequisites:
            lines.append(f"- {p}")
        lines.append("")

    if runbook.steps:
        lines += ["## Steps", ""]
        for i, step in enumerate(runbook.steps, 1):
            lines.append(f"### Step {i}: {step.title}")
            lines.append("")
            if step.working_dir:
                lines.append(f"**Directory:** `{step.working_dir}`")
                lines.append("")
            if step.command:
                lines.append("```bash")
                lines.append(step.command)
                lines.append("```")
                lines.append("")
            if step.explanation:
                lines.append(step.explanation)
                lines.append("")

    if runbook.errors_and_fixes:
        lines += ["## Errors & Fixes", ""]
        for ef in runbook.errors_and_fixes:
            lines.append(f"- {ef}")
        lines.append("")

    return "\n".join(lines)


def _slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:80] or "runbook"


def _extract_tags(runbook: Runbook) -> list[str]:
    tags = ["trident", "runbook"]
    if runbook.title:
        for word in runbook.title.lower().split():
            if len(word) > 3 and word not in tags:
                tags.append(word)
    return tags[:10]
