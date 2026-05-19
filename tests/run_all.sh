#!/usr/bin/env bash
# run_all.sh — run the team's static test suite.
#
# Static checks only — no API calls, no LLM spawns. Safe to run on every commit
# and in CI. The end-to-end smoke test lives at tests/e2e/csv2json.sh and is
# gated behind --e2e because it costs tokens.
#
# Usage:
#   tests/run_all.sh           # static checks only
#   tests/run_all.sh --e2e     # static checks plus the gated end-to-end

set -uo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_E2E=0
for arg in "$@"; do
  case "$arg" in
    --e2e) RUN_E2E=1 ;;
    -h|--help)
      echo "Usage: $0 [--e2e]"
      exit 0
      ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

fail=0
run() {
  local name="$1"; shift
  echo "=== $name ==="
  if "$@"; then
    echo
  else
    echo "  ↑ FAILED"
    echo
    fail=$((fail + 1))
  fi
}

run "lint_agents.py"     python3 "$TESTS_DIR/lint_agents.py"
run "check_install.sh"   bash    "$TESTS_DIR/check_install.sh"
run "check_buildlog.py"  python3 "$TESTS_DIR/check_buildlog.py"
run "check_protocol.py"  python3 "$TESTS_DIR/check_protocol.py"

if [[ $RUN_E2E -eq 1 ]]; then
  run "e2e/csv2json.sh"  bash "$TESTS_DIR/e2e/csv2json.sh"
fi

if [[ $fail -eq 0 ]]; then
  echo "run_all: PASS"
  exit 0
fi
echo "run_all: FAIL — $fail check(s) failed"
exit 1
