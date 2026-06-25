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


# ── FAISSStore (TF-IDF fallback, no sentence-transformers required) ───────────


def _make_faiss_config(tmp_path: Path) -> dict:
    return {
        "memory": {
            "primary": "faiss",
            "faiss": {"path": str(tmp_path / "faiss")},
        },
        "ai_tier": "none",
    }


@pytest.fixture()
def faiss_store(tmp_path, monkeypatch):
    """FAISSStore forced to TF-IDF backend — no subprocess probe, no torch."""
    import trident.memory.faiss_store as fs_mod

    monkeypatch.setattr(fs_mod, "_sentence_transformers_safe", lambda: False)
    # Reset cached value so the monkeypatch takes effect.
    monkeypatch.setattr(fs_mod, "_ST_SAFE", None)

    from trident.memory.faiss_store import FAISSStore

    return FAISSStore(_make_faiss_config(tmp_path))


def test_faiss_empty_query_returns_empty(faiss_store):
    assert faiss_store.query("deploy auth") == []


def test_faiss_empty_list_returns_empty(faiss_store):
    assert faiss_store.list() == []


def test_faiss_write_returns_store_id(faiss_store):
    sid = faiss_store.write(_sample_chunks(), _sample_metadata())
    assert isinstance(sid, str) and len(sid) == 36  # UUID


def test_faiss_write_populates_index(faiss_store):
    faiss_store.write(_sample_chunks(), _sample_metadata())
    assert faiss_store._index.ntotal == 3  # 3 chunks


def test_faiss_query_returns_results_after_write(faiss_store):
    faiss_store.write(_sample_chunks("Deploy Auth"), _sample_metadata("Deploy Auth"))
    results = faiss_store.query("docker deploy", k=3)
    assert len(results) >= 1
    assert all("text" in r for r in results)


def test_faiss_query_score_in_range(faiss_store):
    faiss_store.write(_sample_chunks(), _sample_metadata())
    results = faiss_store.query("auth", k=3)
    for r in results:
        assert 0.0 < r["score"] <= 1.0


def test_faiss_list_after_two_writes(faiss_store):
    faiss_store.write(_sample_chunks("Auth"), _sample_metadata("Auth"))
    faiss_store.write(_sample_chunks("Database"), _sample_metadata("Database"))
    entries = faiss_store.list()
    assert len(entries) == 2
    titles = {e["title"] for e in entries}
    assert "Auth" in titles and "Database" in titles


def test_faiss_persistence(tmp_path, monkeypatch):
    """Index and metadata survive a reload from disk; TF-IDF is refitted on load."""
    import trident.memory.faiss_store as fs_mod

    monkeypatch.setattr(fs_mod, "_sentence_transformers_safe", lambda: False)
    monkeypatch.setattr(fs_mod, "_ST_SAFE", None)

    from trident.memory.faiss_store import FAISSStore

    cfg = _make_faiss_config(tmp_path)

    store1 = FAISSStore(cfg)
    store1.write(_sample_chunks("Persist Test"), _sample_metadata("Persist Test"))
    # store1._save() is called by write(); explicitly saving again is harmless
    store1._save()

    # Fresh instance — loads index from disk and refits TF-IDF from stored meta.
    monkeypatch.setattr(fs_mod, "_ST_SAFE", None)
    store2 = FAISSStore(cfg)

    assert store2._index.ntotal == 3
    results = store2.query("persist", k=3)
    assert len(results) >= 1
