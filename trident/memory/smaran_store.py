"""
trident.memory.smaran_store — Smaran (supermemory) REST API memory store.

Writes runbook chunks to Smaran as documents; queries via semantic search.
Smaran handles embedding and vector search on its end — no local ML needed.

REST API (api.smaran.ai):
  POST /v3/documents              — add a document/memory
  POST /v3/search                 — semantic search
  POST /v3/documents/documents    — paginated document list

Config:
  memory:
    smaran:
      api_key: "sm_..."
      endpoint: "https://api.smaran.ai"   # optional override
      container_tag: "trident"            # optional namespace
"""

from __future__ import annotations

import uuid
from typing import Any

from trident.memory.base import MemoryStore

_DEFAULT_ENDPOINT = "https://api.smaran.ai"


class SmaranStore(MemoryStore):
    """
    Memory store backed by the Smaran (supermemory) cloud API.

    Each chunk is uploaded as a separate document with a shared store_id in
    the metadata. Queries use Smaran's semantic (hybrid) search.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        smaran_cfg = config["memory"].get("smaran", {})
        self._api_key = smaran_cfg.get("api_key", "")
        if not self._api_key:
            raise ValueError(
                "memory.smaran.api_key must be set in config (get one at smaran.ai)"
            )

        self._endpoint = smaran_cfg.get("endpoint", _DEFAULT_ENDPOINT).rstrip("/")
        self._container_tag = smaran_cfg.get("container_tag", "trident")

        try:
            import httpx  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "SmaranStore requires: pip install httpx (should already be installed)"
            ) from exc

    # ── MemoryStore interface ─────────────────────────────────────────────────

    def write(self, chunks: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
        import httpx

        store_id = str(uuid.uuid4())
        title = metadata.get("title", "Trident Runbook")

        with httpx.Client(timeout=30.0) as client:
            for chunk in chunks:
                payload = {
                    "content": chunk["text"],
                    "title": f"{title} — {chunk.get('type', 'chunk')}",
                    "containerTags": [self._container_tag],
                    "metadata": {
                        "store_id": store_id,
                        "session_id": metadata.get("session_id", ""),
                        "runbook_id": metadata.get("runbook_id", ""),
                        "step_number": chunk.get("step_number"),
                        "chunk_type": chunk.get("type", "chunk"),
                        "source": "trident",
                    },
                }
                resp = client.post(
                    f"{self._endpoint}/v3/documents",
                    json=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()

        return store_id

    def query(self, text: str, k: int = 5) -> list[dict[str, Any]]:
        import httpx

        payload = {
            "q": text,
            "containerTags": [self._container_tag],
            "limit": k,
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{self._endpoint}/v3/search",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()

        data = resp.json()
        results = []
        for item in data.get("results", []):
            # Smaran returns SearchResult objects with chunks array.
            chunks = item.get("chunks", [])
            text_content = " ".join(
                c.get("text", c.get("content", "")) for c in chunks
            ) if chunks else item.get("content", "")
            meta = item.get("metadata", {})
            results.append(
                {
                    "store_id": meta.get("store_id", item.get("documentId", "")),
                    "title": item.get("title", ""),
                    "session_id": meta.get("session_id", ""),
                    "runbook_id": meta.get("runbook_id", ""),
                    "type": meta.get("chunk_type", item.get("type", "chunk")),
                    "step_number": meta.get("step_number"),
                    "text": text_content,
                    "score": float(item.get("score", 0.0)),
                }
            )
        return results

    def update(self, store_id: str, content: dict[str, Any]) -> None:
        chunks = content.get("chunks", [])
        metadata = content.get("metadata", {})
        if chunks:
            self.write(chunks, metadata)

    def list(self) -> list[dict[str, Any]]:
        import httpx

        payload = {
            "page": 1,
            "limit": 50,
            "sort": "createdAt",
            "order": "desc",
            "containerTags": [self._container_tag],
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{self._endpoint}/v3/documents/documents",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()

        data = resp.json()
        seen: dict[str, dict] = {}
        for doc in data.get("documents", []):
            # Group by store_id from metadata so Trident runbooks appear as units.
            mem_entries = doc.get("memoryEntries", [])
            store_id = ""
            if mem_entries:
                meta = mem_entries[0].get("metadata", {}) or {}
                store_id = meta.get("store_id", "")
            if not store_id:
                store_id = doc.get("id", str(uuid.uuid4()))

            if store_id not in seen:
                seen[store_id] = {
                    "store_id": store_id,
                    "title": doc.get("title", ""),
                    "session_id": "",
                    "created_at": doc.get("createdAt", ""),
                }
        return list(seen.values())

    # ── Internal ──────────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
