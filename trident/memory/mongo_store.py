"""
trident.memory.mongo_store — MongoDB memory store with Python-side vector search.

Stores chunks with embeddings as regular BSON arrays. Similarity search is
computed in Python using numpy cosine similarity — this is correct for
collections up to ~50k chunks.

For Atlas M10+ with mongot, swap the query() implementation to use
$vectorSearch aggregation.

Requires:
  pip install 'trident-cli[mongo]'

Config:
  memory:
    mongo:
      url: "mongodb://user:pass@host:27017"
      database: "trident"          # optional, default: trident
      collection: "chunks"         # optional, default: chunks
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from trident.memory.base import MemoryStore

_DIM = 384


class MongoStore(MemoryStore):
    """
    MongoDB memory store.

    Each chunk is stored as a document:
      { store_id, session_id, runbook_id, step_number, chunk_type, title,
        content, embedding: [float x 384], created_at }

    Similarity search fetches all documents with embeddings and ranks by
    cosine similarity in Python (numpy). A text-search fallback is used when
    no embeddings are available.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        try:
            import pymongo  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Mongo store requires: pip install 'trident-cli[mongo]'"
            ) from exc

        mongo_cfg = config["memory"].get("mongo", {})
        self._url = mongo_cfg.get("url", "")
        if not self._url:
            raise ValueError("memory.mongo.url must be set in config")

        db_name = mongo_cfg.get("database", "trident")
        coll_name = mongo_cfg.get("collection", "chunks")

        import pymongo

        self._client = pymongo.MongoClient(self._url, serverSelectionTimeoutMS=5_000)
        self._col = self._client[db_name][coll_name]
        self._ensure_indexes()

        from trident.memory._embed import get_embedder

        self._embedder, self._stable = get_embedder()

        # Warm TF-IDF from stored content on cold start.
        if not self._stable:
            self._warm_tfidf()

    # ── MemoryStore interface ─────────────────────────────────────────────────

    def write(self, chunks: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
        store_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        texts = [c["text"] for c in chunks]

        if not self._stable:
            existing = self._fetch_all_content()
            self._embedder.fit(existing + texts)

        embeddings = self._embedder.embed(texts)

        docs = []
        for chunk, emb in zip(chunks, embeddings):
            docs.append(
                {
                    "store_id": store_id,
                    "session_id": metadata.get("session_id", ""),
                    "runbook_id": metadata.get("runbook_id", ""),
                    "step_number": chunk.get("step_number"),
                    "chunk_type": chunk.get("type", "chunk"),
                    "title": metadata.get("title", ""),
                    "content": chunk["text"],
                    "embedding": emb.tolist(),
                    "created_at": now,
                }
            )
        self._col.insert_many(docs)
        return store_id

    def query(self, text: str, k: int = 5) -> list[dict[str, Any]]:
        import numpy as np

        query_emb = self._embedder.embed([text])[0]

        # Fetch all docs that have an embedding.
        cursor = self._col.find(
            {"embedding": {"$exists": True, "$ne": None}},
            {"_id": 0, "store_id": 1, "title": 1, "session_id": 1, "runbook_id": 1,
             "chunk_type": 1, "step_number": 1, "content": 1, "embedding": 1},
        )
        docs = list(cursor)

        if not docs:
            # Text-search fallback when no embeddings are stored.
            return self._text_search(text, k)

        # Cosine similarity in Python.
        corpus_embs = np.array([d["embedding"] for d in docs], dtype="float32")
        q_norm = np.linalg.norm(query_emb)
        if q_norm < 1e-8:
            return []

        c_norms = np.linalg.norm(corpus_embs, axis=1) + 1e-8
        scores = corpus_embs @ query_emb / (c_norms * q_norm)

        top_idx = np.argsort(scores)[::-1][:k]
        results = []
        for i in top_idx:
            d = docs[i]
            results.append(
                {
                    "store_id": d["store_id"],
                    "title": d.get("title", ""),
                    "session_id": d.get("session_id", ""),
                    "runbook_id": d.get("runbook_id", ""),
                    "type": d.get("chunk_type", "chunk"),
                    "step_number": d.get("step_number"),
                    "text": d["content"],
                    "score": float(scores[i]),
                }
            )
        return results

    def update(self, store_id: str, content: dict[str, Any]) -> None:
        chunks = content.get("chunks", [])
        metadata = content.get("metadata", {})
        if chunks:
            self.write(chunks, metadata)

    def list(self) -> list[dict[str, Any]]:
        pipeline = [
            {"$sort": {"created_at": -1}},
            {
                "$group": {
                    "_id": "$store_id",
                    "title": {"$first": "$title"},
                    "session_id": {"$first": "$session_id"},
                    "created_at": {"$first": "$created_at"},
                }
            },
            {"$sort": {"created_at": -1}},
        ]
        results = []
        for doc in self._col.aggregate(pipeline):
            results.append(
                {
                    "store_id": doc["_id"],
                    "title": doc.get("title", ""),
                    "session_id": doc.get("session_id", ""),
                    "created_at": doc["created_at"].isoformat()
                    if doc.get("created_at")
                    else "",
                }
            )
        return results

    def close(self) -> None:
        self._client.close()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _ensure_indexes(self) -> None:
        self._col.create_index("store_id")
        self._col.create_index([("content", "text")])  # for text-search fallback

    def _fetch_all_content(self) -> list[str]:
        return [
            d["content"]
            for d in self._col.find({}, {"_id": 0, "content": 1})
        ]

    def _warm_tfidf(self) -> None:
        texts = self._fetch_all_content()
        if len(texts) >= 2:
            self._embedder.fit(texts)

    def _text_search(self, text: str, k: int) -> list[dict[str, Any]]:
        """MongoDB full-text search fallback when no embeddings exist."""
        cursor = self._col.find(
            {"$text": {"$search": text}},
            {
                "_id": 0,
                "store_id": 1, "title": 1, "session_id": 1, "runbook_id": 1,
                "chunk_type": 1, "step_number": 1, "content": 1,
                "score": {"$meta": "textScore"},
            },
        ).sort([("score", {"$meta": "textScore"})]).limit(k)
        return [
            {
                "store_id": d["store_id"],
                "title": d.get("title", ""),
                "session_id": d.get("session_id", ""),
                "runbook_id": d.get("runbook_id", ""),
                "type": d.get("chunk_type", "chunk"),
                "step_number": d.get("step_number"),
                "text": d["content"],
                "score": float(d.get("score", 0.0)),
            }
            for d in cursor
        ]
