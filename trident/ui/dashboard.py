"""
trident.ui.dashboard — Rich live dashboard.

Launched by `trident status --watch`.  Shows:
  - Active session header (title, event count, file)
  - Recent runbooks table
  - AI tier and memory store

Refreshes every 2 seconds.  Press Ctrl+C to exit.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def launch(config: dict[str, Any]) -> None:
    """Start the live-updating dashboard (blocking until Ctrl+C)."""
    console = Console()
    try:
        with Live(
            _render(config),
            console=console,
            refresh_per_second=0.5,
            screen=True,
        ) as live:
            while True:
                time.sleep(2)
                live.update(_render(config))
    except KeyboardInterrupt:
        pass


# ── Rendering ─────────────────────────────────────────────────────────────────


def _render(config: dict[str, Any]) -> Columns:
    return Columns([_session_panel(config), _runbooks_panel(config)], expand=True)


def _session_panel(config: dict[str, Any]) -> Panel:
    from trident.config import db_path
    from trident.capture.adapter import Database
    from trident.capture.ndjson import event_count

    lines: list[str] = []
    try:
        db = Database(db_path())
        try:
            session = db.get_active_session()
        finally:
            db.close()

        if session:
            cap_path = Path(session.capture_file)
            n_events = event_count(cap_path) if cap_path.exists() else 0
            started = (
                session.started_at.strftime("%Y-%m-%d %H:%M:%S")
                if session.started_at
                else "unknown"
            )
            lines += [
                f"[bold cyan]ID:[/bold cyan]      {session.id[:12]}",
                f"[bold cyan]Title:[/bold cyan]   {session.title}",
                f"[bold cyan]Shell:[/bold cyan]   {session.shell_type or 'unknown'}",
                f"[bold cyan]Events:[/bold cyan]  {n_events}",
                f"[bold cyan]Started:[/bold cyan] {started}",
                "",
                f"[dim]{session.capture_file}[/dim]",
            ]
        else:
            lines += [
                "[yellow]No active session[/yellow]",
                "",
                "Run [bold]trident start <name>[/bold] to begin.",
            ]
    except Exception as exc:
        lines.append(f"[red]Error: {exc}[/red]")

    tier = config.get("ai_tier", "none")
    primary = config.get("memory", {}).get("primary", "markdown")
    lines += [
        "",
        f"[dim]AI tier:  {tier}[/dim]",
        f"[dim]Memory:   {primary}[/dim]",
    ]

    content = Text.from_markup("\n".join(lines))
    return Panel(content, title="Active Session", border_style="cyan")


def _runbooks_panel(config: dict[str, Any]) -> Panel:
    try:
        from trident.tier import get_memory_store

        store = get_memory_store(config)
        entries = store.list()[:10]
    except Exception as exc:
        return Panel(
            Text.from_markup(f"[red]Memory store error: {exc}[/red]"),
            title="Recent Runbooks",
            border_style="green",
        )

    table = Table(show_header=True, header_style="bold green", box=None, padding=(0, 1))
    table.add_column("Title", style="bold")
    table.add_column("Created", style="dim", width=16)
    table.add_column("Session", style="dim", width=10)

    for entry in entries:
        created = entry.get("created_at", "")[:16].replace("T", " ")
        sess = entry.get("session_id", "")[:8]
        table.add_row(entry.get("title", "Untitled"), created, sess)

    if not entries:
        table.add_row(
            "[dim]No runbooks yet — run trident process[/dim]", "", ""
        )

    return Panel(table, title="Recent Runbooks", border_style="green")
