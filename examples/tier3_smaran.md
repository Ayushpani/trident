# Tier 3 — Smaran (Managed Team Memory)

Smaran provides graph-clustered team memory that persists across sessions and
is shared across your organization. Synthesis uses the same 5-agent swarm as
Tier 2, but memory is stored in Smaran's cloud.

## Setup

```bash
# Get an API key at smaran.ai
pip install 'trident-cli[byok]'   # for the swarm LLM client

trident init
# → AI tier: smaran
# → Smaran API key: sm_...
# → Smaran endpoint: https://api.smaran.ai  (default)
```

This sets `memory.primary: smaran` automatically.

## What changes at Tier 3

- **Memory**: `SmaranStore` sends chunks to Smaran via REST API. Smaran handles
  embedding, deduplication, and graph-clustered retrieval on its end. No local
  ML deps needed for memory.

- **Synthesis**: same 5-agent `SwarmSynthesizer` as Tier 2 (you still need a
  BYOK LLM key for the swarm agents).

## Config snippet

```yaml
ai_tier: smaran
llm:
  provider: anthropic
  model: claude-sonnet-4-6
  api_key: ""   # or TRIDENT_LLM_KEY
memory:
  primary: smaran
  smaran:
    api_key: "sm_..."
    endpoint: "https://api.smaran.ai"
    container_tag: "my-team"   # optional namespace
```

## Usage

```bash
trident start "postgres migration"
source ~/.trident/sessions/<id>.sh
# run migration commands
exit
trident process   # → swarm synthesis + write to Smaran cloud
trident query "postgres migration rollback"   # → Smaran semantic search
```

## Team sharing

All team members pointing to the same Smaran account + container_tag will
share memory. `trident query "incident last week"` returns runbooks written by
any team member.

## Container tags

Use `memory.smaran.container_tag` to namespace memory by project or team:

```yaml
memory:
  smaran:
    container_tag: "platform-team"
```

Each tag creates a separate memory space in Smaran.

## Listing stored runbooks

```bash
trident list     # shows local sessions
trident query "" # broad query returns recent Smaran memories
```
