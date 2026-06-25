package main

import "github.com/charmbracelet/lipgloss"

// ── Palette ──────────────────────────────────────────────────────────────────

var (
	clrPurple    = lipgloss.Color("#7c3aed")
	clrViolet    = lipgloss.Color("#a78bfa")
	clrIndigo    = lipgloss.Color("#4f46e5")
	clrDark      = lipgloss.Color("#0f0c29")
	clrPanel     = lipgloss.Color("#1e1b4b")
	clrSurface   = lipgloss.Color("#24243e")
	clrBorder    = lipgloss.Color("#302b63")
	clrText      = lipgloss.Color("#e0e7ff")
	clrMuted     = lipgloss.Color("#6b7280")
	clrSubtext   = lipgloss.Color("#9ca3af")
	clrGreen     = lipgloss.Color("#22c55e")
	clrOrange    = lipgloss.Color("#f97316")
	clrCyan      = lipgloss.Color("#0891b2")
	clrWhite     = lipgloss.Color("#ffffff")
)

// ── Logo ─────────────────────────────────────────────────────────────────────

var (
	logoStyle = lipgloss.NewStyle().
			Foreground(clrViolet).
			Bold(true)

	logoMark = lipgloss.NewStyle().
			Foreground(clrPurple).
			Bold(true)

	versionStyle = lipgloss.NewStyle().
			Foreground(clrMuted)

	taglineStyle = lipgloss.NewStyle().
			Foreground(clrSubtext).
			Italic(true)
)

// ── Stat card ────────────────────────────────────────────────────────────────

var (
	statCardStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(clrBorder).
			Background(clrPanel).
			Padding(1, 3)

	statLabelStyle = lipgloss.NewStyle().
			Foreground(clrMuted).
			Width(20)

	statValueStyle = lipgloss.NewStyle().
			Foreground(clrViolet).
			Bold(true)
)

// ── Home screen items ────────────────────────────────────────────────────────

var (
	sectionStyle = lipgloss.NewStyle().
			Foreground(clrViolet).
			Bold(true)

	selectedRowStyle = lipgloss.NewStyle().
				Foreground(clrViolet).
				Bold(true)

	normalRowStyle = lipgloss.NewStyle().
			Foreground(clrText)

	dimStyle = lipgloss.NewStyle().
			Foreground(clrMuted)

	arrowStyle = lipgloss.NewStyle().
			Foreground(clrPurple).
			Bold(true)
)

// ── Status / help bar ────────────────────────────────────────────────────────

var (
	statusBarStyle = lipgloss.NewStyle().
			Background(clrPanel).
			Foreground(clrMuted).
			Padding(0, 0)

	keyStyle = lipgloss.NewStyle().
			Background(clrPurple).
			Foreground(clrWhite).
			Bold(true).
			Padding(0, 1)

	keyDescStyle = lipgloss.NewStyle().
			Foreground(clrMuted).
			Padding(0, 1)
)

// ── Browser panes ────────────────────────────────────────────────────────────

var (
	paneStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(clrBorder)

	activePaneStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(clrPurple)

	previewStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			BorderForeground(clrBorder).
			Padding(0, 1)

	previewTitleStyle = lipgloss.NewStyle().
				Foreground(clrViolet).
				Bold(true)

	previewMetaStyle = lipgloss.NewStyle().
				Foreground(clrMuted)

	previewBodyStyle = lipgloss.NewStyle().
				Foreground(clrSubtext)
)

// ── Viewer ───────────────────────────────────────────────────────────────────

var (
	viewerTitleBarStyle = lipgloss.NewStyle().
				Background(clrPanel).
				Foreground(clrViolet).
				Bold(true).
				Padding(0, 2)

	viewerScrollStyle = lipgloss.NewStyle().
				Background(clrPanel).
				Foreground(clrMuted).
				Padding(0, 2)

	separatorStyle = lipgloss.NewStyle().
			Foreground(clrBorder)

	progressStyle = lipgloss.NewStyle().
			Foreground(clrPurple)
)

// ── Tier badges ──────────────────────────────────────────────────────────────

var tierColors = map[string]lipgloss.Color{
	"none":   clrMuted,
	"local":  clrCyan,
	"byok":   clrIndigo,
	"smaran": clrOrange,
}

var tierLabels = map[string]string{
	"none":   "Tier 0",
	"local":  "Tier 1",
	"byok":   "Tier 2",
	"smaran": "Tier 3",
}

func tierBadge(tier string) string {
	color, ok := tierColors[tier]
	if !ok {
		color = clrMuted
	}
	label, ok := tierLabels[tier]
	if !ok {
		label = tier
	}
	return lipgloss.NewStyle().
		Background(color).
		Foreground(clrWhite).
		Bold(true).
		Padding(0, 1).
		Render(" " + label + " ")
}
