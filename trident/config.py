"""
trident.config — YAML config at ~/.trident/config.yaml.

All behaviour is driven from this file; nothing in Trident is hardcoded.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import yaml

TRIDENT_DIR = Path.home() / ".trident"
CONFIG_PATH = TRIDENT_DIR / "config.yaml"

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "ai_tier": "none",  # none | local | byok | smaran
    "llm": {
        "provider": "ollama",  # ollama | openrouter | anthropic | openai
        "model": "llama3:8b",
        "api_key": "",
        "fallback_chain": [],
    },
    "memory": {
        "primary": "markdown",  # faiss | postgres | mongo | markdown | smaran
        "faiss": {
            "path": str(TRIDENT_DIR / "memory" / "faiss"),
            "embedding_model": "all-MiniLM-L6-v2",
        },
        "postgres": {"url": ""},
        "mongo": {"url": ""},
        "smaran": {
            "api_key": "",
            "endpoint": "https://api.smaran.ai",
        },
    },
    "execution": {
        "mode": "mechanical",  # mechanical | ksai_local | ksai_byok | external_mcp
        "confirm_destructive": True,
    },
    "connectors": {
        "obsidian": {"enabled": False, "vault_path": ""},
        "notion": {"enabled": False, "api_key": "", "database_id": ""},
    },
    "capture": {
        "redaction": "strict",  # strict | standard | off
        "sessions_dir": str(TRIDENT_DIR / "sessions"),
    },
}


def load_config(path: Path | None = None) -> dict[str, Any]:
    """
    Load config from disk, creating it with defaults if missing.
    Environment variable TRIDENT_LLM_KEY overrides llm.api_key.
    """
    cfg_path = path or CONFIG_PATH
    if not cfg_path.exists():
        cfg = _deep_copy(DEFAULT_CONFIG)
        save_config(cfg, cfg_path)
        return cfg

    with open(cfg_path, encoding="utf-8") as f:
        on_disk = yaml.safe_load(f) or {}

    cfg = _deep_merge(DEFAULT_CONFIG, on_disk)

    env_key = os.environ.get("TRIDENT_LLM_KEY", "")
    if env_key:
        cfg["llm"]["api_key"] = env_key

    return cfg


def save_config(config: dict[str, Any], path: Path | None = None) -> Path:
    """Write config to YAML with secure permissions (owner read/write only)."""
    cfg_path = path or CONFIG_PATH
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    try:
        cfg_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, NotImplementedError):
        pass  # Windows may not support this; non-fatal

    return cfg_path


def ensure_dirs(config: dict[str, Any]) -> None:
    """Create all directories Trident needs at runtime."""
    sessions_dir = Path(config["capture"]["sessions_dir"]).expanduser()
    sessions_dir.mkdir(parents=True, exist_ok=True)

    memory_dir = TRIDENT_DIR / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    runbooks_dir = memory_dir / "runbooks"
    runbooks_dir.mkdir(parents=True, exist_ok=True)

    primary = config["memory"].get("primary", "markdown")
    if primary == "faiss":
        faiss_path = Path(config["memory"]["faiss"]["path"]).expanduser()
        faiss_path.mkdir(parents=True, exist_ok=True)


def sessions_dir(config: dict[str, Any]) -> Path:
    return Path(config["capture"]["sessions_dir"]).expanduser()


def db_path() -> Path:
    return TRIDENT_DIR / "trident.db"


# ── Internal helpers ──────────────────────────────────────────────────────────


def _deep_copy(d: dict) -> dict:
    import copy
    return copy.deepcopy(d)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    import copy
    result = copy.deepcopy(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result
