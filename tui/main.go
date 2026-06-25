package main

import (
	"fmt"
	"os"

	tea "github.com/charmbracelet/bubbletea"
)

func main() {
	p := tea.NewProgram(
		initial(),
		tea.WithAltScreen(),       // full-screen mode
		tea.WithMouseCellMotion(), // mouse scroll support
	)
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "trident-tui:", err)
		os.Exit(1)
	}
}
