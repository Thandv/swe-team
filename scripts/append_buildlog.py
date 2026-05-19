#!/usr/bin/env python3
"""Atomic append to a project's BUILD_LOG.json.

Why this exists
---------------
Agents that run in parallel (typically multiple coders working on disjoint
subtrees) both want to append a row to BUILD_LOG.json at the end of their
turn. The naive read-parse-append-write cycle is racy: two processes can
read the same prefix and each overwrite the other's update. This helper
takes an exclusive fcntl lock for the read-modify-write window so concurrent
callers serialize cleanly.

Usage
-----
Direct CLI:

    append_buildlog.py <project-root> <role> <action> <artifacts-json> <next-role> <notes>

where `artifacts-json` is a JSON array of relative paths. Example:

    append_buildlog.py /path/to/proj coder-backend "implemented server" \\
        '["repo/server/app/main.py","repo/server/README.md"]' \\
        qa "service ready; run with uvicorn"

The script writes a single line to stdout on success: the new total entry
count. Exits non-zero on bad input. Safe to call from multiple processes
concurrently.

Library use
-----------
    from append_buildlog import append_entry
    append_entry(project_root, role, action, artifacts, next_role, notes)
"""

from __future__ import annotations

import fcntl
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_ROLES = {
    "pm", "architect", "qa",
    "coder-cpp", "coder-backend", "coder-frontend", "coder-python",
}
VALID_NEXT_ROLES = VALID_ROLES | {"user", "done"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_entry(
    project_root: Path | str,
    role: str,
    action: str,
    artifacts: list[str],
    next_role: str,
    notes: str,
) -> int:
    """Atomically append one row to <project_root>/BUILD_LOG.json. Returns total row count."""
    if role not in VALID_ROLES:
        raise ValueError(f"role must be one of {sorted(VALID_ROLES)}, got {role!r}")
    if next_role not in VALID_NEXT_ROLES:
        raise ValueError(f"next_role must be one of {sorted(VALID_NEXT_ROLES)}, got {next_role!r}")
    if not isinstance(artifacts, list) or not all(isinstance(p, str) for p in artifacts):
        raise ValueError("artifacts must be a list of strings")

    log_path = Path(project_root) / "BUILD_LOG.json"
    # Ensure the file exists so we can lock on it.
    log_path.touch(exist_ok=True)

    new_entry: dict[str, Any] = {
        "ts": _now_iso(),
        "role": role,
        "action": action,
        "artifacts": artifacts,
        "next_role": next_role,
        "notes": notes,
    }

    with log_path.open("r+") as f:
        # Block until we get an exclusive lock. fcntl locks are released when
        # the fd is closed (i.e. when we exit this `with` block).
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.seek(0)
        raw = f.read() or "[]"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Corrupted log — start fresh rather than blow up.
            data = []
        if not isinstance(data, list):
            data = []
        data.append(new_entry)
        f.seek(0)
        f.truncate()
        f.write(json.dumps(data, indent=2))
        f.write("\n")
        # Lock is released by the `with` exit.
    return len(data)


def main(argv: list[str]) -> int:
    if len(argv) != 7:
        print(
            "usage: append_buildlog.py <project-root> <role> <action> "
            "<artifacts-json> <next-role> <notes>",
            file=sys.stderr,
        )
        return 2
    _, project_root, role, action, artifacts_json, next_role, notes = argv
    try:
        artifacts = json.loads(artifacts_json)
    except json.JSONDecodeError as e:
        print(f"bad artifacts JSON: {e}", file=sys.stderr)
        return 2
    try:
        count = append_entry(project_root, role, action, artifacts, next_role, notes)
    except (ValueError, OSError) as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(count)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
