"""
trident.connectors.markdown — wraps ShellStory's MarkdownConnector.
"""

from __future__ import annotations

from shellstory.connectors import MarkdownConnector as _MarkdownConnector  # noqa: F401
from shellstory.models import Runbook


def export(runbook: Runbook, config: dict) -> str:
    """Export a Runbook to a Markdown file.  Returns the output path."""
    connector_config = config.get("connectors", {}).get("markdown", {})
    connector = _MarkdownConnector()
    return connector.export(runbook, connector_config)
