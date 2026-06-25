"""
trident.memory.base — abstract MemoryStore interface.

All stores (FAISS, Postgres, Mongo, Markdown, Smaran) implement this
interface.  A user switching from FAISS to Postgres changes one config
line; no code changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MemoryStore(ABC):
    """Abstract interface for all Trident memory backends."""

    @abstractmethod
    def write(self, chunks: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
        """
        Persist a list of content chunks with associated metadata.

        Args:
            chunks:   List of chunk dicts, each with at least a 'text' key.
            metadata: Session/runbook metadata (title, session_id, tags, etc.).

        Returns:
            A store-specific ID for the written record (e.g. runbook slug).
        """

    @abstractmethod
    def query(self, text: str, k: int = 5) -> list[dict[str, Any]]:
        """
        Retrieve the k most relevant chunks for the query text.

        Args:
            text: Natural-language query.
            k:    Maximum number of results to return.

        Returns:
            List of chunk dicts, each including 'text', 'score', and 'metadata'.
        """

    @abstractmethod
    def update(self, store_id: str, content: dict[str, Any]) -> None:
        """Replace the content of an existing record."""

    @abstractmethod
    def list(self) -> list[dict[str, Any]]:
        """
        List all stored records.

        Returns:
            List of metadata dicts, sorted newest-first.
        """
