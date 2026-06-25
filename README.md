# Trident

> Capture terminal sessions → synthesize runbooks → store as team memory → replay anywhere.

Trident unifies three tools (ShellStory, ksai, Smaran) into a single `trident` CLI. The core thesis: **AI is a swappable plugin**. Everything works at Tier 0 with zero API keys, no GPU, and no cloud account.

---

## Four AI tiers

| Tier | What you need | What you get |
|------|--------------|--------------|
| **0 — none** | Nothing | Deterministic runbook synthesis (heuristics) |
| **1 — local** | Ollama running locally | Single-agent synthesis via local LLM |
| **2 — byok** | OpenAI / Anthropic / OpenRouter key | 5-agent swarm synthesis (ShellStory pipeline) |
| **3 — smaran** | Smaran API key | Swarm synthesis + graph-clustered team memory |

The floor works for any engineer. AI tiers add quality, not access.

---

## Quickstart (Tier 0)

```bash
# Install
pip install -e shellstory-main/shellstory-main
pip install -e .

# Configure (answer: none, markdown, Y, default)
trident init

# Start a session
trident start "deploy auth service"
source ~/.trident/sessions/<id>.sh   # bash/zsh
# or: . ~/.trident/sessions/<id>.sh

# Run commands in the captured shell, then stop
exit

# Synthesize a runbook (no LLM needed)
trident process

# Search memory
trident query "deploy auth"

# Replay the runbook
trident run
```

No LLM calls are made at Tier 0. Verify with `HTTPX_LOG_LEVEL=debug trident process`.

---

## Installation

**Core (Tier 0):**
```bash
pip install -e shellstory-main/shellstory-main
pip install -e .
```

**Tier 1 (local Ollama):** start Ollama, `trident init` → choose `local`

**Tier 2 (BYOK):**
```bash
pip install 'trident-cli[byok]'      # anthropic + openai SDKs
```

**FAISS memory (local vector search):**
```bash
pip install 'trident-cli[faiss]'     # faiss-cpu + sentence-transformers
# Note: on Python 3.14 + Windows, falls back to TF-IDF automatically
```

**Postgres memory:**
```bash
pip install 'trident-cli[postgres]'  # psycopg2-binary + pgvector
# Requires: CREATE EXTENSION vector; in your Postgres DB
```

**MongoDB memory:**
```bash
pip install 'trident-cli[mongo]'     # pymongo
```

**MCP bridge (expose memory to Claude Code etc.):**
```bash
pip install 'trident-cli[mcp]'       # fastmcp>=2.12
```

---

## CLI reference

```
trident init            Interactive wizard → ~/.trident/config.yaml
trident start <name>    Begin capture session; prints hook to source
trident stop            Mark session stopped
trident process         Load events → redact → synthesize → store
trident query <text>    Search memory
trident run [id]        Mechanical replay of a runbook
trident list            List sessions
trident status          Active session + event count
trident status --watch  Live Rich TUI dashboard
trident mcp-serve       Expose memory as MCP SSE server (port 9000)
trident export          Push runbook to Obsidian or Notion
  --obsidian <vault>
  --notion
  --runbook-id <id>
```

---

## Config (`~/.trident/config.yaml`)

```yaml
version: 1
ai_tier: none              # none | local | byok | smaran

llm:
  provider: ollama         # ollama | openrouter | anthropic | openai
  model: llama3:8b
  api_key: ""              # or set TRIDENT_LLM_KEY env var

memory:
  primary: markdown        # markdown | faiss | postgres | mongo | smaran
  faiss:
    path: ~/.trident/memory/faiss
  postgres:
    url: postgresql://user:pass@localhost:5432/trident
  mongo:
    url: mongodb://localhost:27017
    database: trident
  smaran:
    api_key: "sm_..."
    endpoint: https://api.smaran.ai
    container_tag: trident

capture:
  sessions_dir: ~/.trident/sessions
  redaction: strict        # strict | standard | off

execution:
  confirm_destructive: true
  timeout: 300

mcp_bridge:
  port: 9000
  host: localhost

connectors:
  obsidian:
    vault_path: ~/Documents/MyVault
    subfolder: runbooks
  notion:
    api_key: secret_...
    database_id: abc123
```

---

## Memory stores

| Store | Use case | Vector search |
|-------|----------|---------------|
| `markdown` | Solo developer, zero deps | No (substring match) |
| `faiss` | Local vector search, offline | Yes (L2, 384-dim) |
| `postgres` | Team, pgvector | Yes (cosine, 384-dim) |
| `mongo` | Team, MongoDB | Yes (Python-side cosine) |
| `smaran` | Managed team memory | Yes (Smaran cloud) |

**Note on FAISS + Python 3.14:** sentence-transformers crashes on Windows Python 3.14 due to a PyTorch DLL issue. Trident detects this via a subprocess probe and automatically falls back to TF-IDF + TruncatedSVD (LSA). The FAISS index still works; search quality is slightly lower.

---

## Connecting to Claude Code

After `trident mcp-serve`:

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

Then in Claude Code: `/memory search_memory "how did I deploy auth"`

---

## Exporting runbooks

**Obsidian:**
```bash
trident export --obsidian ~/Documents/MyVault --subfolder runbooks
```

**Notion** (requires `connectors.notion.api_key` and `database_id` in config):
```bash
trident export --notion
```

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design.

---

## Running tests

```bash
pytest tests/ -q
```

All 64 tests pass with zero network calls and zero API keys.
