# Phase 2 — Installable Binary

This directory is reserved for the standalone binary that wraps the agent team
with a "what do you want to build?" screen.

## Status

**Not yet implemented.** Phase 1 (the team itself, driven from Claude Code via
`/swe-build`) is the current focus. The binary will be built once the team
flow is reliable.

## What goes here

When phase 2 starts, this directory will contain:

```
binary/
  src/             Application source (UI shell + agent driver)
  Cargo.toml       (Tauri) or package.json (Electron) or pyproject.toml (Python+PyInstaller)
  README.md        How to build locally
  installers/      Per-platform install bundles produced by CI
```

## Architecture (planned)

The binary is a thin shell around three pieces:

1. **UI**: a single window with a text input ("what do you want to build?")
   plus a per-project history. Clarifying questions appear inline.
2. **Driver**: embeds the Claude Agent SDK, reads `../orchestrator.md` and
   `../team-brief.md`, spawns role agents from `../agents/`, routes work per
   the orchestrator playbook.
3. **Model routing**: a hybrid policy that prefers a local model for cheap
   steps (slug generation, PM clarification, scaffolding) and Claude for hard
   steps (architecture, debugging). The policy can graduate over time as the
   local model accumulates a "skill library" of past successful trajectories.

## Stack decision

Pending. Candidates:

- **Tauri** (Rust shell, web UI, small binary). Best fit for "single
  downloadable binary that installs cleanly." Native feel on macOS/Windows/Linux.
- **Electron** (Node shell, web UI, larger binary). More ecosystem; heavier.
- **Python + PyInstaller** (single-file Python executable). Simplest path if
  the rest of the team tooling stays Python-first.

The choice gates the release CI workflow at `.github/workflows/release.yml`,
which is currently a placeholder.

## Driver portability

The binary reads the same `agents/*.md` files the Claude Code phase-1 driver
uses. The portable capability vocabulary in agent frontmatter (`read`, `edit`,
`shell`, `web`, `spawn`) is what makes this possible — the binary maps those
to SDK tool implementations the same way `scripts/install-agents.sh` maps
them to Claude Code tools.
