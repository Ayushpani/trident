"""
trident.ui.tui — full-session interactive dashboard.

Stay in the TUI for the entire Trident workflow:
  SESSIONS  start capture -> monitor events -> process runbook
  RUNBOOKS  search -> live preview -> full viewer
  REPLAY    select runbook -> stream step output
  SEARCH    query memory store
  CONFIG    current configuration

Navigation
  1-6    switch panel
  r      refresh current panel
  q      quit
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import (
    Button,
    ContentSwitcher,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    RichLog,
    Rule,
    Static,
)


# ── data helpers ──────────────────────────────────────────────────────────────

def _dir() -> Path:
    return Path.home() / ".trident"


def _load_config() -> dict:
    try:
        import yaml
        with open(_dir() / "config.yaml") as f:
            cfg = yaml.safe_load(f) or {}
        cfg.setdefault("ai_tier", "none")
        cfg.setdefault("memory", {})
        cfg["memory"].setdefault("primary", "markdown")
        return cfg
    except Exception:
        return {"ai_tier": "none", "memory": {"primary": "markdown"}}


def _load_runbooks() -> list[dict]:
    try:
        data = json.loads((_dir() / "memory" / "index.json").read_text(encoding="utf-8"))
        data.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return data
    except Exception:
        return []


def _load_sessions() -> list[dict]:
    try:
        from trident.config import db_path
        from trident.capture.adapter import Database
        db = Database(db_path())
        try:
            return [
                {
                    "id": s.id,
                    "title": s.title,
                    "status": s.status,
                    "has_runbook": bool(s.runbook_id),
                    "started_at": s.started_at.isoformat() if s.started_at else "",
                }
                for s in db.list_sessions(limit=20)
            ]
        finally:
            db.close()
    except Exception:
        return []


def _get_active_session() -> dict | None:
    try:
        from trident.config import db_path
        from trident.capture.adapter import Database
        db = Database(db_path())
        try:
            s = db.get_active_session()
            if not s:
                return None
            capture = Path(s.capture_file)
            n = 0
            if capture.exists():
                with open(capture) as f:
                    n = sum(1 for _ in f)
            return {
                "id": s.id,
                "title": s.title,
                "status": s.status,
                "capture_file": s.capture_file,
                "event_count": n,
                "started_at": s.started_at.isoformat() if s.started_at else "",
            }
        finally:
            db.close()
    except Exception:
        return None


def _count_sessions() -> int:
    d = _dir() / "sessions"
    return sum(1 for f in d.iterdir() if f.suffix == ".ndjson") if d.exists() else 0


def _read_runbook(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        return "_Could not read file._"


def _rel_time(ts: str) -> str:
    if not ts:
        return "--"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        secs = (datetime.now(timezone.utc) - dt).total_seconds()
        if secs < 60:
            return "just now"
        if secs < 3_600:
            return f"{int(secs / 60)}m ago"
        if secs < 86_400:
            return f"{int(secs / 3_600)}h ago"
        return dt.strftime("%b %d")
    except Exception:
        return "--"


def _tier_label(tier: str) -> str:
    return {
        "none":   "Tier 0  deterministic",
        "local":  "Tier 1  Ollama",
        "byok":   "Tier 2  BYOK",
        "smaran": "Tier 3  Smaran",
    }.get(tier, tier)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


# ── messages ──────────────────────────────────────────────────────────────────

class SwitchPanel(Message):
    def __init__(self, panel_id: str) -> None:
        super().__init__()
        self.panel_id = panel_id


# ── viewer screen (full-screen markdown) ──────────────────────────────────────

class ViewerScreen(Screen):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("q",      "back", "Back",    show=False),
        Binding("g",      "top",  "Top"),
        Binding("G",      "bottom", "Bottom"),
        Binding("ctrl+d", "page_down", "Page down", show=False),
        Binding("ctrl+u", "page_up",   "Page up",   show=False),
    ]

    def __init__(self, runbook: dict) -> None:
        super().__init__()
        self._meta    = runbook
        self._content = _read_runbook(runbook.get("path", ""))

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(id="vs"):
            yield Markdown(self._content)
        yield Footer()

    def on_mount(self) -> None:
        self.app.sub_title = self._meta.get("title", "viewer")

    def on_unmount(self) -> None:
        self.app.sub_title = "no active session"

    def action_back(self)      -> None: self.app.pop_screen()
    def action_top(self)       -> None: self.query_one("#vs", VerticalScroll).scroll_home(animate=True)
    def action_bottom(self)    -> None: self.query_one("#vs", VerticalScroll).scroll_end(animate=True)
    def action_page_down(self) -> None: self.query_one("#vs", VerticalScroll).action_page_down()
    def action_page_up(self)   -> None: self.query_one("#vs", VerticalScroll).action_page_up()


# ── HOME panel ────────────────────────────────────────────────────────────────

_LOGO = """\
  _______ _____  ___ ____  _____  _   _ _____
 |__   __|  __ \\|_ _|  _ \\| ____|| \\ | |_   _|
    | |  | |__) || | | | | |  _| |  \\| | | |
    | |  |  _  / | | | |_| | |___| |\\  | | |
    |_|  |_| \\_\\___|____/|_____|_| \\_| |_|"""

_QUICK_START = """\
[bold #a78bfa]quick start[/]

  [dim]1.[/]  [bold]SESSIONS[/]  [dim]-->[/]  type a name  [dim]-->[/]  press [bold]Start[/]
  [dim]2.[/]  open a [bold]new terminal[/] and source the hook command shown
  [dim]3.[/]  work normally in that terminal
  [dim]4.[/]  return here  [dim]-->[/]  [bold]Process[/] to generate a runbook
  [dim]5.[/]  [bold]RUNBOOKS[/]  [dim]-->[/]  browse and preview your runbooks
  [dim]6.[/]  [bold]REPLAY[/]   [dim]-->[/]  select a runbook and stream output

[dim]press [bold]1-6[/] to switch panels  [bold]r[/] to refresh  [bold]q[/] to quit[/]"""


class HomePanel(Vertical):

    def compose(self) -> ComposeResult:
        yield Static(_LOGO, id="home-logo")
        yield Static("", id="home-stats")
        yield Rule()
        yield Static(_QUICK_START, id="home-guide")
        yield Rule()
        yield Static("[bold #a78bfa]recent runbooks[/]", id="recent-lbl")
        yield ListView(id="recent-list")

    def on_mount(self) -> None:
        self._refresh()
        self.set_interval(3.0, self._refresh)

    def _refresh(self) -> None:
        cfg      = _load_config()
        runbooks = _load_runbooks()
        tier     = cfg.get("ai_tier", "none")
        mem      = cfg.get("memory", {}).get("primary", "markdown")
        self.query_one("#home-stats", Static).update(
            f"  runbooks [bold #a78bfa]{len(runbooks)}[/]"
            f"   sessions [bold #a78bfa]{_count_sessions()}[/]"
            f"   tier [bold #a78bfa]{_tier_label(tier)}[/]"
            f"   memory [bold #a78bfa]{mem}[/]"
        )
        lv = self.query_one("#recent-list", ListView)
        lv.clear()
        for rb in runbooks[:6]:
            title = rb.get("title", "untitled")
            meta  = f"[dim]{_plural(rb.get('step_count', 0), 'step')}  {_rel_time(rb.get('created_at', ''))}[/]"
            lv.append(ListItem(Label(f"  [bold]{title}[/]  {meta}")))
        if not runbooks:
            lv.append(ListItem(Label("  [dim]no runbooks yet  --  complete the quick start above[/]")))

    @on(ListView.Selected, "#recent-list")
    def _open_viewer(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        rbs = _load_runbooks()
        if idx is not None and 0 <= idx < len(rbs):
            self.app.push_screen(ViewerScreen(rbs[idx]))


# ── SESSIONS panel ────────────────────────────────────────────────────────────

class SessionPanel(Vertical):

    def compose(self) -> ComposeResult:
        yield Static("[bold #a78bfa]active session[/]", classes="panel-heading")
        yield Static("", id="active-card")
        yield Rule()
        yield Static("[bold #a78bfa]start new session[/]", classes="panel-heading")
        yield Input(placeholder="session name  e.g. deploy-auth-service", id="sess-name")
        with Horizontal(id="sess-btns"):
            yield Button("Start",   id="btn-start",   variant="primary")
            yield Button("Process", id="btn-process", variant="default")
            yield Button("Stop",    id="btn-stop",    variant="error")
        yield Static("", id="hook-box")
        yield Rule()
        yield Static("[bold #a78bfa]recent sessions[/]", classes="panel-heading")
        yield ListView(id="sess-list")
        yield Static("", id="sess-log")

    def on_mount(self) -> None:
        self._refresh()
        self.set_interval(2.0, self._refresh)

    def _refresh(self) -> None:
        sess = _get_active_session()
        card = self.query_one("#active-card", Static)
        if sess:
            card.update(
                f"  [bold]{sess['title']}[/]  [dim]{sess['id'][:8]}[/]\n"
                f"  status [bold #a6e3a1]{sess['status']}[/]"
                f"   events [bold #a78bfa]{sess['event_count']}[/]"
                f"   started [dim]{_rel_time(sess['started_at'])}[/]"
            )
        else:
            card.update("  [dim]no active session[/]")
        lv = self.query_one("#sess-list", ListView)
        lv.clear()
        for s in _load_sessions():
            has = "[dim green]y[/]" if s["has_runbook"] else "[dim red]n[/]"
            lv.append(ListItem(Label(
                f"  [bold]{s['title'][:40]}[/]  "
                f"[dim]{s['status']}  runbook:{has}  {_rel_time(s['started_at'])}[/]"
            )))

    @on(Button.Pressed, "#btn-start")
    def _start(self) -> None:
        name = self.query_one("#sess-name", Input).value.strip()
        if not name:
            self.query_one("#hook-box", Static).update(
                "[bold red]  enter a session name first[/]"
            )
            return
        self._do_start(name)

    @on(Input.Submitted, "#sess-name")
    def _start_from_enter(self, event: Input.Submitted) -> None:
        name = event.value.strip()
        if name:
            self._do_start(name)

    @work(thread=True)
    def _do_start(self, name: str) -> None:
        hook_box = self.query_one("#hook-box", Static)
        self.app.call_from_thread(hook_box.update, "  [dim]starting...[/]")
        try:
            from trident.config import load_config, ensure_dirs
            from trident.capture.hooks import start_session
            cfg = load_config()
            ensure_dirs(cfg)
            session, hook_path = start_session(name, cfg)
            shell = session.shell_type or "bash"
            if shell == "powershell":
                cmd = f". {hook_path}"
            else:
                cmd = f"source {hook_path}"
            msg = (
                f"  [bold #a6e3a1]session created[/]  [dim]{session.id[:8]}[/]\n\n"
                f"  [bold]open a new terminal and run:[/]\n\n"
                f"  [bold #f9e2af]{cmd}[/]\n\n"
                f"  [dim]work normally, then return here and click Process[/]"
            )
            self.app.call_from_thread(hook_box.update, msg)
            self.app.call_from_thread(self._refresh)
        except Exception as e:
            self.app.call_from_thread(hook_box.update, f"  [bold red]error: {e}[/]")

    @on(Button.Pressed, "#btn-process")
    def _process(self) -> None:
        log = self.query_one("#sess-log", Static)
        log.update("  [dim]processing...[/]")
        self._do_process()

    @work(thread=True)
    def _do_process(self) -> None:
        log = self.query_one("#sess-log", Static)
        r = subprocess.run(
            [sys.executable, "-m", "trident.cli", "process"],
            capture_output=True, text=True, timeout=120,
        )
        out = (r.stdout + r.stderr).strip()
        color = "#a6e3a1" if r.returncode == 0 else "#f38ba8"
        lines = "\n".join(f"  {l}" for l in out.splitlines()[-20:])
        self.app.call_from_thread(log.update, f"[{color}]{lines}[/]")
        if r.returncode == 0:
            self.app.call_from_thread(self.post_message, SwitchPanel("runbooks"))

    @on(Button.Pressed, "#btn-stop")
    def _stop(self) -> None:
        try:
            from trident.capture.hooks import stop_session, get_active_session
            s = get_active_session()
            if s:
                stop_session(s.id)
                self.query_one("#hook-box", Static).update(
                    f"  [bold #a6e3a1]session {s.id[:8]} stopped[/]"
                )
            else:
                self.query_one("#hook-box", Static).update("  [dim]no active session to stop[/]")
            self._refresh()
        except Exception as e:
            self.query_one("#hook-box", Static).update(f"  [bold red]{e}[/]")


# ── RUNBOOKS panel ────────────────────────────────────────────────────────────

class RunbooksPanel(Horizontal):

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._all:      list[dict] = []
        self._filtered: list[dict] = []
        self._cache:    dict[str, str] = {}

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="rb-list-pane"):
            yield Input(placeholder="/ filter by name", id="rb-search")
            yield ListView(id="rb-list")
        with VerticalScroll(id="rb-preview-pane"):
            yield Markdown("", id="rb-preview")

    def on_mount(self) -> None:
        self._load()
        self.query_one("#rb-list", ListView).focus()

    def _load(self) -> None:
        self._all      = _load_runbooks()
        self._filtered = list(self._all)
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        lv = self.query_one("#rb-list", ListView)
        lv.clear()
        for rb in self._filtered:
            title = rb.get("title", "untitled")
            meta  = f"[dim]{_plural(rb.get('step_count', 0), 'step')}  {_rel_time(rb.get('created_at', ''))}[/]"
            lv.append(ListItem(Label(f"  [bold]{title}[/]  {meta}")))
        if not self._filtered:
            lv.append(ListItem(Label("  [dim]no matches[/]")))

    def _refresh_preview(self) -> None:
        lv  = self.query_one("#rb-list", ListView)
        idx = lv.index
        md  = self.query_one("#rb-preview", Markdown)
        if idx is None or not (0 <= idx < len(self._filtered)):
            md.update("_select a runbook to preview_")
            return
        path = self._filtered[idx].get("path", "")
        if path not in self._cache:
            content = _read_runbook(path)
            lines = content.split("\n")
            self._cache[path] = "\n".join(lines[:80]) + (
                "\n\n---\n_... press enter to read more_" if len(lines) > 80 else ""
            )
        md.update(self._cache[path])

    @on(ListView.Highlighted, "#rb-list")
    def _on_highlight(self, _: ListView.Highlighted) -> None:
        self._refresh_preview()

    @on(ListView.Selected, "#rb-list")
    def _on_select(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is not None and 0 <= idx < len(self._filtered):
            self.app.push_screen(ViewerScreen(self._filtered[idx]))

    @on(Input.Changed, "#rb-search")
    def _on_search(self, event: Input.Changed) -> None:
        q = event.value.lower().strip()
        self._filtered = [
            rb for rb in self._all
            if not q or q in rb.get("title", "").lower()
        ]
        self._rebuild_list()
        self._refresh_preview()

    @on(Input.Submitted, "#rb-search")
    def _focus_list(self, _: Input.Submitted) -> None:
        self.query_one("#rb-list", ListView).focus()

    def action_focus_search(self) -> None:
        self.query_one("#rb-search", Input).focus()

    def action_refresh(self) -> None:
        self._cache.clear()
        self._load()


# ── REPLAY panel ──────────────────────────────────────────────────────────────

class ReplayPanel(Vertical):

    def compose(self) -> ComposeResult:
        yield Static("[bold #a78bfa]select runbook[/]", classes="panel-heading")
        yield ListView(id="rp-list")
        yield Rule()
        with Horizontal(id="rp-btns"):
            yield Button("Run",  id="btn-run",  variant="primary")
            yield Button("Stop", id="btn-stop", variant="error")
        yield Static(
            "  [dim]enter or click Run to replay the selected runbook step by step[/]",
            id="rp-hint",
        )
        yield RichLog(id="rp-log", highlight=True, markup=True)

    def on_mount(self) -> None:
        self._load()

    def _load(self) -> None:
        lv = self.query_one("#rp-list", ListView)
        lv.clear()
        self._runbooks = _load_runbooks()
        for rb in self._runbooks:
            title = rb.get("title", "untitled")
            meta  = f"[dim]{_plural(rb.get('step_count', 0), 'step')}  {_rel_time(rb.get('created_at', ''))}[/]"
            lv.append(ListItem(Label(f"  [bold]{title}[/]  {meta}")))
        if not self._runbooks:
            lv.append(ListItem(Label("  [dim]no runbooks -- process a session first[/]")))

    @on(Button.Pressed, "#btn-run")
    def _run(self) -> None:
        lv  = self.query_one("#rp-list", ListView)
        idx = lv.index
        if idx is None or not (0 <= idx < len(self._runbooks)):
            return
        rb = self._runbooks[idx]
        log = self.query_one("#rp-log", RichLog)
        log.clear()
        log.write(f"[bold #a78bfa]replaying:[/] {rb.get('title', 'untitled')}")
        log.write("[dim]" + "-" * 60 + "[/]")
        self._stream_replay(rb.get("path", ""))

    @on(ListView.Selected, "#rp-list")
    def _run_from_enter(self, event: ListView.Selected) -> None:
        self._run()

    @work(thread=True)
    def _stream_replay(self, runbook_path: str) -> None:
        log = self.query_one("#rp-log", RichLog)
        proc = subprocess.Popen(
            [sys.executable, "-m", "trident.cli", "run", runbook_path],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        self._replay_proc = proc
        for line in proc.stdout:
            self.app.call_from_thread(log.write, line.rstrip())
        proc.wait()
        rc = proc.returncode
        color = "#a6e3a1" if rc == 0 else "#f38ba8"
        self.app.call_from_thread(log.write, f"[{color}]--- exit {rc} ---[/]")

    @on(Button.Pressed, "#btn-stop")
    def _stop(self) -> None:
        proc = getattr(self, "_replay_proc", None)
        if proc and proc.poll() is None:
            proc.terminate()
            self.query_one("#rp-log", RichLog).write("[yellow]--- terminated ---[/]")

    def action_refresh(self) -> None:
        self._load()


# ── SEARCH panel ──────────────────────────────────────────────────────────────

class SearchPanel(Vertical):

    def compose(self) -> ComposeResult:
        yield Static("[bold #a78bfa]search memory[/]", classes="panel-heading")
        yield Input(placeholder="query  e.g.  how did I deploy the auth service", id="q-input")
        yield Static("[dim]  press enter to search[/]", id="q-hint")
        yield ListView(id="q-results")

    def on_mount(self) -> None:
        self.query_one("#q-input", Input).focus()

    @on(Input.Submitted, "#q-input")
    def _search(self, event: Input.Submitted) -> None:
        q = event.value.strip()
        if not q:
            return
        self.query_one("#q-hint", Static).update("  [dim]searching...[/]")
        self._do_search(q)

    @work(thread=True)
    def _do_search(self, query: str) -> None:
        try:
            from trident.config import load_config
            from trident.tier import get_memory_store
            cfg   = load_config()
            store = get_memory_store(cfg)
            results = store.query(query, k=10)
        except Exception as e:
            results = []
            self.app.call_from_thread(
                self.query_one("#q-hint", Static).update,
                f"  [bold red]error: {e}[/]",
            )

        def _update(res: list) -> None:
            lv = self.query_one("#q-results", ListView)
            lv.clear()
            if not res:
                self.query_one("#q-hint", Static).update("  [dim]no results[/]")
                return
            self.query_one("#q-hint", Static).update(
                f"  [dim]{len(res)} result{'s' if len(res) != 1 else ''}[/]"
            )
            for r in res:
                title   = r.get("title", "untitled")
                snippet = (r.get("snippet", "")[:80] + "...").replace("\n", " ")
                lv.append(ListItem(
                    Label(f"  [bold]{title}[/]"),
                    Label(f"  [dim]{snippet}[/]"),
                ))

        self.app.call_from_thread(_update, results)

    @on(ListView.Selected, "#q-results")
    def _open(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        try:
            from trident.config import load_config
            from trident.tier import get_memory_store
            cfg     = load_config()
            store   = get_memory_store(cfg)
            q       = self.query_one("#q-input", Input).value
            results = store.query(q, k=10)
            if idx is not None and 0 <= idx < len(results):
                self.app.push_screen(ViewerScreen(results[idx]))
        except Exception:
            pass


# ── CONFIG panel ──────────────────────────────────────────────────────────────

class ConfigPanel(Vertical):

    def compose(self) -> ComposeResult:
        yield Static("[bold #a78bfa]configuration[/]", classes="panel-heading")
        yield Markdown("", id="cfg-md")
        yield Static(
            f"  [dim]config file: {_dir() / 'config.yaml'}[/]\n"
            "  [dim]edit with your text editor, then press [bold]r[/] to reload[/]",
            id="cfg-hint",
        )

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        cfg = _load_config()
        tier = cfg.get("ai_tier", "none")
        mem  = cfg.get("memory", {}).get("primary", "markdown")
        llm  = cfg.get("llm", {})
        cap  = cfg.get("capture", {})
        exe  = cfg.get("execution", {})

        lines = [
            "| key | value |",
            "| --- | ----- |",
            f"| ai_tier | `{tier}` |",
            f"| tier description | {_tier_label(tier)} |",
            f"| memory.primary | `{mem}` |",
            f"| llm.provider | `{llm.get('provider', 'none')}` |",
            f"| llm.model | `{llm.get('model', 'none')}` |",
            f"| capture.redaction | `{cap.get('redaction', 'strict')}` |",
            f"| execution.confirm_destructive | `{exe.get('confirm_destructive', True)}` |",
            f"| sessions dir | `{cap.get('sessions_dir', '~/.trident/sessions')}` |",
        ]
        self.query_one("#cfg-md", Markdown).update("\n".join(lines))

    def action_refresh(self) -> None:
        self._refresh()


# ── NAV sidebar ───────────────────────────────────────────────────────────────

_NAV_ITEMS = [
    ("HOME",     "home",     "1"),
    ("SESSIONS", "sessions", "2"),
    ("RUNBOOKS", "runbooks", "3"),
    ("REPLAY",   "replay",   "4"),
    ("SEARCH",   "search",   "5"),
    ("CONFIG",   "config",   "6"),
]


class NavPane(Vertical):

    def compose(self) -> ComposeResult:
        yield Static("[bold #7c3aed] TRIDENT[/]", id="nav-brand")
        yield Static("[dim] v0.1.0[/]", id="nav-ver")
        yield Rule()
        yield ListView(*[
            ListItem(Label(f"  {label}  [dim]{key}[/]"), id=f"nav-{panel}")
            for label, panel, key in _NAV_ITEMS
        ], id="nav-list")
        yield Rule()
        yield Static("", id="nav-session")

    def on_mount(self) -> None:
        self._tick()
        self.set_interval(2.0, self._tick)

    def _tick(self) -> None:
        sess = _get_active_session()
        s    = self.query_one("#nav-session", Static)
        if sess:
            s.update(
                f"  [bold #a6e3a1]capturing[/]\n"
                f"  [dim]{sess['title'][:16]}[/]\n"
                f"  [dim]{sess['event_count']} events[/]"
            )
        else:
            s.update("  [dim]no session[/]")

    @on(ListView.Selected, "#nav-list")
    def _on_nav(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is not None and 0 <= idx < len(_NAV_ITEMS):
            _, panel_id, _ = _NAV_ITEMS[idx]
            self.post_message(SwitchPanel(panel_id))


# ── main app ──────────────────────────────────────────────────────────────────

class TridentApp(App):

    TITLE     = "TRIDENT"
    SUB_TITLE = "no active session"

    BINDINGS = [
        Binding("1",      "switch_home",     "Home",     show=False),
        Binding("2",      "switch_sessions", "Sessions", show=False),
        Binding("3",      "switch_runbooks", "Runbooks", show=False),
        Binding("4",      "switch_replay",   "Replay",   show=False),
        Binding("5",      "switch_search",   "Search",   show=False),
        Binding("6",      "switch_config",   "Config",   show=False),
        Binding("r",      "refresh",         "Refresh"),
        Binding("q",      "quit",            "Quit"),
        Binding("ctrl+c", "quit",            "Quit",     show=False),
        Binding("?",      "show_bindings",   "Keys",     show=False),
    ]

    CSS = """
    /* ── base ───────────────────────────────────────────────────── */
    Screen        { background: #0a0a0f; color: #cdd6f4; }
    Header        { background: #12121a; color: #a78bfa; text-style: bold; }
    Footer        { background: #12121a; color: #585b70; }

    /* ── layout ──────────────────────────────────────────────────── */
    #app-body     { layout: horizontal; height: 1fr; }

    /* ── nav sidebar ─────────────────────────────────────────────── */
    #nav-pane     { width: 22; background: #12121a; border-right: solid #1e1e2e; }
    #nav-brand    { padding: 1 1 0 1; color: #7c3aed; text-style: bold; }
    #nav-ver      { padding: 0 1 0 1; }
    #nav-list     { background: #12121a; border: none; height: 1fr; }
    #nav-session  { padding: 1; color: #585b70; }

    NavPane ListView         { background: #12121a; }
    NavPane ListItem         { background: #12121a; padding: 0 1; }
    NavPane ListItem:hover   { background: #1e1e2e; }
    NavPane ListItem.--highlight { background: #1e1e2e; }
    NavPane ListItem.--highlight Label { color: #a78bfa; text-style: bold; }

    /* ── content area ────────────────────────────────────────────── */
    ContentSwitcher { width: 1fr; height: 1fr; }

    /* ── panels (shared) ─────────────────────────────────────────── */
    .panel-heading { padding: 1 2 0 2; color: #a78bfa; text-style: bold; }

    HomePanel, SessionPanel, ReplayPanel, SearchPanel, ConfigPanel {
        padding: 0 2;
        overflow-y: auto;
    }
    RunbooksPanel { padding: 0; }

    /* ── home ────────────────────────────────────────────────────── */
    #home-logo  { color: #7c3aed; padding: 1 0 0 0; text-style: bold; }
    #home-stats { background: #12121a; border: round #1e1e2e; padding: 1 2; margin: 1 0; }
    #home-guide { padding: 1 0; }
    #recent-lbl { margin: 1 0 0 0; }

    #recent-list { border: round #1e1e2e; background: #0a0a0f; height: auto; max-height: 12; }
    #recent-list:focus-within { border: round #7c3aed; }

    /* ── sessions ────────────────────────────────────────────────── */
    #active-card {
        background: #12121a; border: round #1e1e2e;
        padding: 1 2; margin: 1 0;
        transition: border 200ms;
    }
    #sess-btns   { margin: 1 0; height: auto; }
    #hook-box    {
        background: #0d0d1a; border: round #302b63;
        padding: 1 2; margin: 1 0; min-height: 4;
    }
    #sess-list   { border: round #1e1e2e; background: #0a0a0f; height: auto; max-height: 10; }
    #sess-log    { padding: 1 0; min-height: 3; }

    /* ── runbooks browser ────────────────────────────────────────── */
    #rb-list-pane   {
        width: 38%; min-width: 22;
        border-right: solid #1e1e2e;
    }
    #rb-preview-pane { width: 1fr; padding: 0 1; }
    #rb-list         { border: none; background: #0a0a0f; height: 1fr; }
    #rb-list:focus-within { border-left: solid #7c3aed; }
    #rb-search       {
        border: none; border-bottom: solid #1e1e2e;
        background: #12121a; color: #cdd6f4; height: 3;
    }
    #rb-search:focus { border-bottom: solid #7c3aed; }
    #rb-preview      { padding: 0 1; background: #0a0a0f; }

    /* ── replay ──────────────────────────────────────────────────── */
    #rp-list  {
        border: round #1e1e2e; background: #0a0a0f;
        height: auto; max-height: 10;
        margin: 1 0;
    }
    #rp-list:focus-within { border: round #7c3aed; }
    #rp-btns  { height: auto; margin: 0 0 1 0; }
    #rp-hint  { padding: 0 0 1 0; color: #585b70; }
    #rp-log   {
        border: round #1e1e2e; background: #080810;
        height: 1fr; min-height: 10;
        padding: 0 1;
    }

    /* ── search ──────────────────────────────────────────────────── */
    #q-input   {
        border: round #1e1e2e; background: #12121a;
        color: #cdd6f4; margin: 1 0;
    }
    #q-input:focus { border: round #7c3aed; }
    #q-hint    { color: #585b70; margin: 0 0 1 0; }
    #q-results { border: round #1e1e2e; background: #0a0a0f; height: 1fr; }
    #q-results:focus-within { border: round #7c3aed; }

    /* ── config ──────────────────────────────────────────────────── */
    #cfg-md   { padding: 1 0; }
    #cfg-hint { color: #585b70; padding: 1 0; }

    /* ── buttons ─────────────────────────────────────────────────── */
    Button          { margin: 0 1 0 0; min-width: 10; }
    Button.-primary { background: #7c3aed; color: #ffffff; border: none; }
    Button.-primary:hover { background: #6d28d9; }
    Button.-error   { background: #3b1c1c; color: #f38ba8; border: none; }
    Button.-error:hover   { background: #5c2626; }
    Button.-default { background: #1e1e2e; color: #cdd6f4; border: none; }
    Button.-default:hover { background: #2a2a3e; }

    /* ── inputs ──────────────────────────────────────────────────── */
    Input { background: #12121a; color: #cdd6f4; border: round #1e1e2e; }
    Input:focus { border: round #7c3aed; }

    /* ── lists (shared) ──────────────────────────────────────────── */
    ListView { scrollbar-color: #1e1e2e; scrollbar-color-active: #7c3aed; }
    ListItem { background: #0a0a0f; padding: 0 1; }
    ListItem:hover { background: #12121a; }
    ListItem.--highlight { background: #12121a; }
    ListItem.--highlight Label { color: #a78bfa; }

    /* ── markdown ────────────────────────────────────────────────── */
    Markdown { background: #0a0a0f; color: #cdd6f4; }

    /* ── scrollbars ──────────────────────────────────────────────── */
    VerticalScroll { scrollbar-color: #1e1e2e; scrollbar-color-active: #7c3aed; }

    /* ── rule ────────────────────────────────────────────────────── */
    Rule { color: #1e1e2e; margin: 1 0; }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="app-body"):
            yield NavPane(id="nav-pane")
            with ContentSwitcher(initial="home", id="content"):
                yield HomePanel(id="home")
                yield SessionPanel(id="sessions")
                yield RunbooksPanel(id="runbooks")
                yield ReplayPanel(id="replay")
                yield SearchPanel(id="search")
                yield ConfigPanel(id="config")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(2.0, self._tick_header)

    def _tick_header(self) -> None:
        sess = _get_active_session()
        self.sub_title = (
            f"session: {sess['title']}  {sess['event_count']} events"
            if sess else "no active session"
        )

    def _switch_to(self, panel_id: str) -> None:
        self.query_one(ContentSwitcher).current = panel_id
        nav = self.query_one("#nav-list", ListView)
        ids = [p for _, p, _ in _NAV_ITEMS]
        if panel_id in ids:
            nav.index = ids.index(panel_id)

    def on_switch_panel(self, msg: SwitchPanel) -> None:
        self._switch_to(msg.panel_id)

    # ── panel switch actions ──────────────────────────────────────

    def action_switch_home(self)     -> None: self._switch_to("home")
    def action_switch_sessions(self) -> None: self._switch_to("sessions")
    def action_switch_runbooks(self) -> None: self._switch_to("runbooks")
    def action_switch_replay(self)   -> None: self._switch_to("replay")
    def action_switch_search(self)   -> None: self._switch_to("search")
    def action_switch_config(self)   -> None: self._switch_to("config")

    def action_refresh(self) -> None:
        current = self.query_one(ContentSwitcher).current
        panel   = self.query_one(f"#{current}")
        if hasattr(panel, "action_refresh"):
            panel.action_refresh()
        elif hasattr(panel, "_refresh"):
            panel._refresh()
        elif hasattr(panel, "_load"):
            panel._load()

    def action_show_bindings(self) -> None:
        self.notify(
            "1-6 switch panels  |  r refresh  |  / search  |  j/k navigate  |  enter open  |  esc back  |  q quit",
            title="keyboard shortcuts",
            timeout=8,
        )


def launch() -> None:
    TridentApp().run()


if __name__ == "__main__":
    launch()
