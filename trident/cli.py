"""
trident.cli — Click-based CLI entry point.

Commands:
  trident init       — interactive wizard, writes ~/.trident/config.yaml
  trident start      — begin a capture session
  trident stop       — manually stop the active session
  trident process    — synthesize a runbook from the last (or named) session
  trident query      — search the memory store
  trident run        — mechanical replay of a runbook
  trident list       — list sessions and runbooks
  trident status     — show active session and event count
  trident mcp-serve  — expose memory as MCP server (Phase 8)
  trident export     — push runbook to Obsidian or Notion (Phase 9)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

console = Console()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI group
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@click.group()
@click.version_option(package_name="trident-cli", prog_name="trident")
def main() -> None:
    """Trident — capture terminal sessions, store as team memory, replay anywhere."""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# trident init
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@main.command()
def init() -> None:
    """Interactive wizard — writes ~/.trident/config.yaml."""
    from trident.config import DEFAULT_CONFIG, _deep_copy, save_config, CONFIG_PATH

    console.print("\n[bold cyan]Trident setup wizard[/bold cyan]")
    console.print("Answer 4 questions. Press Enter to accept the default.\n")

    cfg = _deep_copy(DEFAULT_CONFIG)

    # Q1 — AI tier
    tier = click.prompt(
        "AI tier",
        type=click.Choice(["none", "local", "byok", "smaran"]),
        default="none",
        show_default=True,
    )
    cfg["ai_tier"] = tier

    # Q2 — Memory store
    default_memory = "faiss" if tier != "none" else "markdown"
    memory = click.prompt(
        "Memory store",
        type=click.Choice(["faiss", "postgres", "mongo", "markdown", "smaran"]),
        default=default_memory,
        show_default=True,
    )
    cfg["memory"]["primary"] = memory

    # Q3 — Destructive confirmation
    confirm = click.confirm(
        "Confirm destructive commands before replaying?",
        default=True,
    )
    cfg["execution"]["confirm_destructive"] = confirm

    # Q4 — Sessions directory
    default_sessions = cfg["capture"]["sessions_dir"]
    sessions = click.prompt(
        "Sessions directory",
        default=default_sessions,
        show_default=True,
    )
    cfg["capture"]["sessions_dir"] = sessions

    # If tier != none, ask for LLM details
    if tier == "local":
        model = click.prompt("Ollama model", default="llama3:8b", show_default=True)
        cfg["llm"]["provider"] = "ollama"
        cfg["llm"]["model"] = model

    elif tier == "byok":
        provider = click.prompt(
            "LLM provider",
            type=click.Choice(["openrouter", "anthropic", "openai"]),
            default="openrouter",
        )
        model = click.prompt("Model name", default="anthropic/claude-sonnet-4")
        api_key = click.prompt("API key (or leave blank to use TRIDENT_LLM_KEY env var)", default="")
        cfg["llm"]["provider"] = provider
        cfg["llm"]["model"] = model
        cfg["llm"]["api_key"] = api_key

    elif tier == "smaran":
        api_key = click.prompt("Smaran API key")
        endpoint = click.prompt(
            "Smaran endpoint", default="https://api.smaran.ai", show_default=True
        )
        cfg["llm"]["provider"] = "smaran"
        cfg["memory"]["smaran"]["api_key"] = api_key
        cfg["memory"]["smaran"]["endpoint"] = endpoint
        cfg["memory"]["primary"] = "smaran"

    path = save_config(cfg)
    console.print(f"\n[green]Config written to {path}[/green]")

    # Create dirs
    from trident.config import ensure_dirs
    ensure_dirs(cfg)

    console.print(
        "\n[bold]Next steps:[/bold]\n"
        f"  trident start \"my session\"   — begin a capture session\n"
        f"  trident process              — synthesize a runbook\n"
        f"  trident query \"deploy auth\"  — search memory\n"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# trident start
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@main.command()
@click.argument("name")
def start(name: str) -> None:
    """Begin a capture session.  Source the printed command to activate hooks."""
    from trident.config import load_config, ensure_dirs
    from trident.capture.hooks import start_session

    config = load_config()
    ensure_dirs(config)

    session, hook_path = start_session(name, config)

    console.print(f"\n[bold cyan]Session started:[/bold cyan] {session.id[:8]}...")
    console.print(f"  Title:   {name}")
    console.print(f"  Capture: {session.capture_file}")

    shell = session.shell_type or "bash"
    console.print(f"\n[bold]To activate capture hooks, run:[/bold]")

    if shell == "powershell":
        console.print(f"\n  [yellow]. {hook_path}[/yellow]\n")
        console.print("  (or paste the content of the hook file into your current PowerShell session)")
    else:
        console.print(f"\n  [yellow]source {hook_path}[/yellow]\n")

    console.print(
        "  When finished: type [bold]exit[/bold] (or run [bold]trident stop[/bold])"
    )
    console.print(f"  Then: [bold]trident process[/bold] to generate a runbook\n")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# trident stop
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@main.command()
@click.option("--session-id", default=None, help="Session ID (prefix OK). Defaults to active session.")
def stop(session_id: Optional[str]) -> None:
    """Manually mark the active session as stopped."""
    from trident.capture.hooks import get_active_session, stop_session

    if session_id:
        from trident.capture.hooks import get_session
        sess = get_session(session_id)
    else:
        sess = get_active_session()

    if not sess:
        console.print("[red]No active session found.[/red]")
        sys.exit(1)

    stop_session(sess.id)
    console.print(f"[green]Session {sess.id[:8]}... marked as stopped.[/green]")
    console.print("Run [bold]trident process[/bold] to generate a runbook.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# trident process
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@main.command()
@click.option("--session-id", default=None, help="Session ID (prefix OK). Defaults to most recent.")
def process(session_id: Optional[str]) -> None:
    """Synthesize a runbook from a capture session."""
    from trident.config import load_config, db_path, ensure_dirs
    from trident.capture.adapter import Database, load_events
    from trident.capture.redact import redact
    from trident.tier import get_synthesizer, get_memory_store, resolve_tier
    from trident.synthesize.chunker import chunk_runbook
    from datetime import datetime, timezone

    config = load_config()
    ensure_dirs(config)

    db = Database(db_path())
    try:
        if session_id:
            session = db.get_session(session_id)
        else:
            session = db.get_active_session()
            if not session:
                # fall back to most recent
                sessions = db.list_sessions(limit=1)
                session = sessions[0] if sessions else None
    finally:
        db.close()

    if not session:
        console.print("[red]No session found. Run 'trident start <name>' first.[/red]")
        sys.exit(1)

    capture_file = Path(session.capture_file)
    if not capture_file.exists():
        console.print(f"[red]Capture file not found: {capture_file}[/red]")
        sys.exit(1)

    console.print(f"\n[bold cyan]Processing session:[/bold cyan] {session.id[:8]}...")
    console.print(f"  Title:   {session.title}")
    console.print(f"  Capture: {capture_file}")

    # Load events
    with console.status("Loading events..."):
        events = load_events(capture_file)
    console.print(f"  Loaded {len(events)} event(s)")

    # Redact PII
    redact_mode = config["capture"].get("redaction", "strict")
    with console.status(f"Redacting PII ({redact_mode})..."):
        redaction_result = redact(events, mode=redact_mode)
    if redaction_result.redaction_count > 0:
        console.print(
            f"  Redacted {redaction_result.redaction_count} secret(s): "
            + ", ".join(v.variable_name for v in redaction_result.variables[:5])
        )

    # Synthesize
    tier = resolve_tier(config)
    synthesizer = get_synthesizer(config)
    console.print(f"  Synthesizing (tier: {tier})...")
    with console.status("Running synthesis..."):
        runbook = synthesizer.synthesize(
            redaction_result.events,
            title=session.title,
            session_id=session.id,
        )

    console.print(f"  Steps:     {len(runbook.steps)}")
    console.print(f"  Variables: {len(runbook.variables)}")

    # Chunk and store
    chunks = chunk_runbook(runbook)
    memory_store = get_memory_store(config)
    metadata = {
        "title": runbook.title,
        "session_id": runbook.session_id,
        "runbook_id": runbook.id,
        "tier": tier,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runbook": runbook.model_dump(),  # full structured data for rich rendering
    }
    store_id = memory_store.write(chunks, metadata)

    # Save runbook to DB
    db = Database(db_path())
    try:
        db.save_runbook(runbook)
    finally:
        db.close()

    console.print(f"\n[green]Runbook written:[/green] {store_id}")
    console.print(f"  Run [bold]trident run[/bold] to replay it.\n")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# trident query
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@main.command()
@click.argument("query_text")
@click.option("-k", default=5, show_default=True, help="Number of results to return.")
def query(query_text: str, k: int) -> None:
    """Search the memory store for relevant runbooks."""
    from trident.config import load_config
    from trident.tier import get_memory_store

    config = load_config()
    store = get_memory_store(config)

    with console.status("Searching..."):
        results = store.query(query_text, k=k)

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    console.print(f"\n[bold]Results for:[/bold] {query_text}\n")
    for i, result in enumerate(results, 1):
        console.print(f"[bold cyan]{i}. {result.get('title', 'Untitled')}[/bold cyan]")
        if result.get("created_at"):
            console.print(f"   Created: {result['created_at'][:19]}")
        if result.get("step_count"):
            console.print(f"   Steps:   {result['step_count']}")
        if result.get("path"):
            console.print(f"   File:    {result['path']}")
        if result.get("snippet"):
            snippet = result["snippet"][:200].replace("\n", " ")
            console.print(f"   [dim]{snippet}...[/dim]")
        console.print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# trident run
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@main.command()
@click.argument("runbook_id", required=False, default=None)
def run(runbook_id: Optional[str]) -> None:
    """Replay a runbook step by step (mechanical, no AI)."""
    from trident.config import load_config, db_path
    from trident.capture.adapter import Database, Runbook
    from trident.execute.mechanical import MechanicalReplayer

    config = load_config()
    db = Database(db_path())

    try:
        if runbook_id:
            runbook = db.get_runbook(runbook_id)
            if not runbook:
                # Try treating it as a session ID
                session = db.get_session(runbook_id)
                runbook = db.get_runbook_by_session(session.id) if session else None
        else:
            # Use the most recently completed session's runbook
            sessions = db.list_sessions(limit=10)
            runbook = None
            for sess in sessions:
                if sess.runbook_id:
                    runbook = db.get_runbook(sess.runbook_id)
                    if runbook:
                        break
    finally:
        db.close()

    if not runbook:
        console.print(
            "[red]No runbook found.[/red] Run [bold]trident process[/bold] first."
        )
        sys.exit(1)

    replayer = MechanicalReplayer(config)
    result = replayer.run(runbook)

    if not result.success:
        sys.exit(1)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# trident list
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@main.command(name="list")
@click.option("--limit", default=20, show_default=True, help="Max sessions to show.")
def list_cmd(limit: int) -> None:
    """List capture sessions and their runbook status."""
    from trident.config import load_config, db_path
    from trident.capture.adapter import Database

    load_config()
    db = Database(db_path())
    try:
        sessions = db.list_sessions(limit=limit)
    finally:
        db.close()

    if not sessions:
        console.print("[yellow]No sessions yet. Run 'trident start <name>'.[/yellow]")
        return

    table = Table(title="Trident Sessions", show_lines=False)
    table.add_column("ID", style="dim", width=10)
    table.add_column("Title", style="bold")
    table.add_column("Status", width=12)
    table.add_column("Runbook", width=8)
    table.add_column("Started", width=20)

    for sess in sessions:
        status_style = {
            "capturing": "yellow",
            "processing": "cyan",
            "complete": "green",
            "error": "red",
        }.get(sess.status, "white")

        table.add_row(
            sess.id[:8],
            sess.title,
            f"[{status_style}]{sess.status}[/{status_style}]",
            "yes" if sess.runbook_id else "no",
            sess.started_at.strftime("%Y-%m-%d %H:%M") if sess.started_at else "",
        )

    console.print(table)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# trident status
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@main.command()
@click.option("--watch", is_flag=True, default=False, help="Live-updating dashboard.")
def status(watch: bool) -> None:
    """Show active session and event count."""
    from trident.config import load_config, db_path
    from trident.capture.adapter import Database
    from trident.capture.ndjson import event_count
    from pathlib import Path

    config = load_config()

    if watch:
        from trident.ui.dashboard import launch
        launch(config)
        return

    db = Database(db_path())
    try:
        session = db.get_active_session()
    finally:
        db.close()

    if not session:
        console.print("[yellow]No active session.[/yellow]")
        console.print("Run [bold]trident start <name>[/bold] to begin capturing.")
        return

    capture_file = Path(session.capture_file)
    n_events = event_count(capture_file)

    console.print(f"\n[bold cyan]Active session:[/bold cyan] {session.id[:8]}...")
    console.print(f"  Title:       {session.title}")
    console.print(f"  Shell:       {session.shell_type or 'unknown'}")
    console.print(f"  Events:      {n_events}")
    console.print(f"  Capture:     {session.capture_file}")
    console.print(f"  Started:     {session.started_at.strftime('%Y-%m-%d %H:%M:%S') if session.started_at else 'unknown'}")
    console.print(
        f"\n  Run [bold]trident process[/bold] when done to generate a runbook.\n"
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# trident mcp-serve
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@main.command("mcp-serve")
@click.option("--port", default=9000, show_default=True, help="Port to bind.")
@click.option("--host", default="localhost", show_default=True, help="Host to bind.")
def mcp_serve(port: int, host: str) -> None:
    """Expose Trident memory as an MCP server (for Claude Code, Cursor, etc.)."""
    from trident.config import load_config
    from trident.execute.mcp_bridge import serve

    config = load_config()
    config.setdefault("mcp_bridge", {})
    config["mcp_bridge"]["port"] = port
    config["mcp_bridge"]["host"] = host

    console.print(
        f"\n[bold cyan]Trident MCP bridge[/bold cyan] starting on {host}:{port}\n"
        f"  Connect: http://{host}:{port}/sse\n"
        f"  Tools:   search_memory, list_runbooks, get_runbook\n"
        f"\nPress Ctrl+C to stop.\n"
    )
    serve(config)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# trident export
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@main.command()
@click.option("--obsidian", "vault_path", default=None, help="Obsidian vault path.")
@click.option("--subfolder", default="runbooks", show_default=True, help="Subfolder within vault.")
@click.option("--notion", "to_notion", is_flag=True, default=False, help="Export to Notion.")
@click.option("--runbook-id", default=None, help="Runbook ID (defaults to most recent).")
def export(
    vault_path: Optional[str],
    subfolder: str,
    to_notion: bool,
    runbook_id: Optional[str],
) -> None:
    """Export a runbook to Obsidian or Notion."""
    from trident.config import load_config, db_path
    from trident.capture.adapter import Database

    if not vault_path and not to_notion:
        console.print("[red]Specify --obsidian <vault-path> or --notion[/red]")
        sys.exit(1)

    config = load_config()
    db = Database(db_path())
    try:
        if runbook_id:
            runbook = db.get_runbook(runbook_id)
        else:
            sessions = db.list_sessions(limit=10)
            runbook = None
            for sess in sessions:
                if sess.runbook_id:
                    runbook = db.get_runbook(sess.runbook_id)
                    if runbook:
                        break
    finally:
        db.close()

    if not runbook:
        console.print("[red]No runbook found. Run 'trident process' first.[/red]")
        sys.exit(1)

    if vault_path:
        from trident.connectors.obsidian import export as obs_export
        out = obs_export(runbook, vault_path, subfolder)
        console.print(f"[green]Exported to Obsidian:[/green] {out}")

    if to_notion:
        from trident.connectors.notion import export_from_config as notion_export
        url = notion_export(runbook, config)
        console.print(f"[green]Exported to Notion:[/green] {url}")
