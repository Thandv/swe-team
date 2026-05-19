# Phase 2 — Installable Binary

This directory holds the standalone desktop binary that wraps the agent team
with a "what do you want to build?" screen.

## Status

**Scaffolded.** The shell window builds and runs end-to-end, but the submit
handler is a placeholder: it echoes the input back. The real orchestrator
driver — which embeds the Claude Agent SDK and runs the phase-1 agent team —
lands in a follow-up.

## What's here

```
binary/
  index.html          UI shell (vanilla HTML/CSS)
  src/main.js         Submit-button wiring (calls Tauri invoke)
  package.json        Tauri CLI + API dev deps
  src-tauri/
    Cargo.toml        Rust crate config
    tauri.conf.json   App config (window, identifier, bundle)
    build.rs          Tauri build script
    src/main.rs       Entry point + `build_idea` placeholder command
    icons/            Placeholder icon set (replace before release)
  README.md           This file
```

## Stack: Tauri 2

Tauri 2 was picked over Electron / PyInstaller because:

- Smallest binary footprint of the three (single-digit MB on release).
- Native webview on every supported OS — no bundled Chromium.
- Rust shell is a clean place for the orchestrator driver to live once we
  embed the Agent SDK (FFI or a sidecar process).

The web UI is plain HTML/CSS/JS — no framework, no bundler. Keeping the
frontend honest about its current scope (one textarea, one button) means
phase-2 work focuses on the driver, not on rewriting UI plumbing.

## Build

Prerequisites:

- Node.js 18+ and npm
- Rust toolchain (`rustup`, `cargo`)
- Platform-specific deps:
  - **macOS**: Xcode Command Line Tools
  - **Linux**: `libwebkit2gtk-4.1-dev`, `build-essential`, `curl`, `wget`,
    `file`, `libxdo-dev`, `libssl-dev`, `libayatana-appindicator3-dev`,
    `librsvg2-dev`
  - **Windows**: Microsoft C++ Build Tools, WebView2 (preinstalled on
    Windows 11)

Then:

```
cd binary
npm install
npm run tauri build      # release build per host platform
npm run dev              # hot-reload dev shell
```

Release artifacts land under `src-tauri/target/release/bundle/`.

## Architecture (planned, phase-2 driver)

The binary is a thin shell around three pieces:

1. **UI** — single window with a text input ("what do you want to build?")
   plus a per-project history. Clarifying questions appear inline.
2. **Driver** — embeds the Claude Agent SDK, reads `../orchestrator.md` and
   `../team-brief.md`, spawns role agents from `../agents/`, routes work per
   the orchestrator playbook. Swap-in point: the `build_idea` Tauri command
   in `src-tauri/src/main.rs`.
3. **Model routing** — hybrid policy that prefers a local model for cheap
   steps (slug generation, PM clarification, scaffolding) and Claude for hard
   steps (architecture, debugging). The policy can graduate over time as the
   local model accumulates a "skill library" of past successful trajectories.

## Driver portability

The binary reads the same `agents/*.md` files the Claude Code phase-1 driver
uses. The portable capability vocabulary in agent frontmatter (`read`, `edit`,
`shell`, `web`, `spawn`) is what makes this possible — the binary maps those
to SDK tool implementations the same way `scripts/install-agents.sh` maps
them to Claude Code tools.

## CI

`.github/workflows/release.yml` runs the cross-platform Tauri build matrix
on tagged pushes (`v*.*.*`) and uploads per-OS artifacts. Code signing and
GitHub Release publishing are gated off until we have a signing setup —
flip the `publish` job's `if:` to enable it.
