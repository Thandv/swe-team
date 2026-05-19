# SWE — Software Engineering Agent Team

A multi-agent software engineering team that takes a product idea and produces working software end-to-end.

## Status

| Layer | State |
| --- | --- |
| Agent team (specs, design, code, QA) | **Working.** Smoke-tested end-to-end on a CSV→JSON CLI. |
| Static test suite (`tests/run_all.sh`) | **Passing.** 4 static checks + 1 gated end-to-end. CI green on every push. |
| Tauri 2 desktop shell (`binary/`) | **Scaffolded.** Window builds, submit button echoes input via a placeholder Rust command. |
| Phase 2 driver (orchestrator subprocess) | **First cut in progress.** Python sidecar using the Anthropic Agent SDK. See `binary/driver/`. |
| Release pipeline | Cross-platform Tauri build on `v*.*.*` tags. Publish gated on signing certs. |

## Goals

1. **Phase 1 (now)** — drive the team from inside Claude Code via `/swe-build <idea>`.
2. **Phase 2 (in progress)** — wrap the same team in a downloadable binary with a "what do you want to build?" screen. The Tauri shell spawns a Python driver subprocess that embeds the Anthropic Agent SDK and runs the team without Claude Code installed.

The agent definitions, orchestration playbook, and team conventions are **driver-independent** — plain markdown, no Claude-Code-specific syntax in the bodies. Phase 2 swaps the driver, not the team.

## Team

| Role | Agent file | Responsibility |
| --- | --- | --- |
| Product Manager | `agents/pm.md` | Turns a raw idea into a written brief: goals, non-goals, users, success criteria, clarifying questions. |
| Architect | `agents/architect.md` | Designs the system: tech choices, component boundaries, data shapes, build/deploy plan. Doubles as code reviewer on handoff. |
| C++ Systems Coder | `agents/coder-cpp.md` | Native/perf-sensitive code, CMake, low-level work. |
| Backend Coder | `agents/coder-backend.md` | Services, APIs, data layer. |
| Frontend Coder | `agents/coder-frontend.md` | UI, client-side logic, UX wiring. |
| Python Systems Coder | `agents/coder-python.md` | Tooling, scripts, data/ML pipelines, glue code. |
| QA | `agents/qa.md` | Test plans, automated tests, behavior verification, regression guards. |

The **orchestrator** (`orchestrator.md`) is a playbook, not a 7th agent. Under Claude Code, the main session acts as the orchestrator. Under the binary, the Agent SDK runs the orchestrator playbook as its main loop.

## Per-project layout

When the team builds something, output goes to a user-specified path or, if unset, `Claude/SWE/<project-name>/`:

```
<project>/
  specs/          PM brief, requirements, clarifying-question log
  design/         Architect's design docs, ADRs, interface contracts
  repo/           The actual source code
  binaries/       Compiled outputs (per-platform subdirs)
  reports/        QA results, review notes, security findings
  BUILD_LOG.json  Append-only trace of agent activity
```

## Driver independence

- `team-brief.md` — conventions every agent follows. Prepended to each agent's system prompt at runtime.
- `orchestrator.md` — the handoff playbook. Used as the orchestrator's system prompt.
- `agents/*.md` — one file per role. Each declares its capabilities and tool needs in frontmatter.

Drivers:

- **Claude Code (phase 1)** — `scripts/install-agents.sh` writes translated subagent files into `../.claude/agents/`. `/swe-build` is a slash-command shim around the orchestrator playbook. The main session routes work between agents using the Task tool.
- **Standalone binary (phase 2)** — Tauri 2 shell at `binary/` opens a window with a "what do you want to build?" textarea. Submit invokes a Rust command (`build_idea`) that spawns the Python driver at `binary/driver/` as a subprocess. The driver reads the same `orchestrator.md` / `team-brief.md` / `agents/` files, uses the Anthropic Agent SDK to spawn role agents, and streams events back to the UI over stdio JSON.

```
┌──────────────────────┐     stdio JSON       ┌──────────────────────┐     HTTPS      ┌──────────────────┐
│  Tauri shell (Rust)  │ ───────────────────▶ │  Python driver       │ ─────────────▶ │  Anthropic API   │
│  binary/src-tauri/   │ ◀──────────────────  │  binary/driver/      │ ◀───────────── │  (Claude models) │
└──────────────────────┘   events: started,   └──────────────────────┘                └──────────────────┘
        ▲                  handoff, done,            │                                          │
        │ window event     error                     │ spawns                                   │
        ▼                                            ▼                                          │
┌──────────────────────┐                    ┌──────────────────────┐                            │
│  UI (HTML + JS)      │                    │  Role agent (one of  │ ◀──────────────────────────┘
│  binary/index.html   │                    │  agents/*.md)        │
└──────────────────────┘                    └──────────────────────┘
```

## Upstream agents

All role agents are sourced from community collections and mirrored into `agents/upstream/` so the team functions without external network calls to fetch them. See `UPSTREAM.md` for provenance and `scripts/sync-upstream.sh` for the update workflow.
