"""
trident.memory.postgres_store — pgvector-backed memory store.

Uses psycopg2 + pgvector for 384-dim cosine similarity search.

Embedding model: sentence-transformers (preferred) or TF-IDF fallback.
Note: TF-IDF embeddings are NOT stable across restarts (vocabulary changes
as the corpus grows). On startup this store re-fits the model from all stored
content and re-embeds any rows with NULL embeddings.

Requires:
  pip install 'trident-cli[postgres]'   # psycopg2-binary, pgvector
  CREATE EXTENSION vector;               # in your Postgres database

Config:
  memory:
    postgres:
      url: "postgresql://user:pass@host:5432/dbname"
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from trident.memory.base import MemoryStore

_TABLE = "trident_chunks"
_DIM = 384


class PostgresStore(MemoryStore):
    """
    pgvector memory store. Chunks are stored with 384-dim embeddings; queries
    use cosine distance (<=>).

    Schema (auto-created):
      trident_chunks(id, store_id, session_id, runbook_id, step_number,
                     chunk_type, title, content, embedding vector(384),
                     created_at)
    """

    def __init__(self, config: dict[str, Any]) -> None:
        try:
            import psycopg2  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Postgres store requires: pip install 'trident-cli[postgres]'"
            ) from exc

        try:
            from pgvector.psycopg2 import register_vector  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "pgvector adapter requires: pip install pgvector"
            ) from exc

        pg_cfg = config["memory"].get("postgres", {})
        self._url = pg_cfg.get("url", "")
        if not self._url:
            raise ValueError("memory.postgres.url must be set in config")

        from trident.memory._embed import TFIDFBackend, get_embedder

        self._embedder, self._stable = get_embedder()
        self._conn = self._connect()
        self._ensure_schema()

        # Warm up TF-IDF from existing content so queries work after a restart.
        if not self._stable:
            self._warm_tfidf()

    # ── MemoryStore interface ─────────────────────────────────────────────────

    def write(self, chunks: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
        import numpy as np

        store_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        texts = [c["text"] for c in chunks]

        if not self._stable:
            # Re-fit on all existing + new texts so vectors are consistent,
            # then re-embed all existing NULL rows before inserting the new ones.
            existing_texts = self._fetch_all_content()
            self._embedder.fit(existing_texts + texts)
            self._reembed_nulls()

        embeddings = self._embedder.embed(texts)

        with self._conn.cursor() as cur:
            for chunk, emb in zip(chunks, embeddings):
                cur.execute(
                    f"""
                    INSERT INTO {_TABLE}
                        (store_id, session_id, runbook_id, step_number,
                         chunk_type, title, content, embedding, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        store_id,
                        metadata.get("session_id", ""),
                        metadata.get("runbook_id", ""),
                        chunk.get("step_number"),
                        chunk.get("type", "chunk"),
                        metadata.get("title", ""),
                        chunk["text"],
                        emb.tolist(),
                        now,
                    ),
                )
        self._conn.commit()
        return store_id

    def query(self, text: str, k: int = 5) -> list[dict[str, Any]]:
        embedding = self._embedder.embed([text])
        vec = embedding[0].tolist()

        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT store_id, title, session_id, runbook_id,
                       chunk_type, step_number, content,
                       1 - (embedding <=> %s::vector) AS score
                FROM {_TABLE}
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (vec, vec, k),
            )
            rows = cur.fetchall()

        return [
            {
                "store_id": r[0],
                "title": r[1],
                "session_id": r[2],
                "runbook_id": r[3],
                "type": r[4],
                "step_number": r[5],
                "text": r[6],
                "score": float(r[7]),
            }
            for r in rows
        ]

    def update(self, store_id: str, content: dict[str, Any]) -> None:
        chunks = content.get("chunks", [])
        metadata = content.get("metadata", {})
        if chunks:
            self.write(chunks, metadata)

    def list(self) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT ON (store_id) store_id, title, session_id, created_at
                FROM {_TABLE}
                ORDER BY store_id, created_at DESC
                """
            )
            rows = cur.fetchall()

        return sorted(
            [
                {
                    "store_id": r[0],
                    "title": r[1],
                    "session_id": r[2],
                    "created_at": r[3].isoformat() if r[3] else "",
                }
                for r in rows
            ],
            key=lambda x: x["created_at"],
            reverse=True,
        )

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _connect(self):
        import psycopg2
        from pgvector.psycopg2 import register_vector

        conn = psycopg2.connect(self._url)
        register_vector(conn)
        return conn

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_TABLE} (
                    id          SERIAL PRIMARY KEY,
                    store_id    TEXT NOT NULL,
                    session_id  TEXT,
                    runbook_id  TEXT,
                    step_number INTEGER,
                    chunk_type  TEXT,
                    title       TEXT,
                    content     TEXT NOT NULL,
                    embedding   vector({_DIM}),
                    created_at  TIMESTAMPTZ DEFAULT NOW()
                )
                """
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_store ON {_TABLE}(store_id)"
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{_TABLE}_emb
                ON {_TABLE} USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
                """
            )
        self._conn.commit()

    def _fetch_all_content(self) -> list[str]:
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT content FROM {_TABLE}")
            return [r[0] for r in cur.fetchall()]

    def _warm_tfidf(self) -> None:
        """Re-fit TF-IDF on all stored content after a cold start."""
        texts = self._fetch_all_content()
        if len(texts) >= 2:
            self._embedder.fit(texts)

    def _reembed_nulls(self) -> None:
        """Re-embed any rows that have a NULL embedding (after a re-fit)."""
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT id, content FROM {_TABLE} WHERE embedding IS NULL")
            rows = cur.fetchall()
        if not rows:
            return
        ids = [r[0] for r in rows]
        texts = [r[1] for r in rows]
        embeddings = self._embedder.embed(texts)
        with self._conn.cursor() as cur:
            for row_id, emb in zip(ids, embeddings):
                cur.execute(
                    f"UPDATE {_TABLE} SET embedding = %s WHERE id = %s",
                    (emb.tolist(), row_id),
                )
        self._conn.commit()
