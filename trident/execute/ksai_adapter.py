"""
trident.execute.ksai_adapter — wraps ksai's k8s_mcp_server.py.

k8s_mcp_server.py uses module-level FastMCP state and binds to
http://localhost:8000/sse. It must run as a subprocess; KsaiAdapter
manages the lifecycle and provides a Python interface to its tools.

Requirements:
  - kubectl configured (ksai loads kube config at startup)
  - pip install 'trident-cli[mcp]'  →  fastmcp>=2.12

Config (optional):
  ksai:
    server_path: "ks-ai-main/ks-ai-main/k8s_mcp_server.py"
    port: 8000
    startup_timeout: 10
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_DEFAULT_PORT = 8000
_SSE_URL = f"http://localhost:{_DEFAULT_PORT}/sse"
_KSAI_SERVER = (
    Path(__file__).parent.parent.parent
    / "ks-ai-main"
    / "ks-ai-main"
    / "k8s_mcp_server.py"
)


class KsaiAdapter:
    """
    Manages the ksai k8s_mcp_server.py subprocess and exposes K8s tools
    through a simple Python API.

    Usage:
        adapter = KsaiAdapter(config)
        adapter.start()
        tools = adapter.list_tools()
        result = adapter.call_tool("list_pods", {"namespace": "default"})
        answer = adapter.query("show me all failing pods")
        adapter.stop()
    """

    def __init__(self, config: dict[str, Any]) -> None:
        ksai_cfg = config.get("ksai", {})
        server_path = ksai_cfg.get("server_path", str(_KSAI_SERVER))
        self._server_path = Path(server_path)
        self._port = int(ksai_cfg.get("port", _DEFAULT_PORT))
        self._startup_timeout = int(ksai_cfg.get("startup_timeout", 10))
        self._sse_url = f"http://localhost:{self._port}/sse"
        self._proc: subprocess.Popen | None = None
        self._config = config

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start k8s_mcp_server.py as a background subprocess."""
        if not self._server_path.exists():
            raise FileNotFoundError(
                f"k8s_mcp_server.py not found at {self._server_path}. "
                "Make sure ks-ai-main is in the trident repo root."
            )

        self._proc = subprocess.Popen(
            [sys.executable, str(self._server_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Poll until the server responds or times out.
        self._wait_for_server()

    def stop(self) -> None:
        """Terminate the k8s_mcp_server.py subprocess."""
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    # ── Public interface ──────────────────────────────────────────────────────

    def list_tools(self) -> list[dict[str, Any]]:
        """Return available K8s tools from the MCP server."""
        return asyncio.run(self._async_list_tools())

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> str:
        """Call a K8s tool by name and return its result as a string."""
        return asyncio.run(self._async_call_tool(tool_name, arguments or {}))

    def query(self, natural_language: str) -> str:
        """
        Handle a natural language K8s query.

        Uses the configured LLM client to pick and call the right tool.
        Falls back to keyword matching when ai_tier is 'none'.
        """
        from trident.tier import get_llm_client

        llm = get_llm_client(self._config)
        if llm is None:
            return self._keyword_query(natural_language)

        return self._llm_query(natural_language, llm)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _wait_for_server(self) -> None:
        import httpx

        deadline = time.monotonic() + self._startup_timeout
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    "k8s_mcp_server.py exited immediately. "
                    "Check that kubectl is configured correctly."
                )
            try:
                r = httpx.get(f"http://localhost:{self._port}/", timeout=1.0)
                if r.status_code < 500:
                    return
            except Exception:
                pass
            time.sleep(0.5)

        self.stop()
        raise TimeoutError(
            f"k8s_mcp_server.py did not respond within {self._startup_timeout}s."
        )

    async def _async_list_tools(self) -> list[dict[str, Any]]:
        try:
            from fastmcp import Client
        except ImportError as exc:
            raise ImportError(
                "KsaiAdapter requires: pip install 'trident-cli[mcp]'"
            ) from exc

        async with Client(self._sse_url) as client:
            tools = await client.list_tools()

        result = []
        for t in tools:
            result.append(
                {
                    "name": t.name,
                    "description": t.description or "",
                    "schema": t.inputSchema if hasattr(t, "inputSchema") else {},
                }
            )
        return result

    async def _async_call_tool(self, name: str, args: dict) -> str:
        try:
            from fastmcp import Client
        except ImportError as exc:
            raise ImportError(
                "KsaiAdapter requires: pip install 'trident-cli[mcp]'"
            ) from exc

        async with Client(self._sse_url) as client:
            result = await client.call_tool(name, args)

        if hasattr(result, "content") and result.content:
            if isinstance(result.content, list):
                return "\n".join(
                    item.text if hasattr(item, "text") else str(item)
                    for item in result.content
                )
            return str(result.content)
        return str(result)

    def _keyword_query(self, query: str) -> str:
        """Deterministic fallback: match keywords to common K8s tools."""
        q = query.lower()
        if any(w in q for w in ("pod", "pods", "container")):
            ns = _extract_ns(q)
            return self.call_tool("list_pods", {"namespace": ns})
        if any(w in q for w in ("deploy", "deployment", "deployments")):
            ns = _extract_ns(q)
            return self.call_tool("list_deployments", {"namespace": ns})
        if any(w in q for w in ("service", "svc", "services")):
            ns = _extract_ns(q)
            return self.call_tool("list_services", {"namespace": ns})
        if any(w in q for w in ("node", "nodes")):
            return self.call_tool("list_nodes", {})
        if any(w in q for w in ("namespace", "namespaces", "ns")):
            return self.call_tool("list_namespaces", {})
        if any(w in q for w in ("log", "logs")):
            return "Please specify: trident ksai logs <pod-name>"
        # Default: list pods in default namespace
        return self.call_tool("list_pods", {"namespace": "default"})

    def _llm_query(self, query: str, llm) -> str:
        """Use Trident's LLM client to select and call the appropriate K8s tool."""
        try:
            tools = self.list_tools()
        except Exception as exc:
            return f"Could not list tools: {exc}"

        tools_desc = "\n".join(
            f"- {t['name']}: {t['description']}" for t in tools[:30]
        )

        from trident.llm.base import LLMMessage

        messages = [
            LLMMessage(
                role="user",
                content=(
                    f"User query: {query}\n\n"
                    f"Available K8s tools:\n{tools_desc}\n\n"
                    "Reply with JSON only: "
                    '{"tool": "<tool_name>", "args": {<tool_args>}}'
                ),
            )
        ]

        try:
            resp = llm.complete(
                messages,
                system="You are a Kubernetes operations assistant. Pick the single best tool for the query.",
                max_tokens=200,
                json_mode=True,
            )
            import json

            parsed = json.loads(resp.content)
            tool_name = parsed.get("tool", "")
            args = parsed.get("args", {})
            if tool_name:
                return self.call_tool(tool_name, args)
        except Exception:
            pass

        return self._keyword_query(query)


def _extract_ns(query: str) -> str:
    """Extract namespace from a query string (e.g. 'in kube-system')."""
    words = query.split()
    for i, w in enumerate(words):
        if w in ("in", "namespace", "ns") and i + 1 < len(words):
            candidate = words[i + 1].strip(".,;:")
            if candidate and not candidate.startswith("-"):
                return candidate
    return "default"
