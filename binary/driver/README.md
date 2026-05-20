# Phase 2 Driver

Python subprocess spoken to over stdio JSON by the Tauri shell. Runs the SWE
agent team headless: spawns role agents via the Anthropic Messages API,
parses HANDOFF directives, advances the routing loop, and emits per-step
events.

## Install

```bash
cd binary/driver
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run standalone (dry-run, no API key needed)

```bash
echo '{
  "command": "build",
  "idea": "a hello-world script",
  "swe_root": "/Users/gokulpm/Claude/SWE",
  "parent_dir": "/tmp",
  "dry_run": true
}' | python orchestrator_driver.py
```

Output is one JSON event per line. With `dry_run: true`, agents are stubbed
out (each writes a placeholder file and hands off to the next role) so you
can validate the protocol end-to-end without an API key.

## Run live (real agents)

The driver speaks to two LLM backends — pick with `LLM_BACKEND`. Each
construction is lazy, so you only need the matching SDK and API key for the
backend you select.

### Where the key lives

Two equally-valid options. **Existing shell env vars always win** over the
file, so you can mix them (file for the persistent default, env for a
one-off override).

**Option A — keys.env file (recommended for repeated use):**

```bash
# Easiest: use the helper. It prompts silently and writes ~/.config/swe-team/keys.env
# with mode 0600. The key never lands in your shell history.
scripts/set-key.sh GEMINI_API_KEY          # or ANTHROPIC_API_KEY

# Or write the file yourself:
mkdir -p ~/.config/swe-team
chmod 700 ~/.config/swe-team
cat > ~/.config/swe-team/keys.env <<'EOF'
LLM_BACKEND=gemini
GEMINI_API_KEY=AIzaSy...
EOF
chmod 600 ~/.config/swe-team/keys.env
```

Search order (first hit wins):
1. `$SWE_TEAM_KEYS` (custom path)
2. `./keys.env` (current dir — useful in dev)
3. `./binary/driver/keys.env` (colocated)
4. `~/.config/swe-team/keys.env` (canonical)
5. `~/.swe-team/keys.env` (fallback)

All five locations are gitignored. The file format is plain `KEY=value`
with `#` comments, no quote-escaping (paste the key as-is).

**Option B — shell env vars (one-off):**

```bash
export LLM_BACKEND=anthropic                         # or gemini
export ANTHROPIC_API_KEY=sk-ant-...                  # or GEMINI_API_KEY
# export LLM_MODEL=claude-sonnet-4-5                 # optional override
```

Then:
```bash
echo '{
  "command": "build",
  "idea": "Python CLI that converts CSV to JSON",
  "swe_root": "/Users/gokulpm/Claude/SWE",
  "parent_dir": "/Users/gokulpm/Claude/SWE",
  "dry_run": false
}' | python orchestrator_driver.py
```

Adding a new backend: subclass `Backend` in `orchestrator_driver.py`,
register it in `make_backend()`, and add its default model to `DEFAULT_MODELS`.

## Protocol

**Input** (stdin, one JSON object):

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `command` | string | yes | Must be `"build"`. |
| `idea` | string | yes | The user's idea text. |
| `swe_root` | string | yes | Absolute path to the SWE repo (where `agents/`, `team-brief.md`, `orchestrator.md` live). |
| `parent_dir` | string | yes | Where the new project workspace should be created. |
| `dry_run` | bool | no | If true, agents are stubs. Default false. |

**Output** (stdout, JSON lines):

| `event` | Other fields | When |
| --- | --- | --- |
| `project_initialized` | `project_root` | After workspace dirs are created. |
| `agent_started` | `role` | Before each agent invocation. |
| `log` | `level`, `message` | Anywhere — diagnostic. |
| `agent_completed` | `role`, `artifacts`, `handoff_target`, `notes` | After each agent finishes. |
| `user_question` | `role`, `question` | When an agent emits `HANDOFF: user — ...` (not yet handled; exits with code 3). |
| `error` | `message`, optional `traceback` | On any unrecoverable failure. |
| `done` | `project_root`, `summary` | When the chain reaches `HANDOFF: done`. |

**Exit codes**

- `0` build completed
- `1` unrecoverable error (also emitted as an `error` event)
- `2` bad request on stdin
- `3` agent requested user follow-up (phase 2.1 work to wire UI prompt)

## Tools given to each agent

Filesystem tools only, sandboxed to the project root:

- `read_file(path)`
- `write_file(path, content)`
- `append_file(path, content)`
- `list_dir(path)`

`shell` and `web` capabilities declared in agent frontmatter are **not** yet
exposed by the driver. Adding them requires sandboxing decisions that
deserve their own design pass.

## Tests

```bash
pytest tests/
```

The included test runs the driver in `dry_run` mode against the live
`agents/` definitions and verifies the protocol shape end-to-end. No API key
required.
