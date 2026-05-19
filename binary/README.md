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
  package.json          Tauri CLI + API dev deps
  frontend/
    index.html          UI shell (vanilla HTML/CSS) — isolated from src-tauri/, node_modules/
    src/main.js         Submit wiring; calls the Rust `build_idea` command
  src-tauri/
    Cargo.toml          Rust crate config
    tauri.conf.json     App config; `frontendDist` points at ../frontend
    build.rs            Tauri build script
    src/main.rs         Entry point + `build_idea` command (spawns driver subprocess)
    icons/              Placeholder icon set (replace before release)
  driver/
    orchestrator_driver.py   Python driver — runs the team headless over stdio JSON
    pyproject.toml           Driver package config (deps: anthropic)
    tests/                   Protocol tests (dry-run, no API key needed)
    README.md                Driver-specific docs
  README.md             This file
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
GitHub Release publishing are gated off until you've configured signing —
see the next section.

## Before shipping a signed release

Three things to get in order. None block the CI build itself — they only
gate the `publish` job in `release.yml` (currently `if: false`).

### 1. Replace the placeholder icons

`src-tauri/icons/` ships with single-color PNG placeholders generated from
Python `zlib`. They're enough to satisfy Tauri's icon requirement but not
fit for distribution. Replace them with real branding:

```
src-tauri/icons/
  32x32.png            Required, used for taskbars
  128x128.png          Required
  128x128@2x.png       Required, retina
  icon.icns            macOS bundle (Tauri can generate from a 1024×1024 PNG)
  icon.ico             Windows installer
  Square30x30Logo.png  Microsoft Store sizes; needed if you target MS Store
  Square44x44Logo.png  …through Square310x310Logo.png + StoreLogo.png
```

Fastest path: produce one 1024×1024 source PNG, then run
`npx @tauri-apps/cli icon path/to/source.png` from `binary/` — it emits
every size and format Tauri's bundler wants.

### 2. Wire macOS signing + notarization

GitHub repo secrets to set (Settings → Secrets and variables → Actions):

| Secret | What it is |
| --- | --- |
| `APPLE_CERTIFICATE` | Developer ID Application cert, base64-encoded p12. `base64 -i cert.p12 \| pbcopy`. |
| `APPLE_CERTIFICATE_PASSWORD` | Password for the p12. |
| `APPLE_SIGNING_IDENTITY` | E.g. `Developer ID Application: Your Name (TEAMID)`. |
| `APPLE_ID` | The Apple ID email used for notarization. |
| `APPLE_PASSWORD` | App-specific password generated at appleid.apple.com. |
| `APPLE_TEAM_ID` | 10-character team ID from your Apple Developer account. |

In `release.yml`, the macOS legs of the build matrix need an additional env
block referencing those secrets. `tauri-apps/tauri-action` picks them up
automatically when present.

### 3. Wire Windows signing

| Secret | What it is |
| --- | --- |
| `WINDOWS_CERTIFICATE` | Base64-encoded `.pfx` of your code-signing cert. |
| `WINDOWS_CERTIFICATE_PASSWORD` | Password for the pfx. |

Add to `tauri.conf.json > bundle > windows > certificateThumbprint` (or use
the action's env-var passthrough). Without these, Windows still builds an
`.exe` and `.msi`, but they trigger SmartScreen warnings on install.

### 4. Flip the publish job on

Once the matrix builds reliably with signing, change `release.yml`:

```yaml
publish:
  needs: build
  runs-on: ubuntu-latest
  if: true   # was: false
```

The job downloads every per-OS artifact and creates a GitHub Release using
`softprops/action-gh-release@v2`. Release notes are auto-generated from
commits since the previous tag.

### Linux (no signing needed)

The Linux leg already produces `.deb` and `.AppImage` artifacts. No certs
needed — users can install directly. If you publish to a package manager
(apt, Flatpak, Snap), that's a separate workflow.
