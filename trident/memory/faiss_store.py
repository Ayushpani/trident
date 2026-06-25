"""
trident.memory.faiss_store — local vector store using FAISS.

Primary embedder: sentence-transformers all-MiniLM-L6-v2 (384 dim)
Fallback embedder: sklearn TF-IDF + TruncatedSVD (LSA).

The TF-IDF backend re-fits on every write and rebuilds the FAISS index from
scratch so that all stored vectors remain consistent with the current model.
This is intentionally simple — for a local developer tool the corpus is
typically <10k chunks and the rebuild is sub-second.

Requires: pip install 'trident-cli[faiss]'
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trident.memory.base import MemoryStore

_DIM = 384


_ST_SAFE: bool | None = None  # cached after first probe


def _sentence_transformers_safe() -> bool:
    """
    Return True only if sentence-transformers can be imported without crashing.

    PyTorch on Python 3.14 / Windows may cause a hard C-level crash
    (access violation) that try/except cannot intercept.  We probe via a
    short-lived subprocess whose non-zero exit code signals a crash.
    Result is cached so the probe runs at most once per process.
    """
    global _ST_SAFE
    if _ST_SAFE is not None:
        return _ST_SAFE

    import importlib.util
    import subprocess
    import sys

    if importlib.util.find_spec("sentence_transformers") is None:
        _ST_SAFE = False
        return False

    try:
        result = subprocess.run(
            [sys.executable, "-c", "from sentence_transformers import SentenceTransformer"],
            capture_output=True,
            timeout=15,
        )
        _ST_SAFE = result.returncode == 0
    except Exception:
        _ST_SAFE = False

    return _ST_SAFE


class FAISSStore(MemoryStore):
    """
    Local vector memory store backed by FAISS ANN search.

    Index:    ~/.trident/memory/faiss/index.bin
    Metadata: ~/.trident/memory/faiss/meta.json
    """

    def __init__(self, config: dict[str, Any]) -> None:
        try:
            import faiss  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "FAISS store requires: pip install 'trident-cli[faiss]'"
            ) from exc

        faiss_cfg = config["memory"].get("faiss", {})
        self._store_path = Path(
            faiss_cfg.get("path", "~/.trident/memory/faiss")
        ).expanduser()
        self._store_path.mkdir(parents=True, exist_ok=True)
        self._index_path = self._store_path / "index.bin"
        self._meta_path = self._store_path / "meta.json"

        self._meta: list[dict] = self._load_meta()
        self._backend = self._init_backend()
        self._index = self._load_or_create_index()

    # ── MemoryStore interface ─────────────────────────────────────────────────

    def write(self, chunks: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
        store_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        offset = len(self._meta)

        for i, chunk in enumerate(chunks):
            self._meta.append(
                {
                    "store_id": store_id,
                    "faiss_idx": offset + i,
                    "text": chunk["text"],
                    "type": chunk.get("type", "chunk"),
                    "step_number": chunk.get("step_number"),
                    "title": metadata.get("title", ""),
                    "session_id": metadata.get("session_id", ""),
                    "runbook_id": metadata.get("runbook_id", ""),
                    "created_at": now,
                }
            )

        if isinstance(self._backend, _TFIDFBackend):
            # Re-fit on all corpus (including newly appended entries) then rebuild.
            all_texts = [m["text"] for m in self._meta if m.get("text")]
            self._backend.fit(all_texts)
            self._rebuild_index()
        else:
            texts = [c["text"] for c in chunks]
            embeddings = self._backend.embed(texts)
            self._index.add(embeddings)

        self._save()
        return store_id

    def query(self, text: str, k: int = 5) -> list[dict[str, Any]]:
        if self._index.ntotal == 0:
            return []

        embedding = self._backend.embed([text])
        actual_k = min(k, self._index.ntotal)
        distances, indices = self._index.search(embedding, actual_k)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self._meta):
                continue
            entry = dict(self._meta[idx])
            entry["score"] = float(1.0 / (1.0 + dist))
            results.append(entry)

        return sorted(results, key=lambda x: -x["score"])

    def update(self, store_id: str, content: dict[str, Any]) -> None:
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

    def _init_backend(self):
        """
        Try SentenceTransformer first; fall back to TF-IDF.

        PyTorch DLL crashes on some platforms (e.g. Python 3.14 + Windows) are
        C-level access violations that bypass Python's try/except.  We use a
        probe subprocess to test import safety before touching the module
        in-process.
        """
        if _sentence_transformers_safe():
            try:
                from sentence_transformers import SentenceTransformer

                model = SentenceTransformer("all-MiniLM-L6-v2")
                return _STBackend(model)
            except Exception:
                pass

        backend = _TFIDFBackend()
        # Pre-fit on any existing corpus so queries work immediately.
        existing = [m["text"] for m in self._meta if m.get("text")]
        if len(existing) >= 2:
            backend.fit(existing)
        return backend

    def _load_or_create_index(self):
        import faiss

        if self._index_path.exists():
            return faiss.read_index(str(self._index_path))
        return faiss.IndexFlatL2(_DIM)

    def _rebuild_index(self) -> None:
        """Discard the current FAISS index and re-embed the full corpus."""
        import faiss

        self._index = faiss.IndexFlatL2(_DIM)
        texts = [m["text"] for m in self._meta if m.get("text")]
        if texts:
            embeddings = self._backend.embed(texts)
            self._index.add(embeddings)

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


# ── Embedding backends ─────────────────────────────────────────────────────────


class _STBackend:
    """sentence-transformers backend (preferred)."""

    def __init__(self, model) -> None:
        self._model = model

    def embed(self, texts: list[str]):
        return self._model.encode(texts, normalize_embeddings=True).astype("float32")


class _TFIDFBackend:
    """TF-IDF + TruncatedSVD (LSA) fallback — no torch dependency."""

    def __init__(self) -> None:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vec = TfidfVectorizer(
            max_features=10_000, ngram_range=(1, 2), sublinear_tf=True
        )
        self._svd = TruncatedSVD(n_components=_DIM, random_state=42)
        self._fitted = False

    def fit(self, texts: list[str]) -> None:
        """(Re-)fit the model on the full corpus."""
        if len(texts) < 2:
            return
        X = self._vec.fit_transform(texts)
        # SVD requires n_components < min(n_samples, n_features)
        n_comp = min(_DIM, X.shape[0] - 1, X.shape[1] - 1)
        if n_comp < 2:
            return
        self._svd.n_components = n_comp
        self._svd.fit(X)
        self._fitted = True

    def embed(self, texts: list[str]):
        import numpy as np
        from sklearn.preprocessing import normalize

        if not self._fitted:
            return np.zeros((len(texts), _DIM), dtype="float32")

        X = self._vec.transform(texts)
        result = self._svd.transform(X).astype("float32")
        # Pad to _DIM if SVD used fewer components due to small corpus.
        if result.shape[1] < _DIM:
            pad = np.zeros((result.shape[0], _DIM - result.shape[1]), dtype="float32")
            result = np.hstack([result, pad])
        return normalize(result).astype("float32")
