# Trident Architecture

## Overview

Trident is a thin orchestration layer over three existing tools:

- **ShellStory** — terminal session capture, PII redaction, 5-agent runbook synthesis
- **ksai** — Kubernetes operations via MCP (k8s_mcp_server.py)
- **Smaran** — managed team memory via MCP HTTP API

Trident installs as a single `pip install -e .` package and exposes a `trident` CLI. It does not fork or modify any of the three tools.

---

## Directory layout

```
trident/
├── cli.py                  # Click entry point — 10 commands
├── config.py               # ~/.trident/config.yaml load/save/defaults
├── tier.py                 # Dispatch: which synthesizer / store / LLM client?
│
├── capture/
│   ├── adapter.py          # Re-exports from shellstory (single import hub)
│   ├── hooks.py            # start_session, stop_session, get_active_session
│   ├── ndjson.py           # load_events, event_count wrappers
│   └── redact.py           # Thin wrapper over shellstory.redact_events
│
├── synthesize/
│   ├── deterministic.py    # Tier 0: noise filter + error-recovery + dir grouping
│   ├── local_agent.py      # Tier 1: single Ollama prompt → Runbook
│   ├── swarm.py            # Tier 2/3: delegates to ShellStory SwarmOrchestrator
│   └── chunker.py          # Runbook → embeddable chunks (overview + per step)
│
├── memory/
│   ├── base.py             # MemoryStore ABC: write/query/update/list
│   ├── _embed.py           # Shared embedding: sentence-transformers or TF-IDF
│   ├── markdown_store.py   # Tier 0: filesystem markdown + index.json
│   ├── faiss_store.py      # Tier 1+: FAISS L2 + embedding backends
│   ├── postgres_store.py   # pgvector cosine search
│   ├── mongo_store.py      # pymongo + Python-side cosine similarity
│   └── smaran_store.py     # Smaran REST API (POST /v3/documents + /v3/search)
│
├── execute/
│   ├── mechanical.py       # Tier 0: subprocess replay, stop on failure
│   ├── ksai_adapter.py     # Wraps k8s_mcp_server.py subprocess + fastmcp.Client
│   └── mcp_bridge.py       # Exposes Trident memory as FastMCP SSE server
│
├── connectors/
│   ├── markdown.py         # Thin wrapper over shellstory.connectors.MarkdownConnector
│   ├── obsidian.py         # Write to Obsidian vault (pure filesystem)
│   └── notion.py           # Notion REST API via httpx
│
├── llm/
│   ├── base.py             # Re-exports LLMClient from shellstory.llm.base
│   ├── ollama_client.py    # POST http://localhost:11434/api/chat
│   ├── openrouter_client.py # POST https://openrouter.ai/api/v1/chat/completions
│   ├── anthropic_client.py # anthropic SDK
│   ├── openai_client.py    # openai SDK
│   └── resilient.py        # Exponential backoff + fallback chain
│
└── ui/
    └── dashboard.py        # Rich Live dashboard (trident status --watch)
```

---

## Data flow (Tier 0)

```
trident start "deploy auth"
    │
    ▼
hooks.start_session()
    ├── Creates Session in ~/.trident/trident.db
    ├── Creates ~/.trident/sessions/<id>.ndjson
    └── shellstory.capture.create_hook_file() → writes shell hook

[user runs commands in hooked shell]
    │
    ▼ (NDJSON events appended by hook)

trident process
    │
    ├── load_events(capture_file) → list[RawEvent]
    ├── redact(events, mode="strict") → RedactionResult
    │       └── shellstory.redact.redact_events()
    ├── DeterministicSynthesizer.synthesize()
    │       ├── drop_noise (cd, ls, pwd, clear, ...)
    │       ├── collapse_error_recovery (fail→fix pairs same dir)
    │       ├── drop_orphan_cds (lone cd with no subsequent work)
    │       ├── group_by_working_dir → RunbookStep[]
    │       └── extract_env_vars, ports, files
    ├── chunk_runbook(runbook) → list[dict]  (overview + per step)
    ├── MarkdownStore.write(chunks, metadata) → store_id
    └── Database.save_runbook(runbook)

trident query "deploy auth"
    └── MarkdownStore.query("deploy auth", k=5) → ranked chunks

trident run
    └── MechanicalReplayer.run(runbook)
            ├── subprocess.run(command, shell=True, timeout=300)
            ├── confirm_destructive prompts for rm/drop/kubectl delete
            └── stops on first non-zero exit code
```

---

## Embedding and vector search

`trident/memory/_embed.py` provides:

```
get_embedder() → (embedder, is_stable)
```

**is_stable=True** (sentence-transformers `all-MiniLM-L6-v2`, 384-dim):
- Fixed pretrained model, consistent vectors across restarts
- Blocked on Python 3.14 + Windows due to PyTorch DLL crash
- Detection: subprocess probe before in-process import

**is_stable=False** (TF-IDF + TruncatedSVD / LSA, 384-dim padded):
- No torch dependency, works everywhere
- Vocabulary evolves as corpus grows → vectors are inconsistent after restart
- FAISSStore: rebuilds entire FAISS index on every write (correct, O(n))
- PostgresStore: re-fits and re-embeds all rows on every write (correct, O(n))
- MongoStore: re-fits on write; query uses fitted model (potentially stale after restart)

---

## ShellStory integration contract

Trident uses ShellStory as a pip-installable library. The integration points:

| ShellStory symbol | How Trident uses it |
|-------------------|---------------------|
| `shellstory.capture.create_hook_file` | Session start |
| `shellstory.capture.write_session_start_event` | Session start |
| `shellstory.capture.generate_{bash,zsh,powershell}_hook` | Hook generation |
| `shellstory.models.*` | All Pydantic models (re-exported via adapter.py) |
| `shellstory.redact.redact_events` | PII redaction (16 regex patterns) |
| `shellstory.db.Database` | Session/Runbook CRUD (Trident passes its own db_path) |
| `shellstory.agents.swarm.SwarmOrchestrator` | Tier 2/3 synthesis |
| `shellstory.llm.base.LLMClient` | Abstract LLM interface (Trident implements it) |
| `shellstory.connectors.MarkdownConnector` | Markdown export |
| `shellstory.utils.ndjson.{load_events,append_event,count_events}` | NDJSON I/O |

Trident's DB lives at `~/.trident/trident.db`; ShellStory's at `~/.shellstory/shellstory.db`. Same schema (`Database(db_path=...)`), fully isolated.

---

## ksai integration

`k8s_mcp_server.py` uses module-level `FastMCP` state and `config.load_kube_config()` at import time. It cannot be imported in-process without side effects. Trident runs it as a subprocess:

```
KsaiAdapter.start()
    ├── subprocess.Popen([sys.executable, "k8s_mcp_server.py"])
    ├── poll http://localhost:8000/ until responsive (10s timeout)
    └── fastmcp.Client("http://localhost:8000/sse")

KsaiAdapter.query("show failing pods")
    ├── if ai_tier != none: LLMClient picks tool from list_tools()
    └── else: keyword matching → call_tool("list_pods", ...)
```

---

## Smaran integration

Smaran is a TypeScript/Cloudflare Workers service. Trident accesses it purely via its REST API:

```
POST https://api.smaran.ai/v3/documents    ← write chunk
POST https://api.smaran.ai/v3/search       ← query
POST https://api.smaran.ai/v3/documents/documents  ← list
Authorization: Bearer {api_key}
```

---

## MCP bridge (Phase 8)

`trident mcp-serve` starts a FastMCP SSE server on port 9000 that exposes:

- **Tool `search_memory(query, k)`** — calls `MemoryStore.query()`
- **Tool `list_runbooks(limit)`** — calls `MemoryStore.list()`
- **Resource `trident://runbooks/{store_id}`** — returns full runbook text

Any MCP-compatible client (Claude Code, Cursor, Codex CLI) can connect.

---

## LLM client hierarchy

```
shellstory.llm.base.LLMClient  (ABC)
    ├── OllamaClient            → POST localhost:11434/api/chat
    ├── OpenRouterClient        → POST openrouter.ai/api/v1/chat/completions
    ├── AnthropicClient         → anthropic SDK
    ├── OpenAIClient            → openai SDK
    └── ResilientLLMClient      → wraps any client with backoff + fallback chain
```

`complete(messages, system, max_tokens, temperature, json_mode) → LLMResponse`

The signature is identical to ShellStory's LLMClient so ShellStory's swarm agents (Tier 2+) work unmodified.

---

## Test coverage

```
tests/test_deterministic_synth.py   17 tests  Noise filter, error-recovery, dir grouping
tests/test_capture.py               10 tests  NDJSON round-trip, DB CRUD, prefix lookup
tests/test_memory_stores.py         17 tests  MarkdownStore + FAISSStore (TF-IDF backend)
tests/test_mechanical_replay.py      8 tests  Success, stop-on-failure, destructive, timeout
tests/test_tier_resolution.py       12 tests  Tier dispatch, synthesizer dispatch, store dispatch
─────────────────────────────────────────────
Total                               64 tests  (all passing, zero API keys needed)
```
