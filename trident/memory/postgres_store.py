"""
trident.memory.postgres_store — pgvector-backed memory store.

Requires: pip install 'trident-cli[postgres]'
Config key: memory.postgres.url (postgres DSN)
"""

from __future__ import annotations

from typing import Any

from trident.memory.base import MemoryStore


class PostgresStore(MemoryStore):
    """
    Stores chunks in Postgres with pgvector for similarity search.

    Table: trident_chunks(id, session_id, runbook_id, content, embedding vector(384),
                          metadata jsonb, created_at)
    """

    def __init__(self, config: dict[str, Any]) -> None:
        try:
            import psycopg2  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Postgres store requires: pip install 'trident-cli[postgres]'"
            ) from exc

        self._url = config["memory"]["postgres"]["url"]
        if not self._url:
            raise ValueError("memory.postgres.url must be set in config")

        self._conn = None
        self._ensure_schema()

    def write(self, chunks: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
        raise NotImplementedError("PostgresStore.write — Phase 5")

    def query(self, text: str, k: int = 5) -> list[dict[str, Any]]:
        raise NotImplementedError("PostgresStore.query — Phase 5")

    def update(self, store_id: str, content: dict[str, Any]) -> None:
        raise NotImplementedError("PostgresStore.update — Phase 5")

    def list(self) -> list[dict[str, Any]]:
        raise NotImplementedError("PostgresStore.list — Phase 5")

    def _ensure_schema(self) -> None:
        pass  # Phase 5: CREATE TABLE IF NOT EXISTS trident_chunks ...
