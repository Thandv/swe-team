"""Phase 2 driver — runs the SWE agent team headless, spoken to over stdio.

The Tauri shell at ../src-tauri spawns this script as a subprocess, writes a
single JSON request on stdin, then reads JSON-line events on stdout until
either `done` or `error`.

Protocol
--------

Input  (stdin, one JSON object per line):
  {"command": "build",
   "idea": "<user idea text>",
   "swe_root": "/abs/path/to/SWE",
   "parent_dir": "/abs/path/where/projects/should/land",
   "dry_run": false}

  `dry_run` (optional, default false): if true, agents are stub responses
  instead of real API calls. Used by tests and for protocol smoke tests
  without an ANTHROPIC_API_KEY.

Output (stdout, JSON lines):
  {"event": "project_initialized", "project_root": "..."}
  {"event": "agent_started",   "role": "pm"}
  {"event": "log",             "level": "info", "message": "..."}
  {"event": "agent_completed", "role": "pm",
                               "artifacts": ["specs/brief.md"],
                               "handoff_target": "architect",
                               "notes": "..."}
  {"event": "user_question",   "role": "pm", "question": "..."}
  {"event": "error",           "message": "..."}
  {"event": "done",            "project_root": "...", "summary": "..."}

Exit codes
----------
  0  build completed (handoff_target == "done")
  1  unrecoverable error (also emitted as an "error" event)
  2  bad request on stdin (malformed JSON or missing fields)
  3  hit a `HANDOFF: user — ...` and the driver isn't wired for interactive
     follow-ups yet (UI integration deferred to phase 2.1)

Env
---
  ANTHROPIC_API_KEY   required unless dry_run=true
  ANTHROPIC_MODEL     optional, default "claude-sonnet-4-5"
"""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_ITERATIONS = 30
DEFAULT_MODEL = "claude-sonnet-4-5"
VALID_NEXT_ROLES = {
    "pm", "architect", "qa",
    "coder-cpp", "coder-backend", "coder-frontend", "coder-python",
    "user", "done",
}


# ---------- protocol ----------

def emit(event: str, **fields: Any) -> None:
    """Write a single JSON-line event to stdout and flush."""
    line = json.dumps({"event": event, **fields}, default=str)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def log(level: str, message: str) -> None:
    emit("log", level=level, message=message)


def fatal(message: str, code: int = 1) -> None:
    emit("error", message=message)
    sys.exit(code)


# ---------- workspace ----------

def derive_slug(idea: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", idea.lower()).strip("-")
    return (s[:48] or "unnamed-project").rstrip("-")


def init_project(idea: str, parent_dir: Path) -> Path:
    slug = derive_slug(idea)
    root = parent_dir / slug
    for sub in ("specs", "design", "repo", "binaries", "reports"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    log_file = root / "BUILD_LOG.json"
    if not log_file.exists():
        log_file.write_text("[]")
    idea_file = root / "specs" / "idea.md"
    if not idea_file.exists():
        idea_file.write_text(f"# Idea\n\n{idea}\n")
    return root


# ---------- handoff parsing ----------

@dataclass
class AgentResult:
    role: str
    artifacts: list[str]
    handoff_target: str  # role slug, "user", or "done"
    notes: str
    user_question: str | None = None


HANDOFF_RE = re.compile(
    r"^\s*HANDOFF\s*:\s*([a-z_-]+)\s*[—\-]\s*(.+?)\s*$",
    re.MULTILINE,
)


def parse_handoff(agent_text: str) -> tuple[str, str] | None:
    """Find the LAST HANDOFF directive in the agent's response."""
    matches = list(HANDOFF_RE.finditer(agent_text))
    if not matches:
        return None
    m = matches[-1]
    return m.group(1).strip(), m.group(2).strip()


# ---------- BUILD_LOG.json ----------

def append_buildlog(project_root: Path, entry: dict[str, Any]) -> None:
    log_file = project_root / "BUILD_LOG.json"
    try:
        data = json.loads(log_file.read_text() or "[]")
    except json.JSONDecodeError:
        data = []
    data.append(entry)
    log_file.write_text(json.dumps(data, indent=2))


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- tool definitions for Anthropic Messages API ----------

TOOLS = [
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file under the project root and return its contents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string",
                         "description": "Path relative to the project root."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write (or overwrite) a UTF-8 text file under the project root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string",
                         "description": "Path relative to the project root."},
                "content": {"type": "string",
                            "description": "Full file contents."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "append_file",
        "description": "Append text to a UTF-8 file under the project root. Creates the file if missing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_dir",
        "description": "List entries (files + subdirs) under a directory relative to the project root.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path relative to project root. Use '' for the root itself."},
            },
            "required": ["path"],
        },
    },
]


def _safe_resolve(project_root: Path, rel: str) -> Path:
    p = (project_root / rel).resolve()
    if project_root.resolve() not in [p, *p.parents]:
        raise PermissionError(f"path {rel!r} escapes project root")
    return p


def execute_tool(name: str, args: dict[str, Any], project_root: Path) -> str:
    """Run a tool the agent requested. Returns a string (the tool result block)."""
    if name == "read_file":
        path = _safe_resolve(project_root, args["path"])
        if not path.is_file():
            return f"ERROR: {args['path']} is not a file"
        return path.read_text()
    if name == "write_file":
        path = _safe_resolve(project_root, args["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args["content"])
        return f"OK: wrote {len(args['content'])} bytes to {args['path']}"
    if name == "append_file":
        path = _safe_resolve(project_root, args["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(args["content"])
        return f"OK: appended {len(args['content'])} bytes to {args['path']}"
    if name == "list_dir":
        path = _safe_resolve(project_root, args["path"])
        if not path.is_dir():
            return f"ERROR: {args['path']} is not a directory"
        entries = sorted(p.name + ("/" if p.is_dir() else "") for p in path.iterdir())
        return "\n".join(entries) or "(empty)"
    return f"ERROR: unknown tool {name!r}"


# ---------- agent invocation ----------

def build_system_prompt(team_brief: str, role_text: str) -> str:
    return (
        team_brief
        + "\n\n---\n\n"
        + role_text
    )


def build_user_message(idea: str, project_root: Path, role: str, note: str) -> str:
    return (
        f"You are spawned by the orchestrator as the **{role}** role.\n\n"
        f"Project root (absolute): {project_root}\n"
        f"All artifacts you produce must live inside that directory using the subdirs "
        f"documented in team-brief.md. The orchestrator passed in this note for you:\n\n"
        f"{note}\n\n"
        f"The original idea is preserved in `specs/idea.md` inside the project root."
        f"\n\nFollow your role definition. End your response with a single HANDOFF directive on its own line."
    )


def run_agent_with_anthropic(
    role: str,
    role_text: str,
    team_brief: str,
    project_root: Path,
    note: str,
    idea: str,
    model: str,
) -> AgentResult:
    """Real agent loop using the Anthropic Messages API."""
    try:
        from anthropic import Anthropic
    except ImportError:
        fatal(
            "anthropic package not installed. "
            "Install with: pip install anthropic"
        )

    client = Anthropic()
    system = build_system_prompt(team_brief, role_text)
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": build_user_message(idea, project_root, role, note)},
    ]
    artifacts_touched: list[str] = []
    final_text = ""

    # Tool-use loop: keep going until the model stops without requesting tools.
    for turn in range(20):  # per-agent turn cap
        response = client.messages.create(
            model=model,
            max_tokens=8000,
            system=system,
            tools=TOOLS,
            messages=messages,
        )
        # Append the assistant turn to the conversation as-is.
        messages.append({"role": "assistant", "content": response.content})

        # If the model produced text, accumulate it (we want the last text block's HANDOFF).
        for block in response.content:
            if block.type == "text":
                final_text = block.text
            elif block.type == "tool_use":
                pass  # handled below

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                log("debug", f"{role}: tool_use {block.name}({list(block.input.keys())})")
                try:
                    result = execute_tool(block.name, block.input, project_root)
                except Exception as e:  # noqa: BLE001
                    result = f"ERROR: {type(e).__name__}: {e}"
                # Track writes as artifacts.
                if block.name in ("write_file", "append_file"):
                    p = block.input.get("path")
                    if p and p not in artifacts_touched:
                        artifacts_touched.append(p)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
            messages.append({"role": "user", "content": tool_results})
            continue

        # Any other stop_reason (max_tokens, etc.) — bail.
        log("warn", f"{role}: unexpected stop_reason={response.stop_reason}")
        break
    else:
        log("warn", f"{role}: hit per-agent turn cap")

    # Parse HANDOFF from the final text block.
    handoff = parse_handoff(final_text)
    if not handoff:
        return AgentResult(
            role=role,
            artifacts=artifacts_touched,
            handoff_target="done",
            notes="agent ended without HANDOFF directive — assuming done",
        )
    target, note_out = handoff
    if target not in VALID_NEXT_ROLES:
        return AgentResult(
            role=role,
            artifacts=artifacts_touched,
            handoff_target="done",
            notes=f"agent emitted invalid HANDOFF target {target!r}; assuming done",
        )
    return AgentResult(
        role=role,
        artifacts=artifacts_touched,
        handoff_target=target,
        notes=note_out,
        user_question=note_out if target == "user" else None,
    )


def run_agent_stub(role: str, note: str, project_root: Path) -> AgentResult:
    """Dry-run stub. Writes a marker file and hands off to the next role in the chain."""
    chain = {
        "pm": "architect",
        "architect": "coder-python",
        "coder-python": "qa",
        "coder-backend": "qa",
        "coder-frontend": "qa",
        "coder-cpp": "qa",
        "qa": "architect",  # review pass
    }
    # Architect comes back for review then finishes — use a marker to detect re-entry.
    if role == "architect" and (project_root / "design" / "system.md").exists():
        next_role = "done"
        artifact_dir = project_root / "reports"
        artifact_name = "review.md"
    else:
        next_role = chain.get(role, "done")
        artifact_dir = {
            "pm": project_root / "specs",
            "architect": project_root / "design",
            "coder-python": project_root / "repo",
            "coder-backend": project_root / "repo",
            "coder-frontend": project_root / "repo",
            "coder-cpp": project_root / "repo",
            "qa": project_root / "reports",
        }.get(role, project_root)
        artifact_name = {
            "pm": "brief.md",
            "architect": "system.md",
            "coder-python": "main.py",
            "coder-backend": "main.py",
            "coder-frontend": "main.js",
            "coder-cpp": "main.cpp",
            "qa": "results.md",
        }.get(role, f"{role}.txt")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / artifact_name
    artifact_path.write_text(f"# {role} stub artifact\n\nDriver dry-run note: {note}\n")
    return AgentResult(
        role=role,
        artifacts=[str(artifact_path.relative_to(project_root))],
        handoff_target=next_role,
        notes=f"stub handoff from {role}",
    )


# ---------- orchestrator ----------

def run_team(request: dict[str, Any]) -> None:
    idea = request["idea"]
    swe_root = Path(request["swe_root"]).resolve()
    parent_dir = Path(request["parent_dir"]).resolve()
    dry_run = bool(request.get("dry_run", False))
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)

    # Validate SWE root has what we need.
    for required in ("team-brief.md", "orchestrator.md", "agents"):
        if not (swe_root / required).exists():
            fatal(f"swe_root {swe_root} missing {required}")

    team_brief = (swe_root / "team-brief.md").read_text()
    agents_dir = swe_root / "agents"

    project_root = init_project(idea, parent_dir)
    emit("project_initialized", project_root=str(project_root))

    next_role: str = "pm"
    note: str = idea

    for iteration in range(MAX_ITERATIONS):
        if next_role == "done":
            emit("done", project_root=str(project_root), summary=note)
            return
        if next_role == "user":
            emit("user_question", role="(previous)", question=note)
            fatal("user follow-up not wired through driver yet — phase 2.1", code=3)

        role_file = agents_dir / f"{next_role}.md"
        if not role_file.is_file():
            fatal(f"agent file not found: {role_file}")

        emit("agent_started", role=next_role)
        role_text = role_file.read_text()

        try:
            if dry_run:
                result = run_agent_stub(next_role, note, project_root)
            else:
                result = run_agent_with_anthropic(
                    role=next_role,
                    role_text=role_text,
                    team_brief=team_brief,
                    project_root=project_root,
                    note=note,
                    idea=idea,
                    model=model,
                )
        except Exception as e:  # noqa: BLE001
            emit("error", message=f"{type(e).__name__}: {e}", traceback=traceback.format_exc())
            sys.exit(1)

        append_buildlog(project_root, {
            "ts": now_iso(),
            "role": result.role,
            "action": "driver-spawned",
            "artifacts": result.artifacts,
            "next_role": result.handoff_target,
            "notes": result.notes,
        })
        emit("agent_completed",
             role=result.role,
             artifacts=result.artifacts,
             handoff_target=result.handoff_target,
             notes=result.notes)

        next_role = result.handoff_target
        note = result.notes

    fatal(f"hit MAX_ITERATIONS={MAX_ITERATIONS} without reaching done")


def main() -> int:
    try:
        line = sys.stdin.readline()
        if not line.strip():
            print("driver expects one JSON request on stdin", file=sys.stderr)
            return 2
        request = json.loads(line)
    except json.JSONDecodeError as e:
        print(f"bad request: {e}", file=sys.stderr)
        return 2

    if request.get("command") != "build":
        emit("error", message=f"unknown command: {request.get('command')!r}")
        return 2
    for key in ("idea", "swe_root", "parent_dir"):
        if key not in request:
            emit("error", message=f"missing required field: {key!r}")
            return 2

    run_team(request)
    return 0


if __name__ == "__main__":
    sys.exit(main())
