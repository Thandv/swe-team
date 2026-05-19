#!/usr/bin/env python3
"""lint_agents.py — static checks for every adapted agent file in agents/.

Catches the regressions we've already hit once:
  - Frontmatter malformed or missing required keys.
  - Tool list using Claude-Code names instead of the portable capability vocab.
  - Team conventions section dropped.
  - Upstream "Query context manager" vestiges leaking back in.
  - Role file growing back over the size budget that caused our smoke-test timeout.

Run from anywhere; targets /Users/gokulpm/Claude/SWE/agents/ by default.
Exit 0 = clean, exit 1 = at least one failure.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / "agents"

EXPECTED_ROLES = {
    "pm",
    "architect",
    "qa",
    "coder-cpp",
    "coder-backend",
    "coder-frontend",
    "coder-python",
}
PORTABLE_CAPABILITIES = {"read", "edit", "shell", "web", "spawn"}
MAX_LINES_PER_AGENT = 150  # budget: smoke test failed at 300+

# Patterns we never want to see in the body of an adapted agent (the footer
# Team conventions section is allowed to mention "context manager" once, in
# the explicit override note).
BANNED_BODY_PATTERNS = [
    re.compile(r"\bQuery context manager\b", re.IGNORECASE),
    re.compile(r"\bcontext-manager\b"),
    re.compile(r'"requesting_agent"\s*:'),
    re.compile(r'"request_type"\s*:'),
]


@dataclass
class Finding:
    role: str
    severity: str  # "error" or "warn"
    message: str


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not match:
        return {}, text
    fm_raw, body = match.group(1), match.group(2)
    fm: dict[str, str] = {}
    for line in fm_raw.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        fm[key.strip()] = val.strip()
    return fm, body


def parse_tools(tools_value: str) -> list[str]:
    raw = tools_value.strip().strip("[]")
    return [c.strip().strip("'\"") for c in raw.split(",") if c.strip()]


def lint_file(path: Path) -> list[Finding]:
    role = path.stem
    findings: list[Finding] = []
    text = path.read_text()

    fm, body = parse_frontmatter(text)
    if not fm:
        findings.append(Finding(role, "error", "no frontmatter"))
        return findings

    if fm.get("name") != role:
        findings.append(Finding(
            role, "error",
            f"frontmatter name={fm.get('name')!r} does not match filename {role!r}"
        ))

    if not fm.get("description"):
        findings.append(Finding(role, "error", "frontmatter missing description"))

    tools_value = fm.get("tools")
    if not tools_value:
        findings.append(Finding(role, "error", "frontmatter missing tools"))
    else:
        caps = parse_tools(tools_value)
        for cap in caps:
            if cap not in PORTABLE_CAPABILITIES:
                findings.append(Finding(
                    role, "error",
                    f"tools contains {cap!r}; only portable capabilities allowed: "
                    f"{sorted(PORTABLE_CAPABILITIES)}"
                ))

    # Team conventions section must exist.
    if "## Team conventions" not in body:
        findings.append(Finding(role, "error", "missing '## Team conventions' section"))

    # Body must require a HANDOFF directive somewhere.
    if "HANDOFF:" not in body:
        findings.append(Finding(role, "error", "body does not mention HANDOFF protocol"))

    # Body must require BUILD_LOG.json append.
    if "BUILD_LOG.json" not in body:
        findings.append(Finding(role, "error", "body does not mention BUILD_LOG.json"))

    # Banned upstream-isms anywhere outside the explicit override mention.
    # We allow exactly one mention inside the "overrides any conflicting habits"
    # sentence in the Team conventions footer.
    override_marker = 'JSON "context manager" handshakes'
    for pat in BANNED_BODY_PATTERNS:
        for m in pat.finditer(body):
            ctx_start = max(0, m.start() - 80)
            ctx_end = min(len(body), m.end() + 80)
            ctx = body[ctx_start:ctx_end]
            if override_marker in ctx:
                continue  # allowed in the override-note context
            line_no = body[: m.start()].count("\n") + 1
            findings.append(Finding(
                role, "error",
                f"banned upstream-ism {pat.pattern!r} at body line {line_no}"
            ))

    # Size budget.
    line_count = text.count("\n") + (0 if text.endswith("\n") else 1)
    if line_count > MAX_LINES_PER_AGENT:
        findings.append(Finding(
            role, "error",
            f"{line_count} lines exceeds budget of {MAX_LINES_PER_AGENT}; "
            f"the verbose upstream content belongs in agents/upstream/"
        ))

    return findings


def main() -> int:
    if not AGENTS_DIR.is_dir():
        print(f"FAIL: agents dir not found: {AGENTS_DIR}", file=sys.stderr)
        return 1

    found_roles: set[str] = set()
    all_findings: list[Finding] = []

    for path in sorted(AGENTS_DIR.glob("*.md")):
        if path.parent.name == "upstream":
            continue
        found_roles.add(path.stem)
        all_findings.extend(lint_file(path))

    missing = EXPECTED_ROLES - found_roles
    extra = found_roles - EXPECTED_ROLES
    for role in sorted(missing):
        all_findings.append(Finding(role, "error", "expected role file is missing"))
    for role in sorted(extra):
        all_findings.append(Finding(role, "warn", "unexpected role file (not in EXPECTED_ROLES)"))

    errors = [f for f in all_findings if f.severity == "error"]
    warns = [f for f in all_findings if f.severity == "warn"]

    if not all_findings:
        print(f"lint_agents: PASS — {len(found_roles)} agent files clean")
        return 0

    for f in all_findings:
        print(f"  [{f.severity:5}] {f.role}: {f.message}")
    print(f"lint_agents: {len(errors)} error(s), {len(warns)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
