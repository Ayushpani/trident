.PHONY: build install test clean

# ── TUI binary ────────────────────────────────────────────────────────────────

build:
	cd tui && go build -o ../trident-tui .

install: build
	@echo "Installing trident-tui to ~/.local/bin/"
	@mkdir -p ~/.local/bin
	cp trident-tui ~/.local/bin/trident-tui
	@echo "Done. Make sure ~/.local/bin is in your PATH."

# ── Python package ────────────────────────────────────────────────────────────

dev:
	pip install -e shellstory-main/shellstory-main
	pip install -e .

# ── Tests ─────────────────────────────────────────────────────────────────────

test:
	pytest tests/ -q

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	rm -f trident-tui trident-tui.exe
	find . -name "__pycache__" -not -path "*/shellstory-main/*" \
	       -not -path "*/ks-ai-main/*" -not -path "*/smaran-main/*" \
	       -exec rm -rf {} + 2>/dev/null || true
