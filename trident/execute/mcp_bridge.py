"""
trident.execute.mcp_bridge — expose Trident memory as an MCP server.

External AI clients (Claude Code, Cursor, Codex CLI) can connect to this
server and search/list Trident runbooks via the MCP protocol.

Requires: pip install 'trident-cli[mcp]'   →  fastmcp>=2.12

Config:
  mcp_bridge:
    port: 9000          # default
    host: "localhost"   # default

Usage:
  trident mcp-serve              # starts the bridge
  Or: from trident.execute.mcp_bridge import serve; serve(config)
"""

from __future__ import annotations

from typing import Any


class MCPBridge:
    """MCP server that exposes Trident's memory store to external AI clients."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        bridge_cfg = config.get("mcp_bridge", {})
        self._port = int(bridge_cfg.get("port", 9000))
        self._host = bridge_cfg.get("host", "localhost")

    def serve(self) -> None:
        """Start the MCP bridge server (blocking)."""
        serve(self._config)


def serve(config: dict[str, Any]) -> None:
    """Start the Trident memory MCP bridge (blocking)."""
    try:
        from fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError(
            "MCP bridge requires: pip install 'trident-cli[mcp]'"
        ) from exc

    from trident.tier import get_memory_store

    store = get_memory_store(config)
    bridge_cfg = config.get("mcp_bridge", {})
    port = int(bridge_cfg.get("port", 9000))
    host = bridge_cfg.get("host", "localhost")

    mcp = FastMCP("trident-memory")

    @mcp.tool()
    def search_memory(query: str, k: int = 5) -> list[dict]:
        """
        Search Trident runbook memory for the given query.

        Args:
            query: Natural language search query
            k: Number of results to return (default 5)

        Returns:
            List of matching chunks with title, text, score, and session_id
        """
        results = store.query(query, k=k)
        return [
            {
                "title": r.get("title", ""),
                "text": r.get("text", r.get("snippet", "")),
                "score": r.get("score", 0.0),
                "session_id": r.get("session_id", ""),
                "runbook_id": r.get("runbook_id", ""),
                "step_number": r.get("step_number"),
                "type": r.get("type", "chunk"),
            }
            for r in results
        ]

    @mcp.tool()
    def list_runbooks(limit: int = 20) -> list[dict]:
        """
        List all runbooks stored in Trident memory.

        Args:
            limit: Maximum number of runbooks to return (default 20)

        Returns:
            List of runbook metadata (title, session_id, created_at, store_id)
        """
        entries = store.list()
        return [
            {
                "store_id": e.get("store_id", ""),
                "title": e.get("title", ""),
                "session_id": e.get("session_id", ""),
                "created_at": e.get("created_at", ""),
            }
            for e in entries[:limit]
        ]

    @mcp.resource("trident://runbooks/{store_id}")
    def get_runbook(store_id: str) -> str:
        """
        Retrieve the full text of a runbook by its store ID.

        Args:
            store_id: The unique ID returned by list_runbooks()

        Returns:
            Combined text of all chunks in the runbook
        """
        results = store.query(f"store_id:{store_id}", k=50)
        matching = [r for r in results if r.get("store_id") == store_id]
        if not matching:
            matching = results

        return "\n\n---\n\n".join(
            r.get("text", r.get("snippet", "")) for r in matching
        )

    mcp.run(transport="sse", host=host, port=port)
