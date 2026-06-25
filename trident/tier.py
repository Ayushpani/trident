"""
trident.tier — resolve which AI tier, memory store, and synthesizer to use.

Everything flows from ~/.trident/config.yaml; callers ask this module for
the right object and never make provider decisions themselves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from trident.memory.base import MemoryStore


TierName = Literal["none", "local", "byok", "smaran"]


def resolve_tier(config: dict[str, Any]) -> TierName:
    """Return the configured AI tier name."""
    return config.get("ai_tier", "none")


def get_memory_store(config: dict[str, Any]) -> "MemoryStore":
    """Instantiate and return the configured primary memory store."""
    primary = config["memory"].get("primary", "markdown")

    if primary == "markdown":
        from trident.memory.markdown_store import MarkdownStore
        return MarkdownStore(config)

    if primary == "faiss":
        try:
            from trident.memory.faiss_store import FAISSStore
            return FAISSStore(config)
        except ImportError as exc:
            raise ImportError(
                "FAISS store requires extra deps: pip install 'trident-cli[faiss]'"
            ) from exc

    if primary == "postgres":
        try:
            from trident.memory.postgres_store import PostgresStore
            return PostgresStore(config)
        except ImportError as exc:
            raise ImportError(
                "Postgres store requires extra deps: pip install 'trident-cli[postgres]'"
            ) from exc

    if primary == "mongo":
        try:
            from trident.memory.mongo_store import MongoStore
            return MongoStore(config)
        except ImportError as exc:
            raise ImportError(
                "Mongo store requires extra deps: pip install 'trident-cli[mongo]'"
            ) from exc

    if primary == "smaran":
        from trident.memory.smaran_store import SmaranStore
        return SmaranStore(config)

    raise ValueError(f"Unknown memory store: {primary!r}")


def get_synthesizer(config: dict[str, Any]):
    """
    Return the appropriate synthesizer for the configured AI tier.

    Tier 0 (none)  → DeterministicSynthesizer (no LLM, always works)
    Tier 1 (local) → LocalAgentSynthesizer (Ollama; falls back to Tier 0)
    Tier 2 (byok)  → SwarmSynthesizer (5-agent pipeline via ShellStory swarm)
    Tier 3 (smaran)→ SwarmSynthesizer (same swarm, Smaran memory)
    """
    tier = resolve_tier(config)

    if tier == "none":
        from trident.synthesize.deterministic import DeterministicSynthesizer
        return DeterministicSynthesizer()

    if tier == "local":
        try:
            from trident.synthesize.local_agent import LocalAgentSynthesizer
            return LocalAgentSynthesizer(config)
        except Exception:
            from trident.synthesize.deterministic import DeterministicSynthesizer
            return DeterministicSynthesizer()

    if tier in ("byok", "smaran"):
        from trident.synthesize.swarm import SwarmSynthesizer
        return SwarmSynthesizer(config)

    from trident.synthesize.deterministic import DeterministicSynthesizer
    return DeterministicSynthesizer()


def get_llm_client(config: dict[str, Any]):
    """
    Return an LLMClient for the configured tier, or None if ai_tier is 'none'.
    """
    tier = resolve_tier(config)
    if tier == "none":
        return None

    provider = config["llm"].get("provider", "ollama")

    if provider == "ollama":
        from trident.llm.ollama_client import OllamaClient
        return OllamaClient(config)

    if provider == "openrouter":
        from trident.llm.openrouter_client import OpenRouterClient
        return OpenRouterClient(config)

    if provider == "anthropic":
        from trident.llm.anthropic_client import AnthropicClient
        return AnthropicClient(config)

    if provider == "openai":
        from trident.llm.openai_client import OpenAIClient
        return OpenAIClient(config)

    raise ValueError(f"Unknown LLM provider: {provider!r}")
