"""
trident.ui.tui — Full-screen Textual TUI.

Three screens, keyboard-driven, works at any terminal size:
  DashboardScreen   home — stats card + recent runbooks
  BrowserScreen     40/60 split list + live markdown preview
  ViewerScreen      full-screen scrollable markdown viewer

Launch:  trident ui
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    Static,
)


# ── Data helpers ──────────────────────────────────────────────────────────────

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


def _count_sessions() -> int:
    d = _dir() / "sessions"
    if not d.exists():
        return 0
    return sum(1 for f in d.iterdir() if f.suffix == ".ndjson")


def _read_runbook(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        return "_Could not read file._"


def _rel_time(ts: str) -> str:
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        secs = (datetime.now(timezone.utc) - dt).total_seconds()
        if secs < 60:
            return "just now"
        if secs < 3_600:
            return f"{int(secs / 60)}m ago"
        if secs < 86_400:
            return f"{int(secs / 3_600)}h ago"
        if secs < 604_800:
            return f"{int(secs / 86_400)}d ago"
        return dt.strftime("%b %d")
    except Exception:
        return "—"


def _tier_label(tier: str) -> str:
    return {
        "none":   "Tier 0 — deterministic",
        "local":  "Tier 1 — Ollama",
        "byok":   "Tier 2 — BYOK",
        "smaran": "Tier 3 — Smaran",
    }.get(tier, tier)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _preview_lines(content: str, max_lines: int = 60) -> str:
    """Truncate content for the browser preview pane."""
    lines = content.split("\n")
    if len(lines) <= max_lines:
        return content
    return "\n".join(lines[:max_lines]) + "\n\n---\n_… scroll down to read more (enter to open)_"


# ── Screen 1: Dashboard ───────────────────────────────────────────────────────

class DashboardScreen(Screen):
    """Home screen: stat card + recent runbooks list."""

    BINDINGS = [
        Binding("r", "browse",   "Runbooks", priority=True),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._config   = _load_config()
        self._runbooks = _load_runbooks()
        self._sessions = _count_sessions()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(id="dash-scroll"):
            yield Static(self._render_logo(),   id="logo")
            yield Static(self._render_stats(),  id="stats-card")
            yield Static(
                "[bold #a78bfa]  Recent Runbooks[/]",
                id="recent-label",
            )
            yield ListView(*self._recent_items(), id="recent-list")
        yield Footer()

    # ── Rendering helpers ─────────────────────────────────────────────────

    def _render_logo(self) -> str:
        return (
            "\n"
            "  [bold #a78bfa]⚡ TRIDENT[/]  [dim]v0.1.0[/]\n"
            "  [dim italic]Terminal memory that works.[/]\n"
        )

    def _render_stats(self) -> str:
        cfg  = self._config
        tier = cfg.get("ai_tier", "none")
        mem  = cfg.get("memory", {}).get("primary", "markdown")
        tier_color = {
            "none":   "dim",
            "local":  "cyan",
            "byok":   "#7c3aed",
            "smaran": "dark_orange",
        }.get(tier, "dim")
        return (
            f"  [dim]📋  Runbooks[/]  [bold #a78bfa]{len(self._runbooks)}[/]"
            f"        [dim]🎯  Sessions[/]  [bold #a78bfa]{self._sessions}[/]\n\n"
            f"  [dim]🗄   Memory[/]   [bold #a78bfa]{mem}[/]"
            f"      [dim]✨  AI tier[/]  [{tier_color} bold]{_tier_label(tier)}[/]"
        )

    def _recent_items(self) -> list[ListItem]:
        items = []
        for rb in self._runbooks[:8]:
            title = rb.get("title", "untitled")
            meta  = f"[dim]{_plural(rb.get('step_count', 0), 'step')}  ·  {_rel_time(rb.get('created_at', ''))}[/]"
            items.append(ListItem(Label(f"  [bold]{title}[/]"), Label(f"  {meta}")))
        if not items:
            items.append(ListItem(Label(
                "  [dim]No runbooks yet — run [bold]trident process[/] to create one.[/]"
            )))
        return items

    # ── Actions ───────────────────────────────────────────────────────────

    def action_browse(self) -> None:
        self.app.push_screen(BrowserScreen())

    @on(ListView.Selected, "#recent-list")
    def on_recent_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is not None and 0 <= idx < len(self._runbooks):
            self.app.push_screen(ViewerScreen(self._runbooks[idx]))


# ── Screen 2: Browser ─────────────────────────────────────────────────────────

class BrowserScreen(Screen):
    """40/60 split: runbook list on left, live markdown preview on right."""

    BINDINGS = [
        Binding("escape",     "back",         "Back"),
        Binding("q",          "back",         "Back",   show=False),
        Binding("enter",      "open_viewer",  "Open"),
        Binding("/",          "focus_search", "Search"),
        Binding("j",          "cursor_down",  "Down",   show=False),
        Binding("k",          "cursor_up",    "Up",     show=False),
        Binding("ctrl+j",     "cursor_down",  "Down",   show=False),
        Binding("ctrl+k",     "cursor_up",    "Up",     show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._all:      list[dict] = _load_runbooks()
        self._filtered: list[dict] = list(self._all)
        self._cache:    dict[str, str] = {}   # path → full content

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="browser"):
            with VerticalScroll(id="list-pane"):
                yield Input(placeholder="  🔍  filter runbooks…", id="search")
                yield ListView(*self._make_items(self._all), id="run-list")
            with VerticalScroll(id="preview-pane"):
                yield Markdown("", id="preview-md")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#run-list", ListView).focus()
        self._refresh_preview()

    # ── List helpers ──────────────────────────────────────────────────────

    def _make_items(self, runbooks: list[dict]) -> list[ListItem]:
        items = []
        for rb in runbooks:
            title = rb.get("title", "untitled")
            meta  = f"[dim]{_plural(rb.get('step_count', 0), 'step')}  ·  {_rel_time(rb.get('created_at', ''))}[/]"
            items.append(ListItem(Label(f"[bold]{title}[/]"), Label(meta)))
        if not items:
            items.append(ListItem(Label("[dim]No runbooks match.[/]")))
        return items

    def _refresh_preview(self) -> None:
        lv  = self.query_one("#run-list", ListView)
        idx = lv.index
        md  = self.query_one("#preview-md", Markdown)
        if idx is None or not (0 <= idx < len(self._filtered)):
            md.update("_Select a runbook to preview._")
            return
        rb   = self._filtered[idx]
        path = rb.get("path", "")
        if path not in self._cache:
            self._cache[path] = _read_runbook(path)
        md.update(_preview_lines(self._cache[path]))

    # ── Event handlers ────────────────────────────────────────────────────

    @on(ListView.Highlighted, "#run-list")
    def on_highlighted(self, event: ListView.Highlighted) -> None:
        self._refresh_preview()

    @on(ListView.Selected, "#run-list")
    def on_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is not None and 0 <= idx < len(self._filtered):
            self.app.push_screen(ViewerScreen(self._filtered[idx]))

    @on(Input.Changed, "#search")
    def on_search_changed(self, event: Input.Changed) -> None:
        q = event.value.lower().strip()
        self._filtered = [
            rb for rb in self._all
            if not q or q in rb.get("title", "").lower()
        ]
        lv = self.query_one("#run-list", ListView)
        lv.clear()
        for item in self._make_items(self._filtered):
            lv.append(item)
        self._refresh_preview()

    @on(Input.Submitted, "#search")
    def on_search_submitted(self, _: Input.Submitted) -> None:
        # Move focus back to list after pressing Enter in search
        self.query_one("#run-list", ListView).focus()

    # ── Actions ───────────────────────────────────────────────────────────

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_open_viewer(self) -> None:
        lv  = self.query_one("#run-list", ListView)
        idx = lv.index
        if idx is not None and 0 <= idx < len(self._filtered):
            self.app.push_screen(ViewerScreen(self._filtered[idx]))

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_cursor_down(self) -> None:
        self.query_one("#run-list", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#run-list", ListView).action_cursor_up()


# ── Screen 3: Viewer ──────────────────────────────────────────────────────────

class ViewerScreen(Screen):
    """Full-screen scrollable markdown viewer."""

    BINDINGS = [
        Binding("escape",  "back",   "Back"),
        Binding("q",       "back",   "Back",   show=False),
        Binding("h",       "back",   "Back",   show=False),
        Binding("g",       "top",    "Top"),
        Binding("G",       "bottom", "Bottom"),
        Binding("ctrl+d",  "page_down",  "Page ↓", show=False),
        Binding("ctrl+u",  "page_up",    "Page ↑", show=False),
    ]

    def __init__(self, runbook: dict) -> None:
        super().__init__()
        self._meta    = runbook
        self._content = _read_runbook(runbook.get("path", ""))

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(id="viewer-scroll"):
            yield Markdown(self._content, id="viewer-md")
        yield Footer()

    def on_mount(self) -> None:
        self.app.sub_title = self._meta.get("title", "viewer")

    def on_unmount(self) -> None:
        self.app.sub_title = "terminal memory"

    # ── Actions ───────────────────────────────────────────────────────────

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_top(self) -> None:
        self.query_one("#viewer-scroll", VerticalScroll).scroll_home(animate=True)

    def action_bottom(self) -> None:
        self.query_one("#viewer-scroll", VerticalScroll).scroll_end(animate=True)

    def action_page_down(self) -> None:
        self.query_one("#viewer-scroll", VerticalScroll).action_page_down()

    def action_page_up(self) -> None:
        self.query_one("#viewer-scroll", VerticalScroll).action_page_up()


# ── App ───────────────────────────────────────────────────────────────────────

class TridentApp(App):
    """⚡ Trident — interactive terminal dashboard."""

    TITLE     = "⚡  TRIDENT"
    SUB_TITLE = "terminal memory"

    CSS = """
    /* ── Base ────────────────────────────────────────────────────────── */

    Screen {
        background: #0f0c29;
        color: #e0e7ff;
    }

    Header {
        background: #1e1b4b;
        color: #a78bfa;
        text-style: bold;
    }

    Footer {
        background: #1e1b4b;
        color: #6b7280;
    }

    /* ── Dashboard ───────────────────────────────────────────────────── */

    #dash-scroll {
        width: 100%;
        height: 1fr;
        padding: 0 2;
    }

    #logo {
        padding: 1 0 0 0;
    }

    #stats-card {
        background: #1e1b4b;
        border: round #302b63;
        padding: 1 2;
        margin: 1 0;
    }

    #recent-label {
        margin: 1 0 0 0;
    }

    #recent-list {
        border: round #302b63;
        background: #0f0c29;
        height: auto;
        max-height: 18;
        margin: 0 0 1 0;
    }

    #recent-list:focus-within {
        border: round #7c3aed;
    }

    /* ── Browser layout ──────────────────────────────────────────────── */

    #browser {
        width: 100%;
        height: 1fr;
    }

    #list-pane {
        width: 40%;
        min-width: 24;
        max-width: 64;
        border: round #302b63;
        margin: 0 1 0 0;
        padding: 0;
    }

    #list-pane:focus-within {
        border: round #7c3aed;
    }

    #search {
        border: none;
        border-bottom: solid #302b63;
        background: #1e1b4b;
        color: #e0e7ff;
        padding: 0 1;
        margin: 0;
        height: 3;
    }

    #search:focus {
        border-bottom: solid #7c3aed;
    }

    #run-list {
        background: #0f0c29;
        border: none;
        height: 1fr;
    }

    #preview-pane {
        width: 1fr;
        border: round #302b63;
        padding: 0 1;
    }

    #preview-pane:focus-within {
        border: round #302b63;
    }

    #preview-md {
        padding: 0 1;
    }

    /* ── Viewer ──────────────────────────────────────────────────────── */

    #viewer-scroll {
        width: 100%;
        height: 1fr;
    }

    #viewer-md {
        padding: 1 3;
        max-width: 100%;
    }

    /* ── ListView items ──────────────────────────────────────────────── */

    ListView {
        background: #0f0c29;
        scrollbar-color: #302b63;
        scrollbar-color-active: #7c3aed;
        scrollbar-color-hover: #a78bfa;
    }

    ListItem {
        background: #0f0c29;
        padding: 0 1;
    }

    ListItem:hover {
        background: #1a1830;
    }

    ListItem.--highlight {
        background: #1e1b4b;
    }

    ListItem.--highlight Label {
        color: #a78bfa;
    }

    /* ── Input ───────────────────────────────────────────────────────── */

    Input {
        background: #1e1b4b;
        color: #e0e7ff;
        border: round #302b63;
    }

    Input:focus {
        border: round #7c3aed;
        color: #ffffff;
    }

    /* ── Scrollbars ──────────────────────────────────────────────────── */

    VerticalScroll {
        scrollbar-color: #302b63;
        scrollbar-color-active: #7c3aed;
        scrollbar-color-hover: #a78bfa;
    }

    /* ── Markdown ─────────────────────────────────────────────────────── */

    Markdown {
        background: #0f0c29;
        color: #e0e7ff;
    }
    """

    def on_mount(self) -> None:
        self.push_screen(DashboardScreen())


# ── Entry point ───────────────────────────────────────────────────────────────

def launch() -> None:
    """Called by `trident ui`."""
    TridentApp().run()


if __name__ == "__main__":
    launch()
