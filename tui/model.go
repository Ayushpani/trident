package main

import (
	"github.com/charmbracelet/bubbles/list"
	"github.com/charmbracelet/bubbles/spinner"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/glamour"
	"github.com/charmbracelet/lipgloss"
)

// ── View states ───────────────────────────────────────────────────────────────

type viewState int

const (
	viewLoading viewState = iota
	viewHome
	viewBrowser
	viewViewer
)

// ── List item ─────────────────────────────────────────────────────────────────

type runbookItem struct{ meta RunbookMeta }

func (r runbookItem) Title() string { return r.meta.Title }
func (r runbookItem) Description() string {
	return plural(r.meta.StepCount, "step") + "  ·  " + relTime(r.meta.CreatedAt)
}
func (r runbookItem) FilterValue() string { return r.meta.Title }

// ── Messages ──────────────────────────────────────────────────────────────────

type dataReadyMsg struct {
	config   Config
	runbooks []RunbookMeta
	sessions int
}

type contentReadyMsg struct {
	title   string
	content string
}

// ── Root model ────────────────────────────────────────────────────────────────

type model struct {
	view   viewState
	width  int
	height int

	// data
	config   Config
	runbooks []RunbookMeta
	sessions int

	// loading spinner
	spinner spinner.Model

	// browser: list + cached previews
	list         list.Model
	previewIdx   int
	previewCache map[string]string // path → raw content

	// viewer
	viewport    viewport.Model
	viewerTitle string
}

func initial() model {
	sp := spinner.New()
	sp.Spinner = spinner.Dot
	sp.Style = lipgloss.NewStyle().Foreground(clrViolet)
	return model{
		view:         viewLoading,
		spinner:      sp,
		previewIdx:   -1,
		previewCache: make(map[string]string),
	}
}

// ── Init ──────────────────────────────────────────────────────────────────────

func (m model) Init() tea.Cmd {
	return tea.Batch(m.spinner.Tick, func() tea.Msg {
		cfg := loadConfig()
		rb := loadRunbooks()
		n := countSessions()
		return dataReadyMsg{cfg, rb, n}
	})
}

// ── Update ────────────────────────────────────────────────────────────────────

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {

	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		if m.view == viewBrowser {
			m.list.SetSize(m.listWidth(), m.bodyHeight())
		}
		if m.view == viewViewer {
			m.viewport.Width = m.width - 4
			m.viewport.Height = m.bodyHeight()
		}
		return m, nil

	case tea.KeyMsg:
		return m.handleKey(msg)

	case dataReadyMsg:
		m.config = msg.config
		m.runbooks = msg.runbooks
		m.sessions = msg.sessions
		m.buildList()
		m.view = viewHome
		return m, nil

	case contentReadyMsg:
		m.viewerTitle = msg.title
		rendered := m.renderMarkdown(msg.content)
		m.viewport = viewport.New(m.width-4, m.bodyHeight())
		m.viewport.SetContent(rendered)
		m.view = viewViewer
		return m, nil

	case spinner.TickMsg:
		var cmd tea.Cmd
		m.spinner, cmd = m.spinner.Update(msg)
		return m, cmd
	}

	// Delegate component updates for non-key messages
	switch m.view {
	case viewBrowser:
		newList, cmd := m.list.Update(msg)
		m.list = newList
		return m, cmd
	case viewViewer:
		vp, cmd := m.viewport.Update(msg)
		m.viewport = vp
		return m, cmd
	}
	return m, nil
}

func (m model) handleKey(msg tea.KeyMsg) (tea.Model, tea.Cmd) {
	k := msg.String()

	if k == "ctrl+c" {
		return m, tea.Quit
	}

	switch m.view {
	// ── Home ───────────────────────────────────────────────────────────────
	case viewHome:
		switch k {
		case "q":
			return m, tea.Quit
		case "r", "enter", "right", "l":
			m.view = viewBrowser
		}

	// ── Browser ────────────────────────────────────────────────────────────
	case viewBrowser:
		switch k {
		case "q", "esc", "left", "h":
			m.view = viewHome
			return m, nil
		case "enter", "right", "l":
			if item, ok := m.list.SelectedItem().(runbookItem); ok {
				return m, m.openRunbook(item.meta)
			}
			return m, nil
		}
		// Forward all other keys (j/k, /, filter, etc.) to list
		newList, cmd := m.list.Update(msg)
		m.list = newList
		m.warmPreview()
		return m, cmd

	// ── Viewer ─────────────────────────────────────────────────────────────
	case viewViewer:
		switch k {
		case "q", "esc", "left", "h":
			m.view = viewBrowser
			return m, nil
		case "g":
			m.viewport.GotoTop()
			return m, nil
		case "G":
			m.viewport.GotoBottom()
			return m, nil
		}
		vp, cmd := m.viewport.Update(msg)
		m.viewport = vp
		return m, cmd
	}

	return m, nil
}

// ── Helpers ───────────────────────────────────────────────────────────────────

func (m model) openRunbook(meta RunbookMeta) tea.Cmd {
	return func() tea.Msg {
		content := readRunbookFile(meta.Path)
		return contentReadyMsg{title: meta.Title, content: content}
	}
}

func (m *model) buildList() {
	items := make([]list.Item, len(m.runbooks))
	for i, rb := range m.runbooks {
		items[i] = runbookItem{meta: rb}
	}

	d := list.NewDefaultDelegate()
	d.Styles.SelectedTitle = d.Styles.SelectedTitle.
		Foreground(clrViolet).
		BorderForeground(clrPurple)
	d.Styles.SelectedDesc = d.Styles.SelectedDesc.
		Foreground(clrSubtext).
		BorderForeground(clrPurple)
	d.Styles.NormalTitle = d.Styles.NormalTitle.
		Foreground(clrText)
	d.Styles.NormalDesc = d.Styles.NormalDesc.
		Foreground(clrMuted)

	l := list.New(items, d, m.listWidth(), m.bodyHeight())
	l.Title = "  Runbooks"
	l.Styles.Title = lipgloss.NewStyle().
		Background(clrPurple).
		Foreground(clrWhite).
		Bold(true).
		Padding(0, 1)
	l.Styles.TitleBar = lipgloss.NewStyle().
		Background(clrPanel)
	l.SetShowStatusBar(true)
	l.SetFilteringEnabled(true)
	l.SetShowHelp(false)
	m.list = l
	m.warmPreview()
}

// warmPreview loads the selected runbook's raw content into cache.
func (m *model) warmPreview() {
	item, ok := m.list.SelectedItem().(runbookItem)
	if !ok {
		return
	}
	path := item.meta.Path
	if _, cached := m.previewCache[path]; !cached {
		m.previewCache[path] = readRunbookFile(path)
	}
}

func (m model) currentPreview() (RunbookMeta, string, bool) {
	item, ok := m.list.SelectedItem().(runbookItem)
	if !ok {
		return RunbookMeta{}, "", false
	}
	content, _ := m.previewCache[item.meta.Path]
	return item.meta, content, true
}

func (m model) renderMarkdown(content string) string {
	r, err := glamour.NewTermRenderer(
		glamour.WithStylePath("dark"),
		glamour.WithWordWrap(m.width-6),
	)
	if err != nil {
		return content
	}
	out, err := r.Render(content)
	if err != nil {
		return content
	}
	return out
}

// ── Layout ────────────────────────────────────────────────────────────────────

// bodyHeight is usable vertical space (exclude header + status bar).
func (m model) bodyHeight() int {
	h := m.height - 3 // status bar (1) + top margin (2)
	if h < 5 {
		return 5
	}
	return h
}

// listWidth is 40% of the terminal.
func (m model) listWidth() int {
	w := m.width * 2 / 5
	if w < 30 {
		return 30
	}
	return w
}

// previewWidth is the remaining space.
func (m model) previewWidth() int {
	return m.width - m.listWidth() - 3
}
