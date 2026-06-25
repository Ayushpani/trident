"""
trident.memory.markdown_store — file-based memory store (no vectors, no LLM).

The floor for paranoid users or Tier 0 deployments.  Runbooks are written
as Markdown files; an index.json file tracks metadata for search.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trident.memory.base import MemoryStore


class MarkdownStore(MemoryStore):
    """
    Stores runbooks as Markdown files in ~/.trident/memory/runbooks/.
    Queries are substring-matched against titles and tags — no embeddings.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        from trident.config import TRIDENT_DIR
        self._runbooks_dir = TRIDENT_DIR / "memory" / "runbooks"
        self._runbooks_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = TRIDENT_DIR / "memory" / "index.json"

    # ── MemoryStore interface ─────────────────────────────────────────────────

    def write(self, chunks: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
        """
        Write all chunks as a single Markdown file and update the index.

        The overview chunk becomes the file header; step chunks become sections.
        Returns the slug used as the file stem.
        """
        title = metadata.get("title", "untitled")
        session_id = metadata.get("session_id", "")
        runbook_id = metadata.get("runbook_id", "")
        slug = _slugify(title)

        md_path = self._runbooks_dir / f"{slug}.md"
        content = _chunks_to_markdown(chunks, metadata)
        md_path.write_text(content, encoding="utf-8")

        # Update index
        index = self._load_index()
        entry = {
            "slug": slug,
            "title": title,
            "session_id": session_id,
            "runbook_id": runbook_id,
            "path": str(md_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tags": metadata.get("tags", []),
            "step_count": sum(1 for c in chunks if c.get("type") == "step"),
        }
        # Replace existing entry with same slug
        index = [e for e in index if e["slug"] != slug]
        index.insert(0, entry)
        self._save_index(index)

        return slug

    def query(self, text: str, k: int = 5) -> list[dict[str, Any]]:
        """
        Return up to k index entries whose title, slug, or tags contain
        any word from the query (case-insensitive).  Falls back to
        most-recent k entries if no words match.
        """
        index = self._load_index()
        if not index:
            return []

        query_words = [w.lower() for w in text.split() if len(w) > 2]
        scored: list[tuple[int, dict]] = []

        for entry in index:
            score = 0
            haystack = (
                f"{entry.get('title','')} {entry.get('slug','')} "
                f"{' '.join(entry.get('tags', []))}"
            ).lower()
            for word in query_words:
                if word in haystack:
                    score += 1
            scored.append((score, entry))

        scored.sort(key=lambda x: (-x[0], 0))
        results = [entry for _, entry in scored[:k]]

        # Attach a snippet from the markdown file
        for result in results:
            try:
                md = Path(result["path"]).read_text(encoding="utf-8")
                result["snippet"] = md[:400].strip()
            except OSError:
                result["snippet"] = ""

        return results

    def update(self, store_id: str, content: dict[str, Any]) -> None:
        """Re-write the markdown file for the given slug."""
        chunks = content.get("chunks", [])
        metadata = content.get("metadata", {"title": store_id})
        self.write(chunks, metadata)

    def list(self) -> list[dict[str, Any]]:
        """Return all index entries, newest first."""
        return self._load_index()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_index(self) -> list[dict[str, Any]]:
        if not self._index_path.exists():
            return []
        try:
            return json.loads(self._index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _save_index(self, index: list[dict[str, Any]]) -> None:
        self._index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


# ── Module-level helpers ──────────────────────────────────────────────────────


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = slug.strip("-")
    return slug[:80] or "runbook"


def _chunks_to_markdown(chunks: list[dict], metadata: dict) -> str:
    """
    Render a runbook as polished, corporate-ready Markdown.

    Uses the full Runbook dict from metadata["runbook"] when available
    (passed by cli.py process).  Falls back to chunk text for backward compat.
    """
    runbook_data = metadata.get("runbook")
    if runbook_data:
        return _render_from_runbook(runbook_data, metadata)
    return _render_from_chunks(chunks, metadata)


def _render_from_runbook(rb: dict, metadata: dict) -> str:
    title = rb.get("title", "Runbook")
    session_id = metadata.get("session_id", "")
    created_at = metadata.get("created_at", datetime.now(timezone.utc).isoformat())
    tier = metadata.get("tier", "none")
    steps = rb.get("steps", [])
    variables = rb.get("variables", [])
    prerequisites = rb.get("prerequisites", [])
    errors_and_fixes = rb.get("errors_and_fixes", [])
    description = rb.get("description", "")

    # Human-readable timestamp
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        ts = dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        ts = created_at[:16]

    short_session = session_id[:8] if session_id else "unknown"
    tier_label = {
        "none": "Tier 0 — deterministic (no AI)",
        "local": "Tier 1 — local Ollama",
        "byok": "Tier 2 — BYOK (5-agent swarm)",
        "smaran": "Tier 3 — Smaran managed memory",
    }.get(tier, tier)

    L = []

    # ── Header ────────────────────────────────────────────────────────────────
    L += [
        f"# {title}",
        "",
        f"> **Runbook** · Session `{short_session}` · {ts} · {tier_label}",
        "",
        "---",
        "",
    ]

    # ── Table of contents ─────────────────────────────────────────────────────
    L += ["## Table of Contents", ""]
    L.append("1. [Overview](#overview)")
    if prerequisites:
        L.append("2. [Prerequisites](#prerequisites)")
    if variables:
        L.append(f"{'3' if prerequisites else '2'}. [Variables](#variables)")
    step_idx = (2 + bool(prerequisites) + bool(variables)) + 1
    L.append(f"{step_idx - 1}. [Steps](#steps)")
    for s in steps:
        anchor = re.sub(r"[^\w\s-]", "", s.get("title", "").lower())
        anchor = re.sub(r"[\s]+", "-", anchor.strip())
        num = s.get("step_number", "?")
        L.append(f"   - [Step {num}: {s.get('title','')}](#{num}-{anchor})")
    if errors_and_fixes:
        L.append(f"{step_idx}. [Troubleshooting](#troubleshooting)")
    L += ["", "---", ""]

    # ── Overview ──────────────────────────────────────────────────────────────
    L += ["## Overview", ""]
    if description and "no signal commands" not in description.lower():
        L += [description, ""]

    L += [
        "| Field | Value |",
        "|-------|-------|",
        f"| Session ID | `{session_id}` |",
        f"| Generated | {ts} |",
        f"| Synthesis | {tier_label} |",
        f"| Steps | {len(steps)} |",
        f"| Variables | {len(variables)} |",
        "",
        "---",
        "",
    ]

    # ── Prerequisites ─────────────────────────────────────────────────────────
    if prerequisites:
        L += [
            "## Prerequisites",
            "",
            "> Ensure the following are in place before starting.",
            "",
        ]
        for p in prerequisites:
            if isinstance(p, dict):
                name = p.get("name", str(p))
                ptype = p.get("type", "")
                check = p.get("how_to_check", "")
                install = p.get("how_to_install", "")
                version = p.get("version_constraint", "")
                label = f"**{name}**" + (f" `[{ptype}]`" if ptype else "")
                if version:
                    label += f" — version `{version}`"
                L.append(f"- {label}")
                if check:
                    L.append(f"  - Verify: `{check}`")
                if install:
                    L.append(f"  - Install: `{install}`")
            else:
                L.append(f"- {p}")
        L += ["", "---", ""]

    # ── Variables ─────────────────────────────────────────────────────────────
    if variables:
        L += [
            "## Variables",
            "",
            "Set these before running the steps below.",
            "",
            "| Variable | How to set | Source |",
            "|----------|-----------|--------|",
        ]
        for v in variables:
            name = v.get("variable_name", v.get("name", ""))
            how = v.get("how_to_set", "")
            source = v.get("original_pattern", "")
            L.append(f"| `{name}` | `{how}` | {source} |")
        L += ["", "---", ""]

    # ── Steps ─────────────────────────────────────────────────────────────────
    L += ["## Steps", ""]

    for s in steps:
        num = s.get("step_number", "?")
        step_title = s.get("title", f"Step {num}")
        command = s.get("command", "")
        explanation = s.get("explanation", "")
        expected_output = s.get("expected_output", "")
        warning = s.get("warning", "")
        retry_note = s.get("retry_note", "")

        # Anchor-safe heading (GitHub Markdown)
        L.append(f"### Step {num}: {step_title}")
        L.append("")

        if command:
            # Format multi-command chains as one command per line
            clean_cmd = _format_command(command)
            L += ["```bash", clean_cmd, "```", ""]

        if explanation:
            L += [f"**What this does:** {explanation}", ""]

        if expected_output:
            L += [
                "<details>",
                "<summary>Expected output</summary>",
                "",
                "```",
                expected_output,
                "```",
                "",
                "</details>",
                "",
            ]

        if warning:
            L += [f"> ⚠️ **Warning:** {warning}", ""]

        if retry_note:
            L += [f"> 🔄 **If this fails:** {retry_note}", ""]

        L += ["---", ""]

    # ── Errors and fixes ──────────────────────────────────────────────────────
    if errors_and_fixes:
        L += [
            "## Troubleshooting",
            "",
            "These error→fix pairs were observed during the original session.",
            "",
        ]
        for ef in errors_and_fixes:
            if isinstance(ef, dict):
                failed = ef.get("failed_command", "")
                fix = ef.get("final_fix", "")
                lesson = ef.get("lesson", "")
                L.append(f"- **Failed:** `{failed}`")
                if fix:
                    L.append(f"  - **Fix:** `{fix}`")
                if lesson:
                    L.append(f"  - **Lesson:** {lesson}")
            else:
                L.append(f"- {ef}")
        L += ["", "---", ""]

    # ── Footer ────────────────────────────────────────────────────────────────
    L += [
        "",
        "*Generated by [Trident](https://github.com/ayush/trident) · "
        f"{tier_label} · Replay with `trident run`*",
    ]

    return "\n".join(L)


def _format_command(cmd: str) -> str:
    """Return command ready for a bash code block."""
    # Synthesizer already formats multi-command chains with && \<newline> — keep as-is
    if "\n" in cmd:
        return cmd
    # Single-line multi-command: split and indent for readability
    parts = [p.strip() for p in cmd.split("&&")]
    if len(parts) == 1:
        return cmd
    out = [parts[0] + " && \\"]
    for p in parts[1:-1]:
        out.append("  " + p + " && \\")
    out.append("  " + parts[-1])
    return "\n".join(out)


def _render_from_chunks(chunks: list[dict], metadata: dict) -> str:
    """Backward-compat fallback when no Runbook dict is in metadata."""
    title = metadata.get("title", "Runbook")
    session_id = metadata.get("session_id", "")
    created_at = metadata.get("created_at", datetime.now(timezone.utc).isoformat())
    lines = [
        f"# {title}",
        "",
        f"- **Session**: `{session_id}`",
        f"- **Generated**: {created_at}",
        f"- **Tier**: {metadata.get('tier', 'none')} (deterministic)",
        "",
    ]
    for chunk in chunks:
        if chunk.get("type") == "overview":
            lines += ["## Overview", "", chunk["text"], ""]
        elif chunk.get("type") == "step":
            step_num = chunk.get("step_number", "?")
            lines += [f"## Step {step_num}: {chunk['title']}", "", chunk["text"], ""]
    return "\n".join(lines)
