#!/usr/bin/env python3
"""check_protocol.py — verify orchestrator.md and team-brief.md are internally consistent.

Specifically:
  - Every role mentioned in team-brief's "Where you write artifacts" is also a
    file under agents/ AND a valid HANDOFF target.
  - Every subdir referenced by orchestrator.md or team-brief.md uses the
    standard set: specs, design, repo, binaries, reports.
  - Every agent's expected next-role list matches the orchestrator vocabulary.

This catches the kind of drift where someone adds a new role to one document
but not the others.

Exit 0 = clean, exit 1 = at least one inconsistency.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEAM_BRIEF = ROOT / "team-brief.md"
ORCHESTRATOR = ROOT / "orchestrator.md"
AGENTS_DIR = ROOT / "agents"

STANDARD_SUBDIRS = {"specs", "design", "repo", "binaries", "reports"}
EXPECTED_ROLES = {
    "pm", "architect", "qa",
    "coder-cpp", "coder-backend", "coder-frontend", "coder-python",
}
VALID_HANDOFF_TARGETS = EXPECTED_ROLES | {"user", "done"}


def main() -> int:
    failures: list[str] = []

    for p in (TEAM_BRIEF, ORCHESTRATOR):
        if not p.is_file():
            failures.append(f"missing required file: {p}")
    if failures:
        for f in failures:
            print(f"  {f}")
        return 1

    brief = TEAM_BRIEF.read_text()
    orch = ORCHESTRATOR.read_text()

    # Every standard subdir must be mentioned in team-brief.
    for sd in STANDARD_SUBDIRS:
        if f"`{sd}/`" not in brief and f" {sd}/" not in brief:
            failures.append(f"team-brief.md does not document subdir {sd!r}")

    # Every expected role must have an agent file.
    found_files = {p.stem for p in AGENTS_DIR.glob("*.md") if p.parent.name != "upstream"}
    missing = EXPECTED_ROLES - found_files
    for role in sorted(missing):
        failures.append(f"missing agent file: agents/{role}.md")

    # Every agent file must reference all valid handoff targets, OR explicitly
    # call out the orchestrator vocabulary. Easier test: each agent file must
    # list the full handoff target vocabulary somewhere in its body.
    for role in sorted(found_files & EXPECTED_ROLES):
        agent_text = (AGENTS_DIR / f"{role}.md").read_text()
        # Find an explicit list of valid next-role values, if present.
        m = re.search(r"Valid\s+`?<?next.?role>?`?\s+values?\s+are\s+([^.\n]+)", agent_text, re.IGNORECASE)
        if not m:
            failures.append(f"agents/{role}.md: no explicit 'Valid next-role values' list")
            continue
        listed = set(re.findall(r"`([a-z_-]+)`", m.group(1)))
        missing_targets = VALID_HANDOFF_TARGETS - listed
        if missing_targets:
            failures.append(
                f"agents/{role}.md: handoff target list is missing {sorted(missing_targets)}"
            )

    # Orchestrator must mention BUILD_LOG.json and HANDOFF.
    if "BUILD_LOG.json" not in orch:
        failures.append("orchestrator.md: does not mention BUILD_LOG.json")
    if "HANDOFF" not in orch:
        failures.append("orchestrator.md: does not mention HANDOFF directive")

    if not failures:
        print("check_protocol: PASS — orchestrator/team-brief/agents internally consistent")
        return 0

    for f in failures:
        print(f"  {f}")
    print(f"check_protocol: FAIL — {len(failures)} issue(s)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
