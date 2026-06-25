package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

// Config mirrors ~/.trident/config.yaml
type Config struct {
	Version int    `yaml:"version"`
	AITier  string `yaml:"ai_tier"`
	Memory  struct {
		Primary string `yaml:"primary"`
	} `yaml:"memory"`
	Capture struct {
		SessionsDir string `yaml:"sessions_dir"`
		Redaction   string `yaml:"redaction"`
	} `yaml:"capture"`
}

// RunbookMeta is one entry from ~/.trident/memory/index.json
type RunbookMeta struct {
	Slug      string    `json:"slug"`
	Title     string    `json:"title"`
	SessionID string    `json:"session_id"`
	RunbookID string    `json:"runbook_id"`
	Path      string    `json:"path"`
	CreatedAt time.Time `json:"created_at"`
	Tags      []string  `json:"tags"`
	StepCount int       `json:"step_count"`
}

func tridentDir() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return ".trident"
	}
	return filepath.Join(home, ".trident")
}

func loadConfig() Config {
	var cfg Config
	data, err := os.ReadFile(filepath.Join(tridentDir(), "config.yaml"))
	if err != nil {
		cfg.AITier = "none"
		cfg.Memory.Primary = "markdown"
		return cfg
	}
	_ = yaml.Unmarshal(data, &cfg)
	if cfg.AITier == "" {
		cfg.AITier = "none"
	}
	if cfg.Memory.Primary == "" {
		cfg.Memory.Primary = "markdown"
	}
	return cfg
}

func loadRunbooks() []RunbookMeta {
	data, err := os.ReadFile(filepath.Join(tridentDir(), "memory", "index.json"))
	if err != nil {
		return nil
	}
	var rb []RunbookMeta
	_ = json.Unmarshal(data, &rb)
	sort.Slice(rb, func(i, j int) bool {
		return rb[i].CreatedAt.After(rb[j].CreatedAt)
	})
	return rb
}

func readRunbookFile(path string) string {
	data, err := os.ReadFile(path)
	if err != nil {
		return fmt.Sprintf("could not read %s: %v", path, err)
	}
	return string(data)
}

func countSessions() int {
	dir := filepath.Join(tridentDir(), "sessions")
	entries, err := os.ReadDir(dir)
	if err != nil {
		return 0
	}
	n := 0
	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".ndjson") {
			n++
		}
	}
	return n
}

func shortID(id string) string {
	if len(id) >= 8 {
		return id[:8]
	}
	return id
}

func relTime(t time.Time) string {
	if t.IsZero() {
		return "—"
	}
	d := time.Since(t)
	switch {
	case d < time.Minute:
		return "just now"
	case d < time.Hour:
		return fmt.Sprintf("%dm ago", int(d.Minutes()))
	case d < 24*time.Hour:
		return fmt.Sprintf("%dh ago", int(d.Hours()))
	case d < 7*24*time.Hour:
		return fmt.Sprintf("%dd ago", int(d.Hours()/24))
	default:
		return t.Format("Jan 02")
	}
}

func plural(n int, word string) string {
	if n == 1 {
		return fmt.Sprintf("%d %s", n, word)
	}
	return fmt.Sprintf("%d %ss", n, word)
}
