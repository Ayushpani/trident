"""
trident.memory.mongo_store — MongoDB Atlas Vector Search memory store.

Requires: pip install 'trident-cli[mongo]'
Config key: memory.mongo.url (MongoDB connection string)
"""

from __future__ import annotations

from typing import Any

from trident.memory.base import MemoryStore


class MongoStore(MemoryStore):
    """Phase 5 stub — MongoDB vector store."""

    def __init__(self, config: dict[str, Any]) -> None:
        try:
            import pymongo  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "Mongo store requires: pip install 'trident-cli[mongo]'"
            ) from exc

        self._url = config["memory"]["mongo"]["url"]
        if not self._url:
            raise ValueError("memory.mongo.url must be set in config")

    def write(self, chunks: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
        raise NotImplementedError("MongoStore.write — Phase 5")

    def query(self, text: str, k: int = 5) -> list[dict[str, Any]]:
        raise NotImplementedError("MongoStore.query — Phase 5")

    def update(self, store_id: str, content: dict[str, Any]) -> None:
        raise NotImplementedError("MongoStore.update — Phase 5")

    def list(self) -> list[dict[str, Any]]:
        raise NotImplementedError("MongoStore.list — Phase 5")
