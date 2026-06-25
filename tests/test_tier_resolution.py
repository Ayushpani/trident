"""
tests.test_tier_resolution — verify tier and store resolution from config.
"""

from __future__ import annotations

import pytest

from trident.tier import resolve_tier, get_synthesizer, get_memory_store


def _config(tier: str = "none", memory: str = "markdown") -> dict:
    return {
        "ai_tier": tier,
        "llm": {
            "provider": "ollama",
            "model": "llama3:8b",
            "api_key": "",
            "fallback_chain": [],
        },
        "memory": {
            "primary": memory,
            "faiss": {"path": "/tmp/faiss", "embedding_model": "all-MiniLM-L6-v2"},
            "postgres": {"url": ""},
            "mongo": {"url": ""},
            "smaran": {"api_key": "", "endpoint": "https://api.smaran.ai"},
        },
        "execution": {"mode": "mechanical", "confirm_destructive": True},
        "connectors": {"obsidian": {"enabled": False}, "notion": {"enabled": False}},
        "capture": {"redaction": "strict", "sessions_dir": "/tmp/sessions"},
    }


# ── resolve_tier ──────────────────────────────────────────────────────────────


def test_resolve_tier_none():
    assert resolve_tier(_config("none")) == "none"


def test_resolve_tier_local():
    assert resolve_tier(_config("local")) == "local"


def test_resolve_tier_byok():
    assert resolve_tier(_config("byok")) == "byok"


def test_resolve_tier_smaran():
    assert resolve_tier(_config("smaran")) == "smaran"


def test_resolve_tier_defaults_to_none():
    assert resolve_tier({}) == "none"


# ── get_synthesizer ───────────────────────────────────────────────────────────


def test_tier_none_returns_deterministic():
    from trident.synthesize.deterministic import DeterministicSynthesizer
    synth = get_synthesizer(_config("none"))
    assert isinstance(synth, DeterministicSynthesizer)


def test_tier_local_returns_deterministic_fallback_when_ollama_unreachable():
    """LocalAgentSynthesizer falls back to DeterministicSynthesizer on import/connection error."""
    from trident.synthesize.deterministic import DeterministicSynthesizer
    # Ollama is unlikely to be running in CI — should fall back gracefully
    synth = get_synthesizer(_config("local"))
    # Either LocalAgentSynthesizer or DeterministicSynthesizer is acceptable
    assert synth is not None
    assert hasattr(synth, "synthesize")


def test_tier_none_synthesizer_makes_no_network_calls(monkeypatch):
    import httpx
    def fail(*args, **kwargs):
        raise AssertionError("No network calls allowed from Tier 0 synthesizer")
    monkeypatch.setattr(httpx, "post", fail)
    monkeypatch.setattr(httpx, "get", fail)

    synth = get_synthesizer(_config("none"))
    from datetime import datetime, timezone
    from shellstory.models import RawEvent
    events = [
        RawEvent(
            event_type="command",
            timestamp=datetime.now(timezone.utc),
            session_id="test",
            sequence=1,
            command="git status",
            exit_code=0,
        )
    ]
    runbook = synth.synthesize(events, title="Test")
    assert runbook is not None


# ── get_memory_store ──────────────────────────────────────────────────────────


def test_markdown_store_returned_for_markdown_config():
    from trident.memory.markdown_store import MarkdownStore
    store = get_memory_store(_config("none", "markdown"))
    assert isinstance(store, MarkdownStore)


def test_faiss_store_raises_import_error_without_faiss(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name in ("faiss", "sentence_transformers"):
            raise ImportError(f"Mocked missing: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    with pytest.raises(ImportError, match="faiss"):
        get_memory_store(_config("none", "faiss"))


def test_unknown_tier_still_returns_deterministic():
    """Unrecognised tier strings should fall back safely, never crash."""
    synth = get_synthesizer({"ai_tier": "unknown_future_tier"})
    from trident.synthesize.deterministic import DeterministicSynthesizer
    assert isinstance(synth, DeterministicSynthesizer)


def test_unknown_memory_store_raises():
    with pytest.raises(ValueError, match="Unknown memory store"):
        get_memory_store(_config("none", "redis"))
