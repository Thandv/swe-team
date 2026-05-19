# Contributing

## Local setup

```bash
git clone <this-repo>
cd <this-repo>
scripts/install-agents.sh   # installs adapted agents into ../.claude/agents/
tests/run_all.sh            # static checks
tests/run_all.sh --e2e      # adds the gated end-to-end check
```

The repo lives next to your `~/Claude/` workspace (or any directory whose
`.claude/agents/` you want the team installed into).

## Running the team

From inside a Claude Code session in the parent directory:

```
/swe-build <one-line idea>
```

The orchestrator (defined in `orchestrator.md`) routes work between the role
agents in `agents/`. Output goes to `<parent>/<project-slug>/`.

Phase 2 (the standalone binary) will drive the same agents through the Claude
Agent SDK instead of Claude Code. The team files do not need to change.

## Adding or changing an agent

1. Edit the file under `agents/<role>.md`. Keep it lean — under 150 lines.
2. The Team conventions footer is load-bearing. Don't change its shape; it's
   what ties any agent into the HANDOFF protocol.
3. Run `scripts/install-agents.sh` to push the change into `.claude/agents/`.
4. Run `tests/run_all.sh`. All four static checks must pass.

## Updating upstream

```bash
scripts/sync-upstream.sh           # refresh agents/upstream/<role>.upstream.md
```

Then review the diff against `agents/<role>.md` (our adapted version) and
decide whether to fold any upstream changes in. Record what you did in
`UPSTREAM.md`.

## Test layout

- `tests/lint_agents.py` — frontmatter, size budget, banned upstream-isms.
- `tests/check_install.sh` — sandboxed run of `install-agents.sh`.
- `tests/check_buildlog.py` — schema check for any `BUILD_LOG.json`.
- `tests/check_protocol.py` — orchestrator/team-brief/agents consistency.
- `tests/e2e/csv2json.sh` — end-to-end against a team-produced workspace.
- `tests/run_all.sh` — runs everything; `--e2e` adds the gated end-to-end.

## Commit style

- Keep agent diffs separate from infra diffs (script changes, CI changes).
- If you adjust the HANDOFF protocol, update `team-brief.md`, every agent's
  footer, AND `tests/check_protocol.py` in the same commit.
