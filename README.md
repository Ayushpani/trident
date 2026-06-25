<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0f0c29,50:302b63,100:24243e&height=200&section=header&text=%E2%9A%A1%20TRIDENT&fontSize=72&fontColor=ffffff&animation=fadeIn&fontAlignY=38&desc=Capture%20%C2%B7%20Synthesize%20%C2%B7%20Remember%20%C2%B7%20Replay&descAlignY=58&descSize=20&descColor=a78bfa" width="100%" />

<div align="center">

<img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=600&size=18&pause=1200&color=A78BFA&center=true&vCenter=true&width=700&lines=Turn+terminal+sessions+into+team+memory.;AI+is+a+plugin%2C+not+a+dependency.;Works+at+Tier+0+with+zero+API+keys.;64+tests+passing.+Zero+network+calls." alt="Trident tagline" />

<br/><br/>

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776ab?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-64%20passing-22c55e?style=for-the-badge&logo=pytest&logoColor=white)](tests/)
[![Tier 0](https://img.shields.io/badge/Tier%200-No%20AI%20needed-7c3aed?style=for-the-badge)]()
[![MCP](https://img.shields.io/badge/MCP-Claude%20Code%20ready-f97316?style=for-the-badge&logo=anthropic&logoColor=white)]()

</div>

---

## The Problem

Every developer eventually asks: *"How exactly did I deploy that six months ago?"*

Your shell history has no structure. Your runbooks are out of date. Your colleagues start from zero every time. Institutional knowledge lives in people's heads — and walks out the door with them.

**Trident fixes this at the capture layer.**

---

## What Trident Does

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│   trident start "deploy auth service"                               │
│                                                                     │
│   [you work normally — Trident records everything]                  │
│                                                                     │
│   trident process                                                   │
│   ✓ 11 events loaded  ✓ 1 secret redacted  ✓ 2 steps synthesized   │
│                                                                     │
│   trident query "how did I deploy auth"                             │
│   → [1] deploy auth service  (2 steps · 1 variable)                │
│   → [2] deploy backend v2    (5 steps · 3 variables)               │
│                                                                     │
│   trident run                                                       │
│   [mechanical replay — your exact commands, in order]               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Four Tiers. One CLI. AI Is Optional.

> The floor works for everyone. AI tiers add quality, not access.

<table>
<thead>
<tr>
<th>Tier</th>
<th>What you need</th>
<th>Synthesis quality</th>
<th>Memory</th>
<th>Best for</th>
</tr>
</thead>
<tbody>
<tr>
<td><b>0 — none</b></td>
<td>Nothing</td>
<td>Deterministic heuristics</td>
<td>Markdown files</td>
<td>Offline · air-gapped · minimal</td>
</tr>
<tr>
<td><b>1 — local</b></td>
<td>Ollama</td>
<td>Single LLM agent</td>
<td>FAISS (local vector)</td>
<td>Privacy-first teams</td>
</tr>
<tr>
<td><b>2 — byok</b></td>
<td>OpenAI / Anthropic key</td>
<td>5-agent swarm</td>
<td>FAISS · Postgres · Mongo</td>
<td>Engineering orgs</td>
</tr>
<tr>
<td><b>3 — smaran</b></td>
<td>Smaran API key</td>
<td>5-agent swarm</td>
<td>Smaran graph memory</td>
<td>Cross-team knowledge base</td>
</tr>
</tbody>
</table>

---

## Architecture

```mermaid
flowchart TD
    subgraph cap ["📡 Capture Layer"]
        A["🖥️ Shell Session\nbash · zsh · pwsh"] -->|"hook writes events"| B["📄 NDJSON Log\n~/.trident/sessions/"]
    end

    subgraph engine ["⚙️ Synthesis Pipeline"]
        B --> C["🔒 Redaction Engine\nPII → typed placeholders"]
        C --> D{"AI Tier?"}
        D -->|none| E["Tier 0\nDeterministic\nheuristics"]
        D -->|local| F["Tier 1\nOllama\nsingle agent"]
        D -->|byok| G["Tier 2\n5-Agent Swarm\nShellStory"]
        D -->|smaran| H["Tier 3\nSmaran Cloud\nswarm + graph"]
    end

    subgraph mem ["🗄️ Memory Layer"]
        I["📝 Markdown\n(Tier 0)"]
        J["🔍 FAISS\nLocal Vector"]
        K["🐘 Postgres\n+ pgvector"]
        L["🍃 MongoDB"]
        M["☁️ Smaran\nCloud Graph"]
    end

    subgraph out ["🚀 Output Layer"]
        N["▶️ Mechanical\nReplay"]
        O["🔎 Vector\nSearch"]
        P["🌐 MCP Bridge\nPort 9000"]
        Q["📤 Export\nObsidian · Notion"]
    end

    E & F & G & H --> I & J & K & L & M
    I & J & K & L & M --> N & O & P & Q

    style cap fill:#1e1b4b,stroke:#4f46e5,color:#e0e7ff
    style engine fill:#1a1a2e,stroke:#7c3aed,color:#e0e7ff
    style mem fill:#0f2027,stroke:#059669,color:#e0e7ff
    style out fill:#1a0a00,stroke:#ea580c,color:#fff7ed
```

---

## Quickstart

### 1. Install

```bash
# Core — Tier 0, zero AI deps
pip install -e shellstory-main/shellstory-main
pip install -e .
```

### 2. Configure

```bash
trident init
```
```
? AI tier? [none/local/byok/smaran]     ›  none
? Memory store? [markdown/faiss/...]    ›  markdown
? Confirm destructive commands? [Y/n]   ›  Y
? Sessions directory?                   ›  (press enter for default)
✓ Config written to ~/.trident/config.yaml
```

### 3. Capture a session

```bash
trident start "deploy auth service"

# Bash / Zsh:
source ~/.trident/sessions/<session-id>.sh

# PowerShell:
. ~/.trident/sessions/<session-id>.ps1
```

```bash
# Work normally — everything is captured
export DATABASE_URL=$DB_CONNECTION_STRING
npm install && npm run build
docker build -t myapp:latest .
docker push registry.io/myapp:latest
kubectl apply -f k8s/deployment.yaml
kubectl rollout status deployment/myapp

exit  # ends the session
```

### 4. Synthesize → Search → Replay

```bash
trident process
# ✓ 11 events loaded  ✓ 1 secret redacted  ✓ 2 steps synthesized
# Runbook written: deploy-auth-service

trident query "deploy auth"
# [1] deploy-auth-service  (2 steps · 1 variable · 2026-06-25)

trident run
# Step 1: Commands in app   ✓
# Step 2: Commands in k8s   ✓
```

**Verify zero AI calls:**
```bash
HTTPX_LOG_LEVEL=debug trident process 2>&1 | grep -i "POST\|openai\|anthropic"
# (no output)
```

---

## Generated Runbook

Every `trident process` writes a professional, shareable Markdown document:

```markdown
# deploy auth service

> **Runbook** · Session `a3f9b2c1` · 2026-06-25 14:32 UTC · Tier 0 — deterministic (no AI)

---

## Table of Contents
1. [Overview](#overview)
2. [Variables](#variables)
3. [Steps](#steps)

---

## Variables

| Variable | How to set | Source |
|----------|-----------|--------|
| `DATABASE_URL` | `export DATABASE_URL=<value>` | environment variable assignment |

---

## Steps

### Step 1: Commands in app

` ` `bash
npm install && \
  npm run build && \
  docker build -t myapp:latest . && \
  docker push registry.io/myapp:latest
` ` `

**What this does:** Node.js build, Docker image build and push

### Step 2: Commands in k8s

` ` `bash
kubectl apply -f k8s/deployment.yaml && \
  kubectl rollout status deployment/myapp
` ` `

**What this does:** Kubernetes deployment with rollout verification

---

*Generated by Trident · Tier 0 · Replay with `trident run`*
```

---

## Memory Stores

| Store | Install | Search | Best for |
|-------|---------|--------|---------|
| `markdown` | _(none)_ | Substring | Solo · offline · zero deps |
| `faiss` | `[faiss]` | L2 ANN · 384-dim | Local vector search |
| `postgres` | `[postgres]` | Cosine · pgvector | Team · Postgres |
| `mongo` | `[mongo]` | Python-side cosine | Team · MongoDB |
| `smaran` | _(API key)_ | Cloud graph | Cross-team org memory |

```bash
pip install 'trident-cli[faiss]'     # local vector search
pip install 'trident-cli[postgres]'  # pgvector team memory
pip install 'trident-cli[mongo]'     # MongoDB team memory
pip install 'trident-cli[byok]'      # Tier 2 — Anthropic + OpenAI SDKs
pip install 'trident-cli[mcp]'       # MCP bridge for Claude Code / Cursor
pip install 'trident-cli[all]'       # everything
```

> **Python 3.14 + Windows:** `sentence-transformers` crashes due to a PyTorch DLL issue. Trident detects this via a subprocess probe and falls back to TF-IDF + LSA automatically. FAISS still works; the index rebuilds correctly.

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `trident init` | Interactive wizard → `~/.trident/config.yaml` |
| `trident start <name>` | Begin capture; prints hook script to source |
| `trident stop` | Mark session stopped |
| `trident process [--session-id <id>]` | Load → redact → synthesize → store |
| `trident query <text>` | Search memory (top 5 by relevance) |
| `trident run [<id>]` | Mechanical replay of most-recent or named runbook |
| `trident list` | List all stored runbooks |
| `trident status` | Active session + event count |
| `trident status --watch` | Live Rich TUI dashboard (2s refresh) |
| `trident mcp-serve` | Start MCP SSE server on port 9000 |
| `trident export --obsidian <vault>` | Push runbook to Obsidian vault |
| `trident export --notion` | Push runbook to Notion database |

---

## Configuration

<details>
<summary><b>Full <code>~/.trident/config.yaml</code> reference</b></summary>

```yaml
version: 1

# AI synthesis tier: none | local | byok | smaran
ai_tier: none

llm:
  provider: ollama          # ollama | openrouter | anthropic | openai
  model: llama3:8b
  api_key: ""               # or: TRIDENT_LLM_KEY env var
  fallback_chain: []        # ordered list of fallback providers

memory:
  primary: markdown         # markdown | faiss | postgres | mongo | smaran

  faiss:
    path: ~/.trident/memory/faiss
    embedding_model: all-MiniLM-L6-v2

  postgres:
    url: postgresql://user:pass@localhost:5432/trident

  mongo:
    url: mongodb://localhost:27017
    database: trident

  smaran:
    api_key: "sm_..."
    endpoint: https://api.smaran.ai

capture:
  sessions_dir: ~/.trident/sessions
  redaction: strict         # strict | standard | off

execution:
  confirm_destructive: true # prompt before rm -rf, kubectl delete, DROP TABLE, etc.
  timeout: 300              # seconds per replay step

connectors:
  obsidian:
    enabled: false
    vault_path: ~/Documents/MyVault
    subfolder: runbooks
  notion:
    enabled: false
    api_key: secret_...
    database_id: abc123
```

</details>

---

## Claude Code Integration

Expose your runbook memory as an MCP server that Claude Code, Cursor, and Codex CLI can query live.

```bash
trident mcp-serve
# ✓ MCP SSE server listening on http://localhost:9000/sse
```

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "trident": {
      "transport": "sse",
      "url": "http://localhost:9000/sse"
    }
  }
}
```

**Available MCP tools:**

| Tool | Description |
|------|-------------|
| `search_memory(query, k)` | Vector search across all runbooks |
| `list_runbooks(limit)` | Metadata for all stored runbooks |
| `trident://runbooks/<id>` | Full runbook content (MCP resource) |

---

## Export Destinations

**Obsidian:**
```bash
trident export --obsidian ~/Documents/MyVault --subfolder runbooks
# Writes: ~/Documents/MyVault/runbooks/deploy-auth-service.md
# Includes YAML frontmatter: tags, session_id, created_at, step count
```

**Notion:**
```bash
# Configure connectors.notion.api_key + database_id in config first
trident export --notion
# Creates a new page in your Notion database with full runbook content
```

---

## Synthesis Pipeline (Tier 0)

The deterministic synthesizer applies five heuristics in order — no LLM, no network:

```
Raw events (11 total)
    │
    ▼  1. Filter   →  keep only command events
    │
    ▼  2. Denoise  →  drop: cd · ls · pwd · clear · echo · cat · which · exit · ...
    │
    ▼  3. Recover  →  error→fix pairs (failed cmd + successful retry in same dir)
    │                 keep the fix, discard the failure
    │
    ▼  4. Navigate →  drop lone 'cd <path>' with no subsequent work in that dir
    │
    ▼  5. Group    →  consecutive commands in same working dir → one RunbookStep
    │
    ▼  Extract     →  env vars (export VAR= / $env:VAR=)
                      destructive ops (rm -rf, kubectl delete, DROP TABLE) → warning flag

Runbook: 2 steps · 1 variable · 0 prerequisites · 0 errors_and_fixes
```

---

## Project Structure

```
trident/
├── cli.py                    # Click entry point — 10 commands
├── config.py                 # ~/.trident/config.yaml load / save / defaults
├── tier.py                   # Tier dispatch (synthesizer · store · LLM client)
│
├── capture/
│   ├── adapter.py            # shellstory re-exports (single import hub)
│   ├── hooks.py              # session start / stop / query
│   ├── ndjson.py             # event file I/O
│   └── redact.py             # PII redaction wrapper
│
├── synthesize/
│   ├── deterministic.py      # Tier 0 — heuristic synthesis (zero LLM calls)
│   ├── local_agent.py        # Tier 1 — single Ollama agent
│   ├── swarm.py              # Tier 2/3 — ShellStory 5-agent pipeline
│   └── chunker.py            # Runbook → embeddable chunks (overview + per step)
│
├── memory/
│   ├── base.py               # MemoryStore ABC (write · query · update · list)
│   ├── _embed.py             # sentence-transformers / TF-IDF backends
│   ├── markdown_store.py     # Tier 0 — filesystem markdown + index.json
│   ├── faiss_store.py        # FAISS L2 + auto embedding backend
│   ├── postgres_store.py     # pgvector cosine search
│   ├── mongo_store.py        # MongoDB + Python-side cosine similarity
│   └── smaran_store.py       # Smaran REST API (POST /v3/documents + /v3/search)
│
├── execute/
│   ├── mechanical.py         # Subprocess replay with destructive-op confirmation
│   ├── ksai_adapter.py       # Kubernetes MCP adapter (subprocess + fastmcp client)
│   └── mcp_bridge.py         # FastMCP SSE server exposing memory on port 9000
│
├── llm/
│   ├── base.py               # Re-exports shellstory.llm.base.LLMClient
│   ├── ollama_client.py      # POST localhost:11434/api/chat
│   ├── openrouter_client.py  # POST openrouter.ai/api/v1/chat/completions
│   ├── anthropic_client.py   # anthropic SDK
│   ├── openai_client.py      # openai SDK
│   └── resilient.py          # Exponential backoff + fallback chain
│
├── connectors/
│   ├── obsidian.py           # Vault filesystem writer with YAML frontmatter
│   └── notion.py             # Notion REST API via httpx
│
└── ui/
    └── dashboard.py          # Rich Live TUI (trident status --watch)
```

---

## Tests

```bash
pytest tests/ -q
# ................................................................ 64 passed in 6.58s
```

| Module | Tests | Coverage |
|--------|-------|---------|
| `test_deterministic_synth.py` | 17 | Noise filter · error recovery · dir grouping · env var extraction |
| `test_memory_stores.py` | 17 | Markdown + FAISS write / query / list (TF-IDF backend forced) |
| `test_tier_resolution.py` | 12 | Tier dispatch · synthesizer dispatch · store dispatch |
| `test_capture.py` | 10 | NDJSON round-trip · DB CRUD · prefix lookup |
| `test_mechanical_replay.py` | 8 | Success · stop-on-failure · destructive confirmation · timeout |

All 64 tests run with **zero network calls** and **zero API keys required**.

---

## Built On

| Project | Role |
|---------|------|
| [ShellStory](https://github.com/your/shellstory) | Terminal capture · PII redaction · 5-agent swarm synthesis · LLM client interface |
| [ksai](https://github.com/your/ksai) | Kubernetes MCP server (runs as managed subprocess) |
| [Smaran](https://smaran.ai) | Managed team memory via REST API |

---

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:24243e,50:302b63,100:0f0c29&height=120&section=footer&text=MIT%20License%20%C2%B7%20Python%203.11%2B&fontSize=16&fontColor=a78bfa&fontAlignY=65" width="100%" />
