#!/usr/bin/env python3
"""Test the atomic BUILD_LOG append helper, including the parallel-write race
condition that motivated its existence.

Runs as a normal pytest module, but is invoked from tests/run_all.sh too
(without pytest) by being importable and runnable as a script.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "append_buildlog.py"

sys.path.insert(0, str(ROOT / "scripts"))
from append_buildlog import append_entry  # noqa: E402


def _read_log(project: Path) -> list[dict]:
    return json.loads((project / "BUILD_LOG.json").read_text())


def test_single_append() -> None:
    with tempfile.TemporaryDirectory() as td:
        proj = Path(td)
        append_entry(proj, "pm", "wrote brief", ["specs/brief.md"], "architect", "test note")
        data = _read_log(proj)
        assert len(data) == 1
        assert data[0]["role"] == "pm"
        assert data[0]["next_role"] == "architect"
        assert data[0]["artifacts"] == ["specs/brief.md"]


def test_cli_invocation() -> None:
    with tempfile.TemporaryDirectory() as td:
        proj = Path(td)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT),
             str(proj), "architect", "wrote design",
             '["design/system.md","design/contracts.md"]',
             "coder-python", "two designs landed"],
            capture_output=True, text=True, timeout=10,
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "1"
        data = _read_log(proj)
        assert len(data) == 1
        assert data[0]["artifacts"] == ["design/system.md", "design/contracts.md"]


def test_rejects_invalid_role() -> None:
    with tempfile.TemporaryDirectory() as td:
        proj = Path(td)
        try:
            append_entry(proj, "not-a-role", "x", [], "done", "")
        except ValueError as e:
            assert "role" in str(e)
        else:
            raise AssertionError("expected ValueError for invalid role")


def test_parallel_appends_no_lost_writes() -> None:
    """The motivating bug: parallel coders racing on the read-modify-write of
    BUILD_LOG.json. We fire 20 concurrent appends from a thread pool and
    verify every one of them landed."""
    with tempfile.TemporaryDirectory() as td:
        proj = Path(td)
        n = 20

        def worker(i: int) -> int:
            return append_entry(
                proj, "coder-python", f"action {i}",
                [f"repo/file_{i}.py"], "qa", f"note {i}",
            )

        with ThreadPoolExecutor(max_workers=n) as pool:
            list(pool.map(worker, range(n)))

        data = _read_log(proj)
        assert len(data) == n, f"expected {n} entries, got {len(data)}"
        actions = sorted(e["action"] for e in data)
        assert actions == sorted(f"action {i}" for i in range(n)), \
            f"some entries were lost: {actions}"


def test_parallel_subprocesses_no_lost_writes() -> None:
    """Same as above but using actual subprocesses to exercise the fcntl path
    end-to-end (Python threads share the GIL; subprocesses don't)."""
    with tempfile.TemporaryDirectory() as td:
        proj = Path(td)
        n = 10
        procs = []
        for i in range(n):
            procs.append(subprocess.Popen(
                [sys.executable, str(SCRIPT),
                 str(proj), "coder-backend", f"sub action {i}",
                 '[]', "qa", f"sub note {i}"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            ))
        for p in procs:
            rc = p.wait(timeout=10)
            assert rc == 0, p.stderr.read().decode() if p.stderr else "no stderr"
        data = _read_log(proj)
        assert len(data) == n


if __name__ == "__main__":
    # Allow running directly without pytest, since tests/run_all.sh prefers
    # not to depend on pytest being installed for the static checks.
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  {name}: PASS")
            except Exception as e:  # noqa: BLE001
                print(f"  {name}: FAIL — {type(e).__name__}: {e}")
                sys.exit(1)
    print("test_append_buildlog: all pass")
