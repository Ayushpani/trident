package main

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/lipgloss"
)

// ── Top-level dispatch ────────────────────────────────────────────────────────

func (m model) View() string {
	if m.width == 0 {
		return ""
	}
	switch m.view {
	case viewLoading:
		return m.renderLoading()
	case viewHome:
		return m.renderHome()
	case viewBrowser:
		return m.renderBrowser()
	case viewViewer:
		return m.renderViewer()
	}
	return ""
}

// ── Loading screen ────────────────────────────────────────────────────────────

func (m model) renderLoading() string {
	content := lipgloss.JoinVertical(lipgloss.Center,
		logoStyle.Render("⚡  TRIDENT"),
		"",
		dimStyle.Render(m.spinner.View()+"  loading your runbooks..."),
	)
	return lipgloss.Place(m.width, m.height, lipgloss.Center, lipgloss.Center, content)
}

// ── Home dashboard ────────────────────────────────────────────────────────────

func (m model) renderHome() string {
	var b strings.Builder
	b.WriteString("\n")

	// ── Header ───────────────────────────────────────────────────────────
	mark := logoMark.Render("⚡")
	name := logoStyle.Render(" TRIDENT")
	ver := versionStyle.Render("  v0.1.0")
	b.WriteString(mark + name + ver + "\n")
	b.WriteString(taglineStyle.Render("  Terminal memory that works.") + "\n\n")

	// ── Stats card ───────────────────────────────────────────────────────
	tier := m.config.AITier
	badge := tierBadge(tier)

	cardLines := []string{
		statLabelStyle.Render("📋  Runbooks") + statValueStyle.Render(fmt.Sprintf("%d", len(m.runbooks))),
		statLabelStyle.Render("🎯  Sessions") + statValueStyle.Render(fmt.Sprintf("%d", m.sessions)),
		statLabelStyle.Render("🗄   Memory") + statValueStyle.Render(m.config.Memory.Primary),
		statLabelStyle.Render("✨  AI tier") + statValueStyle.Render(tier) + "   " + badge,
	}
	card := statCardStyle.
		Width(m.width - 8).
		Render(strings.Join(cardLines, "\n"))
	b.WriteString(card + "\n\n")

	// ── Recent runbooks ──────────────────────────────────────────────────
	b.WriteString(sectionStyle.Render("  Recent runbooks") + "\n")

	if len(m.runbooks) == 0 {
		b.WriteString(dimStyle.Render("  No runbooks yet.  Run 'trident process' to create one.") + "\n")
	} else {
		limit := 6
		if limit > len(m.runbooks) {
			limit = len(m.runbooks)
		}
		for i := 0; i < limit; i++ {
			rb := m.runbooks[i]
			if i == 0 {
				arrow := arrowStyle.Render("▸")
				title := selectedRowStyle.Width(32).Render(rb.Title)
				steps := dimStyle.Width(12).Render(plural(rb.StepCount, "step"))
				when := dimStyle.Render(relTime(rb.CreatedAt))
				b.WriteString("  " + arrow + " " + title + steps + when + "\n")
			} else {
				title := normalRowStyle.Width(34).Render("  " + rb.Title)
				steps := dimStyle.Width(12).Render(plural(rb.StepCount, "step"))
				when := dimStyle.Render(relTime(rb.CreatedAt))
				b.WriteString("  " + title + steps + when + "\n")
			}
		}
	}
	b.WriteString("\n")

	// ── Status bar ───────────────────────────────────────────────────────
	b.WriteString(m.helpBar([][]string{
		{"enter / r", "browse runbooks"},
		{"q", "quit"},
		{"ctrl+c", "exit"},
	}))

	return b.String()
}

// ── Browser: list + live preview ─────────────────────────────────────────────

func (m model) renderBrowser() string {
	listPane := paneStyle.Render(m.list.View())

	// Preview pane
	pw := m.previewWidth()
	ph := m.bodyHeight()

	var previewContent string
	meta, rawContent, ok := m.currentPreview()
	if !ok {
		previewContent = dimStyle.Render("Select a runbook to preview")
	} else {
		// Header
		title := previewTitleStyle.Render(meta.Title)
		sid := previewMetaStyle.Render(
			shortID(meta.SessionID) + "  ·  " +
				plural(meta.StepCount, "step") + "  ·  " +
				relTime(meta.CreatedAt),
		)
		divider := dimStyle.Render(strings.Repeat("─", pw-4))

		// Body: raw lines, clamped to fit the pane
		rawLines := strings.Split(rawContent, "\n")
		maxBody := ph - 6
		if maxBody < 1 {
			maxBody = 1
		}
		if len(rawLines) > maxBody {
			rawLines = rawLines[:maxBody]
			rawLines = append(rawLines, dimStyle.Render("  ··· (enter to view full runbook)"))
		}
		body := previewBodyStyle.Render(strings.Join(rawLines, "\n"))

		previewContent = lipgloss.JoinVertical(lipgloss.Left,
			title, sid, divider, body,
		)
	}

	preview := previewStyle.
		Width(pw).
		Height(ph).
		Render(previewContent)

	main := lipgloss.JoinHorizontal(lipgloss.Top, listPane, " ", preview)

	help := m.helpBar([][]string{
		{"↑↓ / jk", "navigate"},
		{"/", "filter"},
		{"enter", "open"},
		{"esc / h", "back"},
		{"q", "quit"},
	})

	return lipgloss.JoinVertical(lipgloss.Left, main, help)
}

// ── Full-screen viewer ───────────────────────────────────────────────────────

func (m model) renderViewer() string {
	// ── Title bar ────────────────────────────────────────────────────────
	pct := int(m.viewport.ScrollPercent() * 100)
	bar := renderScrollBar(pct, 16)

	scrollInfo := viewerScrollStyle.Render(
		fmt.Sprintf("%d%%  %s", pct, bar),
	)
	scrollWidth := lipgloss.Width(scrollInfo)
	titleWidth := m.width - scrollWidth
	titleBar := lipgloss.JoinHorizontal(lipgloss.Top,
		viewerTitleBarStyle.Width(titleWidth).Render("⚡  "+m.viewerTitle),
		scrollInfo,
	)

	sep := separatorStyle.Render(strings.Repeat("─", m.width))

	help := m.helpBar([][]string{
		{"↑↓ / jk", "scroll"},
		{"g / G", "top / bottom"},
		{"esc / h", "back"},
		{"q", "quit"},
	})

	return lipgloss.JoinVertical(lipgloss.Left,
		titleBar,
		sep,
		m.viewport.View(),
		sep,
		help,
	)
}

// ── Shared components ─────────────────────────────────────────────────────────

// helpBar renders the bottom key-hint bar.
func (m model) helpBar(hints [][]string) string {
	var parts []string
	for _, h := range hints {
		k := keyStyle.Render(h[0])
		d := keyDescStyle.Render(h[1])
		parts = append(parts, k+d)
	}
	return statusBarStyle.Width(m.width).Render("  " + strings.Join(parts, "  "))
}

// renderScrollBar renders a simple Unicode progress bar.
func renderScrollBar(pct, width int) string {
	filled := width * pct / 100
	if filled > width {
		filled = width
	}
	bar := strings.Repeat("█", filled) + strings.Repeat("░", width-filled)
	return progressStyle.Render(bar)
}
