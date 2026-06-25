"""
tests.test_memory_stores — MarkdownStore write/query/list cycle.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trident.memory.markdown_store import MarkdownStore


def _make_config(tmp_path: Path) -> dict:
    return {
        "memory": {"primary": "markdown"},
        "ai_tier": "none",
    }


def _patch_store_dir(store: MarkdownStore, tmp_path: Path) -> None:
    """Redirect the store's paths to a temp directory."""
    store._runbooks_dir = tmp_path / "runbooks"
    store._runbooks_dir.mkdir(parents=True, exist_ok=True)
    store._index_path = tmp_path / "index.json"


def _sample_chunks(title: str = "Deploy Auth") -> list[dict]:
    return [
        {
            "text": f"Runbook: {title}\nDeploy the auth service to production.",
            "type": "overview",
            "title": title,
            "session_id": str(uuid.uuid4()),
            "runbook_id": str(uuid.uuid4()),
            "step_number": None,
        },
        {
            "text": "Step 1: Build Docker image\nCommand:\n  docker build -t auth:latest .",
            "type": "step",
            "title": "Build Docker image",
            "session_id": "sess1",
            "runbook_id": "rb1",
            "step_number": 1,
        },
        {
            "text": "Step 2: Push to registry\nCommand:\n  docker push registry.io/auth:latest",
            "type": "step",
            "title": "Push to registry",
            "session_id": "sess1",
            "runbook_id": "rb1",
            "step_number": 2,
        },
    ]


def _sample_metadata(title: str = "Deploy Auth") -> dict:
    return {
        "title": title,
        "session_id": str(uuid.uuid4()),
        "runbook_id": str(uuid.uuid4()),
        "tier": "none",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tags": ["auth", "docker"],
    }


# ── MarkdownStore ─────────────────────────────────────────────────────────────


def test_write_creates_markdown_file(tmp_path):
    store = MarkdownStore({})
    _patch_store_dir(store, tmp_path)

    chunks = _sample_chunks()
    meta = _sample_metadata()
    slug = store.write(chunks, meta)

    md_file = tmp_path / "runbooks" / f"{slug}.md"
    assert md_file.exists()
    content = md_file.read_text(encoding="utf-8")
    assert "Deploy Auth" in content
    assert "docker build" in content


def test_write_updates_index(tmp_path):
    store = MarkdownStore({})
    _patch_store_dir(store, tmp_path)

    store.write(_sample_chunks(), _sample_metadata("Deploy Auth"))
    store.write(_sample_chunks("Setup DB"), _sample_metadata("Setup DB"))

    index = store._load_index()
    titles = [e["title"] for e in index]
    assert "Deploy Auth" in titles
    assert "Setup DB" in titles


def test_list_returns_newest_first(tmp_path):
    store = MarkdownStore({})
    _patch_store_dir(store, tmp_path)

    store.write(_sample_chunks("First"), _sample_metadata("First"))
    store.write(_sample_chunks("Second"), _sample_metadata("Second"))

    entries = store.list()
    # Second was written last → should be first in list
    assert entries[0]["title"] == "Second"


def test_query_finds_matching_title(tmp_path):
    store = MarkdownStore({})
    _patch_store_dir(store, tmp_path)

    store.write(_sample_chunks("Deploy Auth Service"), _sample_metadata("Deploy Auth Service"))
    store.write(_sample_chunks("Setup Database"), _sample_metadata("Setup Database"))

    results = store.query("auth deploy", k=5)
    assert results
    assert results[0]["title"] == "Deploy Auth Service"


def test_query_falls_back_to_recency(tmp_path):
    """When no words match, returns most recent entries."""
    store = MarkdownStore({})
    _patch_store_dir(store, tmp_path)

    store.write(_sample_chunks("Migrate Postgres"), _sample_metadata("Migrate Postgres"))
    store.write(_sample_chunks("Deploy Redis"), _sample_metadata("Deploy Redis"))

    results = store.query("xylophone banana", k=5)
    # No matches — should return something (recency fallback)
    assert len(results) >= 1


def test_query_returns_snippet(tmp_path):
    store = MarkdownStore({})
    _patch_store_dir(store, tmp_path)

    store.write(_sample_chunks("Auth Runbook"), _sample_metadata("Auth Runbook"))
    results = store.query("auth", k=1)
    assert results
    assert "snippet" in results[0]
    assert len(results[0]["snippet"]) > 0


def test_update_overwrites_existing(tmp_path):
    store = MarkdownStore({})
    _patch_store_dir(store, tmp_path)

    store.write(_sample_chunks("Update Test"), _sample_metadata("Update Test"))

    new_chunks = [
        {
            "text": "Runbook: Update Test\nUpdated content.",
            "type": "overview",
            "title": "Update Test",
            "session_id": "s1",
            "runbook_id": "r1",
            "step_number": None,
        }
    ]
    store.update("update-test", {"chunks": new_chunks, "metadata": {"title": "Update Test"}})

    results = store.query("Update Test", k=1)
    assert results
    md_path = Path(results[0]["path"])
    content = md_path.read_text()
    assert "Updated content" in content


def test_empty_store_query_returns_empty(tmp_path):
    store = MarkdownStore({})
    _patch_store_dir(store, tmp_path)

    results = store.query("anything")
    assert results == []


def test_empty_store_list_returns_empty(tmp_path):
    store = MarkdownStore({})
    _patch_store_dir(store, tmp_path)

    assert store.list() == []
