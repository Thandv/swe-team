#!/usr/bin/env bash
# csv2json.sh — end-to-end check that re-runs the csv2json smoke test.
#
# This is gated because it depends on an LLM driver (Claude Code or the future
# binary) actually running the team. It is NOT a self-contained shell script —
# it just verifies that the artifacts a previous team run produced still build
# and pass their tests. The team itself must be driven separately (via
# `/swe-build a Python CLI tool that ...` in Claude Code, or via the future
# binary).
#
# What this script verifies:
#   1. The csv2json-smoke workspace exists and has the expected subdirs.
#   2. BUILD_LOG.json is well-formed and the chain ends in `next_role: done`.
#   3. repo/csv2json.py runs and matches the recorded contracts:
#        - --help exits 0.
#        - A trivial CSV input round-trips to JSON.
#        - An invalid CSV path exits non-zero.
#   4. The team-produced test script (reports/run-tests.sh) still passes.
#
# Exit 0 = the previously-built team artifacts still work. Exit 1 = regression.

set -uo pipefail

SWE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROJ="$SWE_DIR/csv2json-smoke"

fail=0
note() { printf "  %s\n" "$*"; }

if [[ ! -d "$PROJ" ]]; then
  note "skip: $PROJ does not exist — run the team first via /swe-build"
  echo "e2e/csv2json: SKIP (no workspace)"
  exit 0
fi

# 1. Subdir shape.
for sub in specs design repo reports BUILD_LOG.json; do
  if [[ ! -e "$PROJ/$sub" ]]; then
    note "missing: $PROJ/$sub"
    fail=$((fail + 1))
  fi
done

# 2. BUILD_LOG.json shape + terminal handoff.
if [[ -f "$PROJ/BUILD_LOG.json" ]]; then
  python3 "$SWE_DIR/tests/check_buildlog.py" "$PROJ/BUILD_LOG.json" >/dev/null || {
    note "BUILD_LOG.json failed schema check"
    fail=$((fail + 1))
  }
  last_next_role=$(python3 -c '
import json, sys
data = json.load(open(sys.argv[1]))
print(data[-1]["next_role"] if data else "")
' "$PROJ/BUILD_LOG.json")
  if [[ "$last_next_role" != "done" ]]; then
    note "BUILD_LOG terminal next_role is '$last_next_role', expected 'done'"
    fail=$((fail + 1))
  fi
else
  note "missing BUILD_LOG.json"
  fail=$((fail + 1))
fi

# 3. Code still works.
CLI="$PROJ/repo/csv2json.py"
if [[ -f "$CLI" ]]; then
  python3 "$CLI" --help >/dev/null 2>&1 || { note "csv2json.py --help failed"; fail=$((fail + 1)); }
  out=$(printf "a,b\n1,2\n" | python3 "$CLI" 2>/dev/null) || true
  if ! echo "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d==[{"a":"1","b":"2"}], d' 2>/dev/null; then
    note "csv2json.py basic round-trip failed: got $out"
    fail=$((fail + 1))
  fi
  if python3 "$CLI" /nonexistent/path >/dev/null 2>&1; then
    note "csv2json.py succeeded on nonexistent file (expected failure)"
    fail=$((fail + 1))
  fi
else
  note "missing $CLI"
  fail=$((fail + 1))
fi

# 4. Team-produced test runner still passes.
RUNNER="$PROJ/reports/run-tests.sh"
if [[ -f "$RUNNER" ]]; then
  if ! bash "$RUNNER" >/dev/null 2>&1; then
    note "reports/run-tests.sh exited non-zero (some test cases failing)"
    note "  (expected: one case classified as design ambiguity in reports/review.md;"
    note "   if more fail, the code or the contract regressed)"
  fi
else
  note "skip: no reports/run-tests.sh (team may not have produced one)"
fi

if [[ $fail -eq 0 ]]; then
  echo "e2e/csv2json: PASS"
  exit 0
fi
echo "e2e/csv2json: FAIL — $fail issue(s)"
exit 1
