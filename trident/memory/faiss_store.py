"""
trident.memory.faiss_store — local vector store using FAISS + sentence-transformers.

Requires: pip install 'trident-cli[faiss]'
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from trident.memory.base import MemoryStore


class FAISSStore(MemoryStore):
    """
    Local vector memory store using FAISS for ANN search and
    all-MiniLM-L6-v2 for 384-dim sentence embeddings.

    Index stored at config['memory']['faiss']['path']/index.bin
    Metadata stored at config['memory']['faiss']['path']/meta.json
    """

    def __init__(self, config: dict[str, Any]) -> None:
        try:
            import faiss  # noqa: F401
            from sentence_transformers import SentenceTransformer  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "FAISS store requires: pip install 'trident-cli[faiss]'"
            ) from exc

        faiss_cfg = config["memory"].get("faiss", {})
        self._store_path = Path(faiss_cfg.get("path", "~/.trident/memory/faiss")).expanduser()
        self._store_path.mkdir(parents=True, exist_ok=True)
        self._index_path = self._store_path / "index.bin"
        self._meta_path = self._store_path / "meta.json"

        model_name = faiss_cfg.get("embedding_model", "all-MiniLM-L6-v2")
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)
        self._dim = 384  # all-MiniLM-L6-v2 output dimension

        self._index = self._load_or_create_index()
        self._meta: list[dict] = self._load_meta()

    # ── MemoryStore interface ─────────────────────────────────────────────────

    def write(self, chunks: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
        import faiss

        store_id = str(uuid.uuid4())
        texts = [c["text"] for c in chunks]
        embeddings = self._embed(texts)

        self._index.add(embeddings)  # type: ignore[arg-type]

        for i, chunk in enumerate(chunks):
            self._meta.append(
                {
                    "store_id": store_id,
                    "faiss_idx": self._index.ntotal - len(chunks) + i,
                    "text": chunk["text"],
                    "type": chunk.get("type", "chunk"),
                    "step_number": chunk.get("step_number"),
                    "title": metadata.get("title", ""),
                    "session_id": metadata.get("session_id", ""),
                    "runbook_id": metadata.get("runbook_id", ""),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        self._save()
        return store_id

    def query(self, text: str, k: int = 5) -> list[dict[str, Any]]:
        if self._index.ntotal == 0:
            return []

        embedding = self._embed([text])
        actual_k = min(k, self._index.ntotal)
        distances, indices = self._index.search(embedding, actual_k)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self._meta):
                continue
            entry = dict(self._meta[idx])
            entry["score"] = float(1.0 / (1.0 + dist))  # convert L2 distance to similarity
            results.append(entry)

        return results

    def update(self, store_id: str, content: dict[str, Any]) -> None:
        # FAISS doesn't support deletion; rebuild the entries for this store_id
        # For simplicity: append new chunks (old ones remain but rank lower)
        chunks = content.get("chunks", [])
        metadata = content.get("metadata", {})
        if chunks:
            self.write(chunks, metadata)

    def list(self) -> list[dict[str, Any]]:
        seen: dict[str, dict] = {}
        for entry in reversed(self._meta):
            sid = entry.get("store_id", "")
            if sid and sid not in seen:
                seen[sid] = {
                    "store_id": sid,
                    "title": entry.get("title", ""),
                    "session_id": entry.get("session_id", ""),
                    "created_at": entry.get("created_at", ""),
                }
        return list(seen.values())

    # ── Internal ──────────────────────────────────────────────────────────────

    def _embed(self, texts: list[str]):
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return embeddings.astype("float32")

    def _load_or_create_index(self):
        import faiss
        if self._index_path.exists():
            return faiss.read_index(str(self._index_path))
        return faiss.IndexFlatL2(self._dim)

    def _load_meta(self) -> list[dict]:
        if not self._meta_path.exists():
            return []
        try:
            return json.loads(self._meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self) -> None:
        import faiss
        faiss.write_index(self._index, str(self._index_path))
        self._meta_path.write_text(
            json.dumps(self._meta, ensure_ascii=False), encoding="utf-8"
        )
