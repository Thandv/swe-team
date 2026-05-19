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

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export ANTHROPIC_MODEL=claude-sonnet-4-5      # optional, this is the default

echo '{
  "command": "build",
  "idea": "Python CLI that converts CSV to JSON",
  "swe_root": "/Users/gokulpm/Claude/SWE",
  "parent_dir": "/Users/gokulpm/Claude/SWE",
  "dry_run": false
}' | python orchestrator_driver.py
```

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
