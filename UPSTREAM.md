# Upstream Provenance

Each agent in `agents/` is sourced from a community collection, mirrored into `agents/upstream/` as-pulled, then adapted into our normalized form at `agents/<role>.md`.

This file is the source of truth for **where each agent came from, what version we pulled, and what we changed**.

## Sync workflow

1. `scripts/sync-upstream.sh` fetches the latest version of each listed source into `agents/upstream/<role>.upstream.md` (overwriting).
2. The script then diffs `agents/upstream/<role>.upstream.md` against our `agents/<role>.md` and prints a summary.
3. A human (or a follow-up Claude run) reviews the diff and decides which upstream changes to fold in.
4. Update the version/commit fields in the table below after merging.

## Sources

| Role | Source repo | File path | Commit / version | License | Last synced | Adaptations |
| --- | --- | --- | --- | --- | --- | --- |
| pm | VoltAgent/awesome-claude-code-subagents | `categories/08-business-product/product-manager.md` | `6f804f0` (main, 2026-05-18) | MIT | 2026-05-18 | Renamed `product-manager` → `pm`; replaced Claude-Code tool list with capability vocabulary `[read, edit, web]`; appended Team conventions section (read team-brief, write to `specs/`, append to BUILD_LOG.json, end with HANDOFF). |
| architect | VoltAgent/awesome-claude-code-subagents | `categories/04-quality-security/architect-reviewer.md` | `6f804f0` (main, 2026-05-18) | MIT | 2026-05-18 | Renamed `architect-reviewer` → `architect`; capability vocabulary `[read, edit, shell]`; appended Team conventions plus an explicit dual-role block (design pass writes to `design/`, review pass writes `reports/review.md`) to satisfy our README requirement that the architect doubles as code reviewer. |
| coder-cpp | VoltAgent/awesome-claude-code-subagents | `categories/02-language-specialists/cpp-pro.md` | `6f804f0` (main, 2026-05-18) | MIT | 2026-05-18 | Renamed `cpp-pro` → `coder-cpp`; capability vocabulary `[read, edit, shell]`; appended Team conventions section pointing artifacts at `repo/` and `binaries/<platform>/`. |
| coder-backend | VoltAgent/awesome-claude-code-subagents | `categories/01-core-development/backend-developer.md` | `6f804f0` (main, 2026-05-18) | MIT | 2026-05-18 | Renamed `backend-developer` → `coder-backend`; capability vocabulary `[read, edit, shell]`; appended Team conventions section. |
| coder-frontend | VoltAgent/awesome-claude-code-subagents | `categories/01-core-development/frontend-developer.md` | `6f804f0` (main, 2026-05-18) | MIT | 2026-05-18 | Renamed `frontend-developer` → `coder-frontend`; capability vocabulary `[read, edit, shell]`; appended Team conventions section. Upstream's JSON `context-manager` handshake is superseded by team-brief workspace conventions (noted in footer). |
| coder-python | VoltAgent/awesome-claude-code-subagents | `categories/02-language-specialists/python-pro.md` | `6f804f0` (main, 2026-05-18) | MIT | 2026-05-18 | Renamed `python-pro` → `coder-python`; capability vocabulary `[read, edit, shell]`; appended Team conventions section. |
| qa | VoltAgent/awesome-claude-code-subagents | `categories/04-quality-security/qa-expert.md` | `6f804f0` (main, 2026-05-18) | MIT | 2026-05-18 | Renamed `qa-expert` → `qa`; capability vocabulary `[read, edit, shell]` (upstream omitted `edit`; we grant it since QA may write test fixtures and reports); appended Team conventions section pointing artifacts at `reports/`. |

## Adaptation rules

When we adapt an upstream agent into `agents/<role>.md`:

1. Keep the upstream system prompt intact wherever possible. We want to inherit community tuning.
2. Add a **Team conventions** section at the bottom referencing `team-brief.md`. This is what ties any upstream agent into our handoff protocol.
3. Replace tool lists in upstream frontmatter with our capability vocabulary (`read`, `edit`, `shell`, `web`, `spawn`) so the driver mapping in `team-brief.md` applies.
4. Record every deviation from upstream in the **Adaptations** column above, even small ones, so we can reapply them after a sync.

## Licensing

We can only mirror agents under permissive licenses (MIT, Apache-2.0, BSD, CC-BY, CC0, Unlicense). The License column above must be set before an agent is committed.
