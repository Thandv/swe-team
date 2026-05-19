"""Protocol-level tests for the driver. Use dry_run so no API key is needed."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

DRIVER = Path(__file__).resolve().parent.parent / "orchestrator_driver.py"
SWE_ROOT = Path(__file__).resolve().parents[3]


def run_driver(request: dict) -> list[dict]:
    proc = subprocess.run(
        [sys.executable, str(DRIVER)],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        timeout=30,
    )
    events: list[dict] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        events.append(json.loads(line))
    if proc.returncode != 0:
        events.append({"event": "_exit", "code": proc.returncode, "stderr": proc.stderr})
    return events


def test_dry_run_completes(tmp_path: Path) -> None:
    events = run_driver({
        "command": "build",
        "idea": "a tiny test idea",
        "swe_root": str(SWE_ROOT),
        "parent_dir": str(tmp_path),
        "dry_run": True,
    })

    types = [e["event"] for e in events]
    assert "project_initialized" in types
    assert types.count("agent_started") >= 4  # pm, architect, coder, qa at minimum
    assert types[-1] == "done", f"chain did not finish: {types}"


def test_dry_run_writes_workspace(tmp_path: Path) -> None:
    events = run_driver({
        "command": "build",
        "idea": "another test idea",
        "swe_root": str(SWE_ROOT),
        "parent_dir": str(tmp_path),
        "dry_run": True,
    })
    init = next(e for e in events if e["event"] == "project_initialized")
    project_root = Path(init["project_root"])
    assert project_root.is_dir()
    for sub in ("specs", "design", "repo", "binaries", "reports"):
        assert (project_root / sub).is_dir(), f"missing {sub}/"
    assert (project_root / "specs" / "idea.md").is_file()
    assert (project_root / "BUILD_LOG.json").is_file()
    # BUILD_LOG must have entries the orchestrator appended per agent.
    log = json.loads((project_root / "BUILD_LOG.json").read_text())
    assert len(log) >= 4
    for entry in log:
        assert set(entry.keys()) == {"ts", "role", "action", "artifacts", "next_role", "notes"}


def test_bad_request_returns_2(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(DRIVER)],
        input="not json at all",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 2


def test_missing_field_returns_2(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(DRIVER)],
        input=json.dumps({"command": "build", "idea": "x"}),  # missing swe_root, parent_dir
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 2
