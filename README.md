# SWE — Software Engineering Agent Team

A multi-agent software engineering team that takes a product idea and produces working software end-to-end.

## Goals

1. **Phase 1 (now)** — drive the team from inside Claude Code via `/swe-build <idea>`.
2. **Phase 2 (later)** — wrap the same team in a downloadable binary with a "what do you want to build?" screen. The binary embeds the Claude Agent SDK and runs the team without Claude Code installed.

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

- **Claude Code (phase 1)** — `.claude/agents/` symlinks expose the team to the Task tool. `/swe-build` is a slash-command shim around the orchestrator.
- **Standalone binary (phase 2)** — embeds Claude Agent SDK, reads the same files, exposes a UI.

## Upstream agents

All role agents are sourced from community collections and mirrored into `agents/upstream/` so the team functions without external network calls to fetch them. See `UPSTREAM.md` for provenance and `scripts/sync-upstream.sh` for the update workflow.
