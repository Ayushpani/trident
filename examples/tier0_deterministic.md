# Tier 0 — Deterministic (no AI)

The default. Works with zero API keys, no GPU, no cloud.

## Setup

```bash
pip install -e shellstory-main/shellstory-main
pip install -e .
trident init
# → AI tier: none
# → Memory store: markdown
# → Confirm destructive: Y
# → Sessions dir: (default)
```

## Capture a session

```bash
trident start "deploy auth service"

# Source the hook (bash/zsh):
source ~/.trident/sessions/<session-id>.sh

# Now run your commands:
cd ~/projects/auth
docker build -t auth:latest .
kubectl apply -f k8s/auth-deployment.yaml
kubectl rollout status deployment/auth
exit
```

## Synthesize

```bash
trident process
```

The `DeterministicSynthesizer` will:
1. Drop noise (`ls`, `pwd`, `clear`, etc.)
2. Collapse error→recovery pairs (failed command followed by fix)
3. Drop lone `cd` commands with no subsequent work
4. Group remaining commands by working directory into RunbookSteps
5. Extract environment variables, ports, and file references

Example output:
```
Processing session: a3f7b2c1...
  Title:   deploy auth service
  Capture: ~/.trident/sessions/a3f7b2c1.ndjson
  Loaded 23 event(s)
  Redacted 0 secret(s)
  Synthesizing (tier: none)...
  Steps:     3
  Variables: 1

Runbook written: 9e1d4c2a-...
```

## Search

```bash
trident query "docker build auth"
```

Results use substring match on titles and content (no vectors at Tier 0).

## Replay

```bash
trident run
```

Replays each command step by step. Stops on first non-zero exit code.
Prompts before destructive commands if `confirm_destructive: true`.

## Verify no LLM calls

```bash
HTTPX_LOG_LEVEL=debug trident process 2>&1 | grep -i "POST\|GET\|openai\|anthropic\|ollama"
# Should produce no output
```
