"""
trident.synthesize.chunker — splits a Runbook into embedding-ready chunks.

Each chunk is a dict with 'text', 'type', and supporting metadata fields.
The chunker produces one overview chunk (title + description + variables)
plus one chunk per RunbookStep.
"""

from __future__ import annotations

from shellstory.models import Runbook


def chunk_runbook(runbook: Runbook) -> list[dict]:
    """
    Decompose a Runbook into a list of text chunks suitable for embedding.

    Each chunk dict includes:
      - text        (str)  the content to embed
      - type        (str)  "overview" | "step"
      - step_number (int)  present on "step" chunks
      - title       (str)  step title or runbook title
      - session_id  (str)  parent session ID
      - runbook_id  (str)  parent runbook ID
    """
    chunks: list[dict] = []

    # --- overview chunk -------------------------------------------------------
    var_lines = (
        "\n".join(f"  - {v.variable_name}: {v.how_to_set}" for v in runbook.variables)
        if runbook.variables
        else "  (none)"
    )
    prereq_lines = (
        "\n".join(f"  - [{p.type}] {p.name}" for p in runbook.prerequisites)
        if runbook.prerequisites
        else "  (none)"
    )
    overview_text = (
        f"Runbook: {runbook.title}\n"
        f"{runbook.description}\n\n"
        f"Variables required:\n{var_lines}\n\n"
        f"Prerequisites:\n{prereq_lines}"
    )
    chunks.append(
        {
            "text": overview_text,
            "type": "overview",
            "title": runbook.title,
            "session_id": runbook.session_id,
            "runbook_id": runbook.id,
            "step_number": None,
        }
    )

    # --- per-step chunks -------------------------------------------------------
    for step in runbook.steps:
        parts = [f"Step {step.step_number}: {step.title}"]
        if step.command:
            parts.append(f"Command:\n  {step.command}")
        parts.append(f"Explanation: {step.explanation}")
        if step.expected_output:
            parts.append(f"Expected output: {step.expected_output}")
        if step.warning:
            parts.append(f"Warning: {step.warning}")
        if step.retry_note:
            parts.append(f"Retry note: {step.retry_note}")

        chunks.append(
            {
                "text": "\n".join(parts),
                "type": "step",
                "title": step.title,
                "session_id": runbook.session_id,
                "runbook_id": runbook.id,
                "step_number": step.step_number,
            }
        )

    return chunks
