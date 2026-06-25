"""
trident.execute.mcp_bridge — Phase 8 stub.

Exposes Trident's memory as an MCP server so external agents
(Claude Code, Codex CLI, Cursor) can query it directly.
"""

from __future__ import annotations

from typing import Any


class MCPBridge:
    """Phase 8 stub — MCP server exposing Trident memory."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._port = 9000

    def serve(self) -> None:
        raise NotImplementedError("MCPBridge.serve — Phase 8")
