#!/usr/bin/env bash
# QA runner for csv2json-service. Executes server unit tests, client unit tests,
# and an integration step (live uvicorn + live csv2json-client).
# Exits non-zero on any failure. Prints PASS/FAIL counts at the end.

set -u

ROOT="/Users/gokulpm/Claude/SWE/csv2json-service"
VENV="$ROOT/.venv-qa"
PYTEST="$VENV/bin/pytest"
UVICORN="$VENV/bin/uvicorn"
CLIENT="$VENV/bin/csv2json-client"
PYTHON="$VENV/bin/python"
SERVER_DIR="$ROOT/repo/server"
CLIENT_DIR="$ROOT/repo/client"
FIXTURES="$ROOT/reports/fixtures"
LOG_DIR="$ROOT/reports"

cd "$ROOT"

server_pytest_log="$LOG_DIR/server-pytest.log"
client_pytest_log="$LOG_DIR/client-pytest.log"
integration_log="$LOG_DIR/integration.log"
server_boot_log="$LOG_DIR/uvicorn.log"

overall_status=0

echo "==> Server pytest"
( cd "$SERVER_DIR" && "$PYTEST" tests -v ) | tee "$server_pytest_log"
server_rc=${PIPESTATUS[0]}
if [ "$server_rc" -ne 0 ]; then overall_status=1; fi

echo
echo "==> Client pytest"
( cd "$CLIENT_DIR" && "$PYTEST" tests -v ) | tee "$client_pytest_log"
client_rc=${PIPESTATUS[0]}
if [ "$client_rc" -ne 0 ]; then overall_status=1; fi

echo
echo "==> Integration: boot uvicorn, exercise live client"
: > "$integration_log"
: > "$server_boot_log"

PORT=8765
SERVER_URL="http://localhost:$PORT"

# Boot uvicorn in background. Server's app package lives at repo/server/app/,
# so cd to repo/server/ to ensure it's importable.
( cd "$SERVER_DIR" && "$UVICORN" app.main:app --host 127.0.0.1 --port "$PORT" >"$server_boot_log" 2>&1 ) &
UVICORN_PID=$!

cleanup() {
  if kill -0 "$UVICORN_PID" 2>/dev/null; then
    kill "$UVICORN_PID" 2>/dev/null || true
    wait "$UVICORN_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# Wait for the server to come up (max ~10s).
ready=0
for i in $(seq 1 50); do
  if "$PYTHON" - <<EOF >/dev/null 2>&1
import urllib.request, sys
try:
    r = urllib.request.urlopen("$SERVER_URL/healthz", timeout=0.5)
    sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
EOF
  then ready=1; break; fi
  sleep 0.2
done

integ_pass=0
integ_fail=0

record() {
  local label="$1"; local ok="$2"; local detail="$3"
  if [ "$ok" -eq 0 ]; then
    integ_pass=$((integ_pass+1))
    echo "  PASS  $label" | tee -a "$integration_log"
  else
    integ_fail=$((integ_fail+1))
    echo "  FAIL  $label  -- $detail" | tee -a "$integration_log"
  fi
}

if [ "$ready" -ne 1 ]; then
  echo "  FAIL  uvicorn did not become ready; see $server_boot_log" | tee -a "$integration_log"
  integ_fail=$((integ_fail+1))
  overall_status=1
else
  # 1) healthz
  hz=$("$PYTHON" - <<EOF 2>/dev/null
import urllib.request, sys
try:
    r = urllib.request.urlopen("$SERVER_URL/healthz", timeout=2)
    sys.stdout.write(r.read().decode())
except Exception as e:
    sys.exit(1)
EOF
)
  if [ "$hz" = '{"ok":true}' ]; then record "healthz returns {ok:true}" 0 ""; else record "healthz returns {ok:true}" 1 "got: $hz"; overall_status=1; fi

  # 2) Header-mode happy path
  out=$("$CLIENT" "$FIXTURES/basic.csv" --server "$SERVER_URL" 2>"$LOG_DIR/_e1.stderr")
  rc=$?
  expected='[{"name":"alice","age":"30"},{"name":"bob","age":"40"}]'
  if [ "$rc" -eq 0 ] && [ "$out" = "$expected" ]; then
    record "client basic.csv -> header mode JSON, exit 0" 0 ""
  else
    record "client basic.csv -> header mode JSON, exit 0" 1 "rc=$rc out=$out"
    overall_status=1
  fi

  # 3) no_header mode happy path
  out=$("$CLIENT" "$FIXTURES/no_header.csv" --server "$SERVER_URL" --no-header 2>"$LOG_DIR/_e2.stderr")
  rc=$?
  expected='[{"0":"alice","1":"30"},{"0":"bob","1":"40"}]'
  if [ "$rc" -eq 0 ] && [ "$out" = "$expected" ]; then
    record "client --no-header -> indexed JSON, exit 0" 0 ""
  else
    record "client --no-header -> indexed JSON, exit 0" 1 "rc=$rc out=$out"
    overall_status=1
  fi

  # 4) empty body -> exit 5 with empty_body
  out=$("$CLIENT" "$FIXTURES/empty.csv" --server "$SERVER_URL" 2>"$LOG_DIR/_e3.stderr")
  rc=$?
  err=$(cat "$LOG_DIR/_e3.stderr")
  if [ "$rc" -eq 5 ] && echo "$err" | grep -q "empty_body"; then
    record "client empty.csv -> exit 5 / empty_body" 0 ""
  else
    record "client empty.csv -> exit 5 / empty_body" 1 "rc=$rc stderr=$err"
    overall_status=1
  fi
fi

cleanup
trap - EXIT

echo
echo "==> Summary"

# Parse pytest summary lines for pass/fail counts.
parse_counts() {
  local log="$1"
  local p f
  # Capture the last "===" summary line emitted by pytest.
  local last
  last=$(grep -E '^=+ .*(passed|failed|error).* in [0-9.]+s' "$log" | tail -n 1)
  if [ -z "$last" ]; then echo "0 0"; return; fi
  p=$(echo "$last" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+' || true)
  f=$(echo "$last" | grep -oE '[0-9]+ (failed|error[s]?)' | grep -oE '[0-9]+' | head -n1 || true)
  [ -z "$p" ] && p=0
  [ -z "$f" ] && f=0
  echo "$p $f"
}

read sp sf <<<"$(parse_counts "$server_pytest_log")"
read cp cf <<<"$(parse_counts "$client_pytest_log")"

total_pass=$((sp + cp + integ_pass))
total_fail=$((sf + cf + integ_fail))

echo "  Server  : passed=$sp  failed=$sf"
echo "  Client  : passed=$cp  failed=$cf"
echo "  Integ.  : passed=$integ_pass  failed=$integ_fail"
echo "  TOTAL   : passed=$total_pass  failed=$total_fail"

if [ "$total_fail" -gt 0 ] || [ "$overall_status" -ne 0 ]; then
  echo "RESULT: FAIL"
  exit 1
fi
echo "RESULT: PASS"
exit 0
