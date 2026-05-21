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

Env / keys
----------
  LLM_BACKEND         anthropic (default) | gemini
  LLM_MODEL           overrides the per-backend default
  ANTHROPIC_API_KEY   required when LLM_BACKEND=anthropic and dry_run=false
  GEMINI_API_KEY      required when LLM_BACKEND=gemini and dry_run=false
                      (GOOGLE_API_KEY also accepted)

Instead of exporting these in your shell every time, you can drop them into
a `keys.env` file with `KEY=value` lines and the driver will pick them up
on startup. Searched in this order, first match wins:

  1. $SWE_TEAM_KEYS                          (custom path)
  2. ./keys.env                              (cwd, useful during dev)
  3. ./binary/driver/keys.env                (colocated with the driver)
  4. ~/.config/swe-team/keys.env             (XDG-style canonical location)
  5. ~/.swe-team/keys.env                    (fallback)

Existing environment variables ALWAYS take precedence over the file — the
loader uses os.environ.setdefault. So you can override per-session by
exporting in your shell, and the file is the persistent default.

`keys.env` MUST NOT be committed; every standard location is gitignored.
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
DEFAULT_BACKEND = "anthropic"
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-5",
    "gemini":    "gemini-2.5-flash",
    "local":     "qwen2.5:7b",
}
DEFAULT_LOCAL_BASE_URL = "http://localhost:11434/v1"
VALID_NEXT_ROLES = {
    "pm", "architect", "qa",
    "coder-cpp", "coder-backend", "coder-frontend", "coder-python",
    "user", "done",
}


# ---------- keys file ----------

def _parse_env_file(text: str) -> dict[str, str]:
    """Parse a .env-style file: KEY=value per line, # comments, blanks ignored.

    Values are NOT shell-unquoted; everything after the first `=` is taken
    literally with surrounding whitespace stripped. This keeps the format
    obvious (paste the key as-is, no quotes to escape).
    """
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        # Strip surrounding quotes if present, but don't process escapes.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        result[key] = value
    return result


def _key_file_candidates() -> list[Path]:
    paths: list[Path] = []
    custom = os.environ.get("SWE_TEAM_KEYS")
    if custom:
        paths.append(Path(custom).expanduser())
    paths.extend([
        Path.cwd() / "keys.env",
        Path.cwd() / "binary" / "driver" / "keys.env",
        Path.home() / ".config" / "swe-team" / "keys.env",
        Path.home() / ".swe-team" / "keys.env",
    ])
    return paths


def load_keys_from_file() -> Path | None:
    """Find a keys.env at a standard location and merge it into os.environ.

    Existing env vars take precedence (setdefault), so a shell `export`
    overrides the file. Returns the path that was loaded, or None.
    """
    for path in _key_file_candidates():
        if not path.is_file():
            continue
        try:
            entries = _parse_env_file(path.read_text())
        except OSError:
            continue
        for k, v in entries.items():
            os.environ.setdefault(k, v)
        return path
    return None


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
#
# Tools are grouped by capability so we can hand each agent only the tools its
# role frontmatter declared. The capability vocabulary matches team-brief.md.

_TOOL_READ_FILE = {
    "name": "read_file",
    "description": "Read a UTF-8 text file under the project root and return its contents.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to the project root."},
        },
        "required": ["path"],
    },
}

_TOOL_WRITE_FILE = {
    "name": "write_file",
    "description": "Write (or overwrite) a UTF-8 text file under the project root.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to the project root."},
            "content": {"type": "string", "description": "Full file contents."},
        },
        "required": ["path", "content"],
    },
}

_TOOL_APPEND_FILE = {
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
}

_TOOL_LIST_DIR = {
    "name": "list_dir",
    "description": "List entries (files + subdirs) under a directory relative to the project root.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path relative to project root. Use '' for the root itself."},
        },
        "required": ["path"],
    },
}

_TOOL_BASH = {
    "name": "bash",
    "description": (
        "Run a bash command from the project root. Use this to run tests, "
        "compile code, start servers, or any other shell operation needed to "
        "verify work. The command runs with the same privileges as the driver; "
        "agents are trusted not to do destructive things outside the project "
        "root. Default timeout 60s, max 300s."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The bash command line. Runs with shell=True."},
            "timeout_seconds": {"type": "integer", "description": "Optional timeout in seconds. Default 60, max 300.", "minimum": 1, "maximum": 300},
        },
        "required": ["command"],
    },
}

# Map each portable capability to the concrete tools it grants.
CAPABILITY_TO_TOOLS: dict[str, list[dict]] = {
    "read":  [_TOOL_READ_FILE, _TOOL_LIST_DIR],
    "edit":  [_TOOL_WRITE_FILE, _TOOL_APPEND_FILE],
    "shell": [_TOOL_BASH],
    # `web` and `spawn` are declared by some agents but not yet implemented
    # in the driver — they map to empty tool lists for now.
    "web":   [],
    "spawn": [],
}


def _safe_resolve(project_root: Path, rel: str) -> Path:
    p = (project_root / rel).resolve()
    if project_root.resolve() not in [p, *p.parents]:
        raise PermissionError(f"path {rel!r} escapes project root")
    return p


def execute_tool(name: str, args: dict[str, Any], project_root: Path) -> str:
    """Run a tool the agent requested. Returns a string (the tool result block).

    Always returns a string — sandbox violations (paths outside the project
    root) and other expected failures are caught and reported as `ERROR: ...`
    so the agent gets a useful tool-result to react to instead of an
    unhandled exception in the loop.
    """
    try:
        return _execute_tool_inner(name, args, project_root)
    except PermissionError as e:
        return f"ERROR: PermissionError: {e}"
    except FileNotFoundError as e:
        return f"ERROR: FileNotFoundError: {e}"
    except (OSError, ValueError) as e:
        return f"ERROR: {type(e).__name__}: {e}"


def _execute_tool_inner(name: str, args: dict[str, Any], project_root: Path) -> str:
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
    if name == "bash":
        import subprocess
        cmd = args["command"]
        timeout = min(int(args.get("timeout_seconds", 60)), 300)
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            return f"TIMEOUT after {timeout}s\nstdout (partial):\n{e.stdout or ''}\nstderr (partial):\n{e.stderr or ''}"
        # Truncate output the model can't usefully consume.
        stdout = proc.stdout[:50_000]
        stderr = proc.stderr[:10_000]
        suffix_stdout = "\n…(truncated)" if len(proc.stdout) > 50_000 else ""
        suffix_stderr = "\n…(truncated)" if len(proc.stderr) > 10_000 else ""
        return (
            f"exit_code: {proc.returncode}\n"
            f"--- stdout ---\n{stdout}{suffix_stdout}\n"
            f"--- stderr ---\n{stderr}{suffix_stderr}"
        )
    return f"ERROR: unknown tool {name!r}"


# ---------- frontmatter parsing for capability gating ----------

def parse_role_capabilities(role_text: str) -> list[str]:
    """Extract the `tools:` list from the agent file's YAML frontmatter."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", role_text, re.DOTALL)
    if not m:
        return []
    fm = m.group(1)
    tools_match = re.search(r"^tools:\s*(.+)$", fm, re.MULTILINE)
    if not tools_match:
        return []
    raw = tools_match.group(1).strip().strip("[]")
    return [c.strip().strip("'\"") for c in raw.split(",") if c.strip()]


def tools_for_role(role_text: str) -> list[dict]:
    """Return the JSON tool definitions an agent gets based on its declared caps."""
    caps = parse_role_capabilities(role_text)
    seen: set[str] = set()
    tools: list[dict] = []
    for cap in caps:
        for t in CAPABILITY_TO_TOOLS.get(cap, []):
            if t["name"] not in seen:
                seen.add(t["name"])
                tools.append(t)
    return tools


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


# ---------- LLM backend abstraction ----------
#
# Two backends so far: Anthropic Messages API and Google Gemini. The agent
# loop below talks to either one via the Backend interface so the team
# definition, tools, and HANDOFF protocol are unaware of provider quirks.
# Add a new backend by subclassing Backend and registering it in `make_backend`.


@dataclass
class ToolUseRequest:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class TurnResult:
    text: str
    tool_uses: list[ToolUseRequest]
    stop_reason: str  # "end_turn" | "tool_use" | "other"
    raw_assistant: Any  # provider-specific; the backend appends this to history


class Backend:
    """Subclass and register in `make_backend` to add a provider."""

    name: str = "abstract"

    def initial_messages(self, user_text: str) -> Any:
        raise NotImplementedError

    def call(self, system: str, messages: Any, tools: list[dict], model: str) -> TurnResult:
        raise NotImplementedError

    def append_assistant(self, messages: Any, turn: TurnResult) -> Any:
        raise NotImplementedError

    def append_tool_results(
        self,
        messages: Any,
        results: list[tuple[str, str, str]],  # (id, name, result_text)
    ) -> Any:
        raise NotImplementedError


class AnthropicBackend(Backend):
    name = "anthropic"

    def __init__(self) -> None:
        try:
            from anthropic import Anthropic
        except ImportError:
            fatal("anthropic package not installed. Install with: pip install anthropic")
        self.client = Anthropic()  # picks up ANTHROPIC_API_KEY from env

    def initial_messages(self, user_text: str) -> list[dict]:
        return [{"role": "user", "content": user_text}]

    def call(self, system: str, messages: list[dict], tools: list[dict], model: str) -> TurnResult:
        response = self.client.messages.create(
            model=model, max_tokens=8000, system=system, tools=tools, messages=messages,
        )
        text = ""
        tool_uses: list[ToolUseRequest] = []
        for block in response.content:
            if block.type == "text":
                text = block.text
            elif block.type == "tool_use":
                tool_uses.append(ToolUseRequest(id=block.id, name=block.name, args=dict(block.input)))
        stop = response.stop_reason or "other"
        if stop not in ("end_turn", "tool_use"):
            stop = "other"
        return TurnResult(text=text, tool_uses=tool_uses, stop_reason=stop, raw_assistant=response.content)

    def append_assistant(self, messages: list[dict], turn: TurnResult) -> list[dict]:
        messages.append({"role": "assistant", "content": turn.raw_assistant})
        return messages

    def append_tool_results(self, messages: list[dict], results: list[tuple[str, str, str]]) -> list[dict]:
        messages.append({
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": tid, "content": text}
                for tid, _name, text in results
            ],
        })
        return messages


class GeminiBackend(Backend):
    name = "gemini"

    def __init__(self) -> None:
        try:
            from google import genai
            from google.genai import types as gentypes
        except ImportError:
            fatal("google-genai package not installed. Install with: pip install google-genai")
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            fatal("GEMINI_API_KEY (or GOOGLE_API_KEY) is required when LLM_BACKEND=gemini")
        self.client = genai.Client(api_key=api_key)
        self._types = gentypes

    def initial_messages(self, user_text: str) -> list[Any]:
        T = self._types
        return [T.Content(role="user", parts=[T.Part(text=user_text)])]

    def _to_gemini_tools(self, tools: list[dict]) -> list[Any]:
        T = self._types
        decls = [
            T.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters=t["input_schema"],
            )
            for t in tools
        ]
        return [T.Tool(function_declarations=decls)] if decls else []

    def call(self, system: str, messages: list[Any], tools: list[dict], model: str) -> TurnResult:
        T = self._types
        config = T.GenerateContentConfig(
            system_instruction=system,
            tools=self._to_gemini_tools(tools),
        )
        response = self._call_with_backoff(model, messages, config)
        text = ""
        tool_uses: list[ToolUseRequest] = []
        # Use a counter to synthesize stable IDs so we can pair function_response
        # with the right function_call when there are duplicates.
        seq = 0
        candidate = response.candidates[0] if response.candidates else None
        raw_parts = []
        if candidate and candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                raw_parts.append(part)
                if getattr(part, "text", None):
                    text = part.text
                fc = getattr(part, "function_call", None)
                if fc and fc.name:
                    seq += 1
                    args = dict(fc.args) if fc.args else {}
                    tool_uses.append(ToolUseRequest(id=f"gem-{seq}", name=fc.name, args=args))
        stop = "tool_use" if tool_uses else "end_turn"
        return TurnResult(
            text=text,
            tool_uses=tool_uses,
            stop_reason=stop,
            raw_assistant=raw_parts,
        )

    def _call_with_backoff(self, model: str, messages: list[Any], config: Any, max_attempts: int = 6) -> Any:
        """Hit Gemini, retrying on 429 RESOURCE_EXHAUSTED and 503 UNAVAILABLE.

        Free tier on gemini-2.5-flash is only 5 req/min, and the shared free
        pool sometimes returns 503 spikes. Without retry, any multi-turn
        agent immediately fails. For 429 we use the API's own retryDelay
        hint when present; for 503 we exponential-backoff (3, 6, 12, 24, 48).
        """
        import re as _re
        import time as _time
        last_err: Exception | None = None
        backoff_503 = 3.0
        for attempt in range(1, max_attempts + 1):
            try:
                return self.client.models.generate_content(
                    model=model, contents=messages, config=config,
                )
            except Exception as e:  # noqa: BLE001
                last_err = e
                msg = str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    delay = 30.0
                    m = _re.search(r"retryDelay'?\s*[:=]\s*'?(\d+(?:\.\d+)?)s", msg)
                    if m:
                        delay = float(m.group(1))
                    delay = min(max(delay + 1, 5), 90)
                    reason = "429 quota"
                elif "503" in msg or "UNAVAILABLE" in msg:
                    delay = backoff_503
                    backoff_503 = min(backoff_503 * 2, 60.0)
                    reason = "503 unavailable"
                else:
                    raise
                if attempt >= max_attempts:
                    break
                log("warn", f"gemini {reason}; sleeping {delay:.0f}s (attempt {attempt}/{max_attempts})")
                _time.sleep(delay)
        assert last_err is not None
        raise last_err

    def append_assistant(self, messages: list[Any], turn: TurnResult) -> list[Any]:
        T = self._types
        messages.append(T.Content(role="model", parts=turn.raw_assistant))
        return messages

    def append_tool_results(self, messages: list[Any], results: list[tuple[str, str, str]]) -> list[Any]:
        T = self._types
        parts = [
            T.Part(function_response=T.FunctionResponse(
                name=name,
                response={"result": text},
            ))
            for _id, name, text in results
        ]
        messages.append(T.Content(role="user", parts=parts))
        return messages


class LocalBackend(Backend):
    """OpenAI-compatible HTTP backend. Default base URL targets Ollama on
    localhost; works with any OpenAI-compat server (LM Studio, llama.cpp's
    `llama-server`, vLLM, etc.) by overriding LOCAL_BASE_URL.

    Model needs to support tool/function calling. As of 2026 that's
    llama3.1+, qwen2.5+, mistral-small/large, and a few others — check
    `ollama show <model> --modelfile` for the `tools` capability.
    """

    name = "local"

    def __init__(self) -> None:
        try:
            from openai import OpenAI
        except ImportError:
            fatal("openai package not installed. Install with: pip install openai")
        base_url = os.environ.get("LOCAL_BASE_URL", DEFAULT_LOCAL_BASE_URL)
        # Some local servers ignore the key; Ollama tolerates anything. The
        # SDK requires a non-empty string though, so we send a placeholder
        # unless the user supplied a real one (some auth proxies want one).
        api_key = os.environ.get("LOCAL_API_KEY", "ollama")
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.base_url = base_url

    def initial_messages(self, user_text: str) -> list[dict]:
        return [{"role": "user", "content": user_text}]

    def _to_openai_tools(self, tools: list[dict]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]

    def call(self, system: str, messages: list[dict], tools: list[dict], model: str) -> TurnResult:
        # OpenAI puts the system prompt as the first message, not a separate
        # field. Prepend it on each call (cheap; doesn't mutate messages).
        full_messages = [{"role": "system", "content": system}] + messages
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": full_messages,
        }
        if tools:
            kwargs["tools"] = self._to_openai_tools(tools)
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        msg = choice.message

        text = msg.content or ""
        tool_uses: list[ToolUseRequest] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    args = {}
                tool_uses.append(ToolUseRequest(
                    id=tc.id, name=tc.function.name, args=args,
                ))
        stop = "tool_use" if tool_uses else "end_turn"

        # Stash the assistant message dict so we can replay it next turn.
        # We don't use the raw object directly because some servers omit
        # fields the SDK expects.
        raw = {"role": "assistant", "content": text or None}
        if tool_uses:
            raw["tool_calls"] = [
                {
                    "id": u.id,
                    "type": "function",
                    "function": {"name": u.name, "arguments": json.dumps(u.args)},
                }
                for u in tool_uses
            ]
        return TurnResult(text=text, tool_uses=tool_uses, stop_reason=stop, raw_assistant=raw)

    def append_assistant(self, messages: list[dict], turn: TurnResult) -> list[dict]:
        messages.append(turn.raw_assistant)
        return messages

    def append_tool_results(self, messages: list[dict], results: list[tuple[str, str, str]]) -> list[dict]:
        # OpenAI wants one `tool` message per tool_call_id (not a batch).
        for tid, _name, text in results:
            messages.append({
                "role": "tool",
                "tool_call_id": tid,
                "content": text,
            })
        return messages


def make_backend(name: str | None = None) -> Backend:
    name = (name or os.environ.get("LLM_BACKEND") or DEFAULT_BACKEND).lower().strip()
    if name == "anthropic":
        return AnthropicBackend()
    if name == "gemini":
        return GeminiBackend()
    if name == "local":
        return LocalBackend()
    fatal(f"unknown LLM_BACKEND={name!r}; valid: anthropic, gemini, local")


def _env_role_key(prefix: str, role: str) -> str:
    """Translate a role slug into the env-var suffix convention.

    `coder-python` → `CODER_PYTHON`, so callers can set
    `LLM_BACKEND_CODER_PYTHON=local` etc.
    """
    return f"{prefix}_{role.upper().replace('-', '_')}"


def backend_name_for_role(role: str) -> str:
    """Pick the backend for a specific role. Per-role env wins over global."""
    per_role = os.environ.get(_env_role_key("LLM_BACKEND", role))
    if per_role:
        return per_role.lower().strip()
    return (os.environ.get("LLM_BACKEND") or DEFAULT_BACKEND).lower().strip()


def model_for_role(role: str, backend_name: str) -> str:
    """Pick the model for a specific role. Per-role env wins over global."""
    per_role = os.environ.get(_env_role_key("LLM_MODEL", role))
    if per_role:
        return per_role
    return os.environ.get("LLM_MODEL") or DEFAULT_MODELS.get(backend_name, "")


# ---------- provider-agnostic agent loop ----------

def run_agent_live(
    role: str,
    role_text: str,
    team_brief: str,
    project_root: Path,
    note: str,
    idea: str,
    backend: Backend,
    model: str,
) -> AgentResult:
    """Drive a real LLM through the team's HANDOFF protocol, backend-agnostic."""
    system = build_system_prompt(team_brief, role_text)
    tools = tools_for_role(role_text)
    log("debug", f"{role}: backend={backend.name} model={model} tools={[t['name'] for t in tools]}")
    messages = backend.initial_messages(
        build_user_message(idea, project_root, role, note)
    )
    artifacts_touched: list[str] = []
    final_text = ""

    for turn in range(20):  # per-agent turn cap
        turn_result = backend.call(system, messages, tools, model)
        messages = backend.append_assistant(messages, turn_result)
        if turn_result.text:
            final_text = turn_result.text

        if turn_result.stop_reason == "end_turn":
            break

        if turn_result.stop_reason == "tool_use":
            results: list[tuple[str, str, str]] = []
            for use in turn_result.tool_uses:
                log("debug", f"{role}: tool_use {use.name}({list(use.args.keys())})")
                output = execute_tool(use.name, use.args, project_root)
                if use.name in ("write_file", "append_file"):
                    p = use.args.get("path")
                    if p and p not in artifacts_touched:
                        artifacts_touched.append(p)
                results.append((use.id, use.name, output))
            messages = backend.append_tool_results(messages, results)
            continue

        log("warn", f"{role}: unexpected stop_reason={turn_result.stop_reason!r}; bailing")
        break
    else:
        log("warn", f"{role}: hit per-agent turn cap")

    handoff = parse_handoff(final_text)
    if not handoff:
        return AgentResult(
            role=role, artifacts=artifacts_touched, handoff_target="done",
            notes="agent ended without HANDOFF directive — assuming done",
        )
    target, note_out = handoff
    if target not in VALID_NEXT_ROLES:
        return AgentResult(
            role=role, artifacts=artifacts_touched, handoff_target="done",
            notes=f"agent emitted invalid HANDOFF target {target!r}; assuming done",
        )
    return AgentResult(
        role=role,
        artifacts=artifacts_touched,
        handoff_target=target,
        notes=note_out,
        user_question=note_out if target == "user" else None,
    )


def run_agent_stub(role: str, note: str, project_root: Path, ask_role: str | None = None) -> AgentResult:
    """Dry-run stub. Writes a marker file and hands off to the next role in the chain.

    `ask_role` (test-only): if set and matches the current role, return a
    HANDOFF: user once instead of advancing. The user's answer comes back as
    a note starting with `User answered`, so on the retry we proceed normally.
    """
    if ask_role and role == ask_role and not note.startswith("User answered"):
        return AgentResult(
            role=role,
            artifacts=[],
            handoff_target="user",
            notes=f"Stub question from {role}: what's the budget?",
            user_question=f"Stub question from {role}: what's the budget?",
        )
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
    # Test-only: in dry-run, force the named role to ask one user question.
    dry_run_ask_role = request.get("_dry_run_ask_role")

    # Backend selection is now per-role: each agent can run on a different
    # backend via LLM_BACKEND_<ROLE>. Global LLM_BACKEND is the fallback.
    # Backends are constructed lazily and cached so a hybrid run that uses
    # the same backend for several roles doesn't re-init the client.
    backend_cache: dict[str, Backend] = {}

    def get_backend(name: str) -> Backend:
        if name not in backend_cache:
            backend_cache[name] = make_backend(name)
        return backend_cache[name]

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
    # `last_role` tracks who ran the previous turn — needed so we can resume
    # the right agent after a HANDOFF: user → user_answer round-trip.
    last_role: str | None = None

    for iteration in range(MAX_ITERATIONS):
        if next_role == "done":
            emit("done", project_root=str(project_root), summary=note)
            return
        if next_role == "user":
            # The previously-spawned agent asked the user something.
            # Surface the question, then block on stdin for the user's answer.
            asker = last_role or "unknown"
            emit("user_question", role=asker, question=note)
            answer = _wait_for_user_answer()
            if answer is None:
                fatal("driver stdin closed while waiting for user_answer", code=3)
            # Resume the same role with the user's answer as the new note.
            log("info", f"resuming {asker} with user answer ({len(answer)} chars)")
            next_role = asker
            note = f"User answered your question:\n\n{answer}"
            continue

        role_file = agents_dir / f"{next_role}.md"
        if not role_file.is_file():
            fatal(f"agent file not found: {role_file}")

        emit("agent_started", role=next_role)
        role_text = role_file.read_text()

        try:
            if dry_run:
                result = run_agent_stub(next_role, note, project_root, ask_role=dry_run_ask_role)
            else:
                role_backend_name = backend_name_for_role(next_role)
                role_model = model_for_role(next_role, role_backend_name)
                role_backend = get_backend(role_backend_name)
                log("info", f"{next_role}: backend={role_backend_name} model={role_model}")
                result = run_agent_live(
                    role=next_role,
                    role_text=role_text,
                    team_brief=team_brief,
                    project_root=project_root,
                    note=note,
                    idea=idea,
                    backend=role_backend,
                    model=role_model,
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

        last_role = result.role
        next_role = result.handoff_target
        note = result.notes

    fatal(f"hit MAX_ITERATIONS={MAX_ITERATIONS} without reaching done")


def _wait_for_user_answer() -> str | None:
    """Block reading lines from stdin until a `user_answer` command arrives.

    Returns the answer string, or None if stdin closed first. Lines that
    aren't valid JSON or aren't a `user_answer` command are logged and
    skipped so the protocol stays forgiving.
    """
    while True:
        line = sys.stdin.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            log("warn", f"ignored non-JSON line on stdin: {e}")
            continue
        cmd = obj.get("command")
        if cmd == "user_answer" and isinstance(obj.get("answer"), str):
            return obj["answer"]
        if cmd == "cancel":
            return None
        log("warn", f"ignored unexpected command on stdin: {cmd!r}")


def main() -> int:
    # Load API keys / config from a standard non-committed file, if present.
    # The shell env still wins (setdefault semantics) so users who export
    # explicitly aren't surprised.
    loaded = load_keys_from_file()
    if loaded is not None:
        # Don't log the contents — just the path so the user knows which file
        # was picked up. Useful when debugging "why isn't my key working".
        log("info", f"loaded keys from {loaded}")

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
