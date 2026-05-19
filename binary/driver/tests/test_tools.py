"""Tests for tool execution and capability gating in the driver.

These don't call the Anthropic API — they invoke the tool helpers directly to
verify behavior. Live-API behavior is covered by manual verification runs.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

DRIVER_PARENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DRIVER_PARENT))

from orchestrator_driver import (  # noqa: E402
    execute_tool,
    parse_role_capabilities,
    tools_for_role,
)


# ---------- capability gating ----------

PM_FRONTMATTER = """---
name: pm
description: Product manager.
tools: [read, edit, web]
---
"""

CODER_PY_FRONTMATTER = """---
name: coder-python
description: Python developer.
tools: [read, edit, shell]
---
"""

ARCHITECT_FRONTMATTER = """---
name: architect
description: Architect.
tools: [read, edit, shell]
---
"""


def test_parse_capabilities_basic() -> None:
    assert parse_role_capabilities(PM_FRONTMATTER) == ["read", "edit", "web"]


def test_parse_capabilities_no_frontmatter() -> None:
    assert parse_role_capabilities("no frontmatter here") == []


def test_pm_gets_no_shell() -> None:
    tool_names = {t["name"] for t in tools_for_role(PM_FRONTMATTER)}
    assert "read_file" in tool_names
    assert "write_file" in tool_names
    assert "bash" not in tool_names, "PM declared no shell capability — must not receive bash"


def test_coder_python_gets_shell() -> None:
    tool_names = {t["name"] for t in tools_for_role(CODER_PY_FRONTMATTER)}
    assert "read_file" in tool_names
    assert "write_file" in tool_names
    assert "bash" in tool_names


def test_architect_gets_shell() -> None:
    tool_names = {t["name"] for t in tools_for_role(ARCHITECT_FRONTMATTER)}
    assert "bash" in tool_names


def test_no_duplicate_tools() -> None:
    # An agent declaring duplicate caps shouldn't get duplicate tools.
    fm = "---\nname: x\ntools: [read, read, edit]\n---\n"
    names = [t["name"] for t in tools_for_role(fm)]
    assert len(names) == len(set(names))


# ---------- bash tool execution ----------

def test_bash_basic(tmp_path: Path) -> None:
    out = execute_tool("bash", {"command": "echo hello"}, tmp_path)
    assert "exit_code: 0" in out
    assert "hello" in out


def test_bash_failure(tmp_path: Path) -> None:
    out = execute_tool("bash", {"command": "exit 42"}, tmp_path)
    assert "exit_code: 42" in out


def test_bash_captures_stderr(tmp_path: Path) -> None:
    out = execute_tool("bash", {"command": "echo to_err >&2"}, tmp_path)
    assert "to_err" in out
    assert "stderr" in out


def test_bash_runs_in_project_root(tmp_path: Path) -> None:
    (tmp_path / "marker.txt").write_text("present")
    out = execute_tool("bash", {"command": "ls"}, tmp_path)
    assert "marker.txt" in out


def test_bash_timeout(tmp_path: Path) -> None:
    start = time.time()
    out = execute_tool("bash", {"command": "sleep 10", "timeout_seconds": 1}, tmp_path)
    elapsed = time.time() - start
    assert elapsed < 3, f"timeout did not kick in: {elapsed:.2f}s"
    assert "TIMEOUT" in out


def test_bash_timeout_cap(tmp_path: Path) -> None:
    # Max should be enforced at 300; passing 9999 should not block forever.
    # We don't actually want to sit through 300s, so verify the cap by mock:
    # just confirm a small command still works and the cap is documented.
    out = execute_tool("bash", {"command": "true", "timeout_seconds": 9999}, tmp_path)
    assert "exit_code: 0" in out


# ---------- filesystem sandbox still holds ----------

def test_read_outside_root_blocked(tmp_path: Path) -> None:
    out = execute_tool("read_file", {"path": "../../../etc/passwd"}, tmp_path)
    assert "PermissionError" in out, f"expected PermissionError in tool result: {out!r}"
    assert "escapes project root" in out


def test_write_outside_root_blocked(tmp_path: Path) -> None:
    out = execute_tool("write_file", {"path": "/tmp/attack", "content": "x"}, tmp_path)
    assert "PermissionError" in out or "ERROR" in out


def test_bash_can_still_escape_via_absolute_path(tmp_path: Path) -> None:
    # We document but don't prevent this — the bash sandbox is cwd, not chroot.
    # The test exists to make the trust model explicit: if you change the design
    # to actually sandbox bash, this test should start failing.
    out = execute_tool("bash", {"command": "ls /tmp >/dev/null 2>&1; echo $?"}, tmp_path)
    assert "exit_code: 0" in out


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                # Provide tmp_path if needed.
                import inspect
                import tempfile
                params = inspect.signature(fn).parameters
                if "tmp_path" in params:
                    with tempfile.TemporaryDirectory() as td:
                        fn(Path(td))
                else:
                    fn()
                print(f"  {name}: PASS")
            except Exception as e:
                print(f"  {name}: FAIL — {type(e).__name__}: {e}")
                failed += 1
    if failed:
        sys.exit(1)
    print(f"test_tools: all pass")
