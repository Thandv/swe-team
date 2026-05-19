"""Test the bidirectional user-question round trip in the driver protocol."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

DRIVER = Path(__file__).resolve().parent.parent / "orchestrator_driver.py"
SWE_ROOT = Path(__file__).resolve().parents[3]


def test_user_question_round_trip(tmp_path: Path) -> None:
    """The PM stub asks one question; we answer; the team finishes."""
    request = {
        "command": "build",
        "idea": "anything bounded",
        "swe_root": str(SWE_ROOT),
        "parent_dir": str(tmp_path),
        "dry_run": True,
        "_dry_run_ask_role": "pm",
    }
    answer = {"command": "user_answer", "answer": "the budget is $100"}

    # Driver reads two stdin lines: the initial build request, then the
    # user_answer when prompted. We feed both up front and close stdin.
    stdin = json.dumps(request) + "\n" + json.dumps(answer) + "\n"
    proc = subprocess.run(
        [sys.executable, str(DRIVER)],
        input=stdin, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, f"driver exited {proc.returncode}\nstderr:\n{proc.stderr}"

    events = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    types = [e["event"] for e in events]

    # Must include a user_question event sourced from PM.
    questions = [e for e in events if e["event"] == "user_question"]
    assert len(questions) == 1, f"expected exactly one user_question, got {len(questions)}"
    assert questions[0]["role"] == "pm", f"question came from {questions[0]['role']!r}"
    assert "Stub question" in questions[0]["question"]

    # PM should have been re-started after the answer (two pm starts total).
    pm_starts = [e for e in events if e.get("event") == "agent_started" and e.get("role") == "pm"]
    assert len(pm_starts) == 2, f"expected pm to be re-spawned after answer; got {len(pm_starts)} starts"

    # And the chain must finish.
    assert types[-1] == "done", f"chain did not finish: tail={types[-3:]}"


def test_stdin_close_during_question_fails_cleanly(tmp_path: Path) -> None:
    """If the UI dies while we're waiting on an answer, exit code 3."""
    request = {
        "command": "build",
        "idea": "x",
        "swe_root": str(SWE_ROOT),
        "parent_dir": str(tmp_path),
        "dry_run": True,
        "_dry_run_ask_role": "pm",
    }
    # Only send the build request; close stdin without ever providing an answer.
    proc = subprocess.run(
        [sys.executable, str(DRIVER)],
        input=json.dumps(request) + "\n", capture_output=True, text=True, timeout=10,
    )
    assert proc.returncode == 3, f"expected exit 3 on stdin-close mid-question; got {proc.returncode}"


def test_cancel_command_aborts(tmp_path: Path) -> None:
    request = {
        "command": "build",
        "idea": "x",
        "swe_root": str(SWE_ROOT),
        "parent_dir": str(tmp_path),
        "dry_run": True,
        "_dry_run_ask_role": "pm",
    }
    cancel = {"command": "cancel"}
    stdin = json.dumps(request) + "\n" + json.dumps(cancel) + "\n"
    proc = subprocess.run(
        [sys.executable, str(DRIVER)],
        input=stdin, capture_output=True, text=True, timeout=10,
    )
    assert proc.returncode == 3
