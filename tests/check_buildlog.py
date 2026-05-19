#!/usr/bin/env python3
"""check_buildlog.py — verify a BUILD_LOG.json is well-formed per team-brief.

Schema (per team-brief.md):
  - Top-level is a JSON array.
  - Each entry is an object with keys: ts, role, action, artifacts, next_role, notes.
  - `role` and `next_role` are drawn from the team-brief role vocabulary.
  - `artifacts` is a list of strings (paths).
  - Entries are append-only — we can't verify history from a single snapshot,
    but we can verify that timestamps are monotonically non-decreasing if all
    entries share a parseable format.

Usage:
  check_buildlog.py <path/to/BUILD_LOG.json> [<another> ...]

With no arguments, runs against the smoke-test workspace if present.
Exit 0 = all logs clean, exit 1 = at least one failure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

VALID_ROLES = {
    "pm", "architect", "qa",
    "coder-cpp", "coder-backend", "coder-frontend", "coder-python",
}
VALID_NEXT_ROLES = VALID_ROLES | {"user", "done"}
REQUIRED_KEYS = {"ts", "role", "action", "artifacts", "next_role", "notes"}


def check_one(path: Path) -> list[str]:
    failures: list[str] = []
    if not path.is_file():
        return [f"{path}: file not found"]

    try:
        data = json.loads(path.read_text() or "[]")
    except json.JSONDecodeError as e:
        return [f"{path}: not valid JSON: {e}"]

    if not isinstance(data, list):
        return [f"{path}: top-level is not a JSON array"]

    prev_ts: str | None = None
    for i, entry in enumerate(data):
        loc = f"{path}#{i}"
        if not isinstance(entry, dict):
            failures.append(f"{loc}: entry is not an object")
            continue
        missing = REQUIRED_KEYS - entry.keys()
        if missing:
            failures.append(f"{loc}: missing keys: {sorted(missing)}")
        extra = set(entry.keys()) - REQUIRED_KEYS
        if extra:
            failures.append(f"{loc}: unexpected keys: {sorted(extra)}")

        role = entry.get("role")
        if role not in VALID_ROLES:
            failures.append(f"{loc}: role={role!r} not in {sorted(VALID_ROLES)}")
        nxt = entry.get("next_role")
        if nxt not in VALID_NEXT_ROLES:
            failures.append(f"{loc}: next_role={nxt!r} not in {sorted(VALID_NEXT_ROLES)}")

        artifacts = entry.get("artifacts")
        if not isinstance(artifacts, list) or not all(isinstance(p, str) for p in artifacts):
            failures.append(f"{loc}: artifacts must be a list of strings, got {type(artifacts).__name__}")

        ts = entry.get("ts")
        if not isinstance(ts, str):
            failures.append(f"{loc}: ts must be a string")
        else:
            if prev_ts is not None and ts < prev_ts:
                failures.append(f"{loc}: ts {ts!r} is earlier than previous {prev_ts!r}")
            prev_ts = ts

    return failures


def main(argv: list[str]) -> int:
    args = argv[1:]
    if not args:
        default = Path(__file__).resolve().parent.parent / "csv2json-smoke" / "BUILD_LOG.json"
        if default.is_file():
            args = [str(default)]
        else:
            print("check_buildlog: no logs to check (pass paths as arguments)")
            return 0

    all_failures: list[str] = []
    for p in args:
        all_failures.extend(check_one(Path(p)))

    if not all_failures:
        print(f"check_buildlog: PASS — {len(args)} log(s) clean")
        return 0

    for f in all_failures:
        print(f"  {f}")
    print(f"check_buildlog: FAIL — {len(all_failures)} issue(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
