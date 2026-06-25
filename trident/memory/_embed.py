"""
trident.memory._embed — shared embedding backends for all memory stores.

Primary: sentence-transformers all-MiniLM-L6-v2 (384-dim, pretrained, stable)
Fallback: sklearn TF-IDF + TruncatedSVD (LSA, 384-dim padded, no torch needed)

The fallback backend has a fit() / embed() split:
  - fit(corpus)   — (re-)trains the model on the full text corpus
  - embed(texts)  — transforms texts using the fitted model

Sentence-transformers is a fixed pretrained model — no fitting needed, and
embeddings are stable across restarts. TF-IDF is not stable: the vocabulary
changes when new documents are added. Callers that persist embeddings (Postgres,
MongoDB) MUST call fit(all_texts) on startup and re-embed all existing rows
whenever new documents are added.
"""

from __future__ import annotations

_ST_SAFE: bool | None = None  # cached after first subprocess probe
_DIM = 384


def sentence_transformers_safe() -> bool:
    """
    Return True only if sentence-transformers can be imported without crashing.

    PyTorch DLL crashes on Python 3.14 / Windows are C-level access violations
    that bypass try/except. We probe in a subprocess; result is cached.
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


def get_embedder():
    """
    Return an (embedder, is_stable) tuple.

    is_stable=True means the model is a fixed pretrained model whose embeddings
    are consistent across restarts (sentence-transformers). is_stable=False means
    the caller must manage corpus consistency (TF-IDF fallback).
    """
    if sentence_transformers_safe():
        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer("all-MiniLM-L6-v2")
            return STBackend(model), True
        except Exception:
            pass
    return TFIDFBackend(), False


class STBackend:
    """sentence-transformers backend — stable, pretrained."""

    def __init__(self, model) -> None:
        self._model = model

    def fit(self, texts: list[str]) -> None:
        pass  # no-op: pretrained model needs no fitting

    def embed(self, texts: list[str]):
        return self._model.encode(texts, normalize_embeddings=True).astype("float32")


class TFIDFBackend:
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
        if len(texts) < 2:
            return
        X = self._vec.fit_transform(texts)
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
        if result.shape[1] < _DIM:
            pad = np.zeros((result.shape[0], _DIM - result.shape[1]), dtype="float32")
            result = np.hstack([result, pad])
        return normalize(result).astype("float32")
