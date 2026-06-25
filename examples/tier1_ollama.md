# Tier 1 — Local Ollama

Requires Ollama running locally. No API keys, no cloud.

## Setup

```bash
# Install Ollama: https://ollama.ai
ollama pull llama3:8b   # or mistral:7b, codellama:13b, etc.

pip install 'trident-cli[faiss]'   # optional: local vector search

trident init
# → AI tier: local
# → Memory store: faiss  (or markdown)
# → Ollama model: llama3:8b
```

## What changes at Tier 1

- **Synthesis**: `LocalAgentSynthesizer` sends raw command history to Ollama with a
  DevOps prompt. It parses the JSON response into a Runbook. If Ollama is
  unreachable, falls back to `DeterministicSynthesizer`.

- **Memory**: if you choose `faiss`, chunks are embedded with sentence-transformers
  (or TF-IDF fallback) and stored in a local FAISS index. `trident query` returns
  semantically similar chunks, not just substring matches.

## Usage

Same as Tier 0:
```bash
trident start "k8s cert renewal"
source ~/.trident/sessions/<id>.sh
# ... run commands ...
exit
trident process      # calls Ollama for synthesis
trident query "certificate renewal"  # semantic search (FAISS)
trident run
```

## Config snippet

```yaml
ai_tier: local
llm:
  provider: ollama
  model: llama3:8b
memory:
  primary: faiss
  faiss:
    path: ~/.trident/memory/faiss
```

## Verify Ollama is being used

```bash
HTTPX_LOG_LEVEL=debug trident process 2>&1 | grep localhost:11434
# Should show: POST http://localhost:11434/api/chat
```
