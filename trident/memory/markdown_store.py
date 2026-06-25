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
            lines.append("## Overview")
            lines.append("")
            lines.append(chunk["text"])
            lines.append("")
        elif chunk.get("type") == "step":
            step_num = chunk.get("step_number", "?")
            lines.append(f"## Step {step_num}: {chunk['title']}")
            lines.append("")
            lines.append(chunk["text"])
            lines.append("")

    return "\n".join(lines)
