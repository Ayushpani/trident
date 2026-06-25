"""
trident.connectors.obsidian — Phase 9 stub.

Writes runbooks into an Obsidian vault with YAML frontmatter.
"""

from __future__ import annotations

from shellstory.models import Runbook


def export(runbook: Runbook, vault_path: str, subfolder: str = "runbooks") -> str:
    raise NotImplementedError("obsidian.export — Phase 9")
