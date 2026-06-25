# Tier 2 — BYOK (Bring Your Own Key)

Uses ShellStory's 5-agent swarm with your own API key. Highest quality synthesis.

## Setup

```bash
pip install 'trident-cli[byok,faiss]'

trident init
# → AI tier: byok
# → LLM provider: openrouter  (or anthropic / openai)
# → Model: anthropic/claude-sonnet-4  (or any OpenRouter model)
# → API key: <your key>
# → Memory store: faiss
```

Or set the key as an environment variable instead:
```bash
export TRIDENT_LLM_KEY="sk-..."
```

## What changes at Tier 2

- **Synthesis**: `SwarmSynthesizer` runs ShellStory's full 5-agent pipeline:
  1. **Extractor** — identifies signal commands, ignores noise
  2. **Enricher** — adds context and explanations
  3. **Validator** — checks for missing steps or prerequisites
  4. **Formatter** — produces clean, runnable commands
  5. **Reviewer** — final quality pass

- **Memory**: FAISS vector search (same as Tier 1)

- **Resilience**: `ResilientLLMClient` wraps the primary client with exponential
  backoff on rate limits and a fallback chain.

## Config snippet

```yaml
ai_tier: byok
llm:
  provider: openrouter
  model: anthropic/claude-sonnet-4
  api_key: ""              # set TRIDENT_LLM_KEY instead
memory:
  primary: faiss
```

## OpenRouter example

```bash
export TRIDENT_LLM_KEY="sk-or-v1-..."
trident process
```

## Anthropic example

```yaml
llm:
  provider: anthropic
  model: claude-sonnet-4-6
```

## Postgres vector search (team setup)

```bash
pip install 'trident-cli[postgres]'
# In Postgres: CREATE EXTENSION vector;
```

```yaml
memory:
  primary: postgres
  postgres:
    url: postgresql://user:pass@db:5432/trident
```

## Expose to Claude Code

```bash
pip install 'trident-cli[mcp]'
trident mcp-serve     # binds to localhost:9000
```

Add to `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "trident": { "transport": "sse", "url": "http://localhost:9000/sse" }
  }
}
```
