"""
trident.execute.ksai_adapter — Phase 7 stub.

Wraps ksai's k8s_mcp_server.py as a subprocess and exposes
K8s operations through Trident's memory layer.
"""

from __future__ import annotations

from typing import Any


class KsaiAdapter:
    """Phase 7 stub — ksai K8s operations adapter."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._proc = None

    def start(self) -> None:
        raise NotImplementedError("KsaiAdapter.start — Phase 7")

    def stop(self) -> None:
        raise NotImplementedError("KsaiAdapter.stop — Phase 7")

    def query(self, natural_language: str) -> str:
        raise NotImplementedError("KsaiAdapter.query — Phase 7")
