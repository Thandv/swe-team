# Build Plan — csv2json-service

Two coders work in parallel against `design/contracts.md`. They touch disjoint directory trees and never import from each other.

## File ownership

| Path | Owner | Notes |
| --- | --- | --- |
| `repo/server/**` | `coder-backend` | FastAPI app, tests, pyproject |
| `repo/client/**` | `coder-python` | CLI, tests, pyproject, entry point |
| `binaries/server/` | `coder-backend` | run script / wheel if produced |
| `binaries/client/` | `coder-python` | wheel + `csv2json-client` script |
| `design/**` | architect (read-only for coders) | |
| `reports/**` | QA | |

No file is written by both coders. No cross-imports.

## coder-backend — server track

Goal: a runnable FastAPI service that satisfies `contracts.md` end-to-end.

Deliverables:
1. `repo/server/pyproject.toml` — deps: `fastapi`, `uvicorn[standard]`; dev: `pytest`, `httpx` (only if needed beyond TestClient).
2. `repo/server/app/main.py` — FastAPI app, routes `POST /convert` and `GET /healthz`, exception handler that maps `CsvError` → JSON error body with the right status.
3. `repo/server/app/convert.py` — `csv_to_records(text, no_header)` per `system.md`. Uses stdlib `csv`.
4. `repo/server/app/errors.py` — `CsvError` and code constants.
5. `repo/server/app/schemas.py` — `ErrorBody` pydantic model (for OpenAPI; runtime returns plain dicts).
6. `repo/server/tests/test_convert.py` — unit tests covering: header/no-header, empty, header-only, ragged rows, extra columns, quoted fields with embedded commas/newlines, malformed CSV raises `CsvError`.
7. `repo/server/tests/test_http.py` — TestClient tests covering each row in the contract's status/error table (200 happy path × 2 modes, 400 empty, 400 malformed, 400 wrong_query, 415 wrong_content_type, healthz 200).
8. `repo/server/README.md` — `pip install -e .` then `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

Acceptance: `pytest` green from `repo/server/`. `curl` examples from contract produce the expected bodies.

## coder-python — client track

Goal: a `csv2json-client` CLI on `$PATH` that satisfies `contracts.md` end-to-end.

Deliverables:
1. `repo/client/pyproject.toml` — no runtime deps; `[project.scripts] csv2json-client = "csv2json_client.cli:main"`; dev: `pytest`.
2. `repo/client/csv2json_client/cli.py` — argparse, file read, calls `http_client.post_csv`, formats output and stderr/exit codes per contract.
3. `repo/client/csv2json_client/http_client.py` — `post_csv(server, csv_bytes, no_header) -> HttpResult` using `urllib.request`. Catches `URLError`, `socket.timeout`, `ConnectionError` and re-raises a typed `NetworkError` for the CLI layer.
4. `repo/client/tests/test_cli.py` — uses `pytest` + a tiny stdlib `http.server.ThreadingHTTPServer` fixture (or `unittest.mock` against `http_client`) to cover: success print-through, `--no-header` query param, file-not-found exit 3, connection-refused exit 4, server-error exit 5 with parsed JSON body, server-error exit 5 with non-JSON body, `--server` URL trailing-slash handling.
5. `repo/client/README.md` — `pip install -e .` then `csv2json-client path/to/file.csv`.
6. `binaries/client/` — best-effort: `pip wheel . -w ../../binaries/client/` so a wheel is dropped for QA.

Acceptance: `pytest` green from `repo/client/`. Manual smoke against the live server matches contract examples.

## Parallelism guarantee

- Coders never edit each other's files. Their `pyproject.toml`s are independent; their tests are independent.
- The only shared surface is `design/contracts.md`. If a coder finds it ambiguous, they HANDOFF back to architect rather than guessing.
- Either coder can finish first; QA will block until both are done.

## How QA verifies both ends

QA writes `reports/test-plan.md` and `reports/results.md` covering:

1. **Server-only checks** (`repo/server/` tests pass):
   - Run `pytest` in `repo/server/`. Record pass/fail counts.
   - Boot server: `uvicorn app.main:app --port 8000 &`. Hit `GET /healthz` → expect `{"ok": true}`.
   - For each row of the contract's status table, fire a `curl` and verify status + JSON body shape (`error`, `code`, `detail` keys present; `code` matches).

2. **Client-only checks** (`repo/client/` tests pass):
   - Run `pytest` in `repo/client/`. Record pass/fail counts.
   - With server **down**, run `csv2json-client some.csv` → expect exit 4 and stderr mentions the server URL.
   - Run with a path that doesn't exist → expect exit 3.
   - Run `csv2json-client --help` → argparse usage printed, exit 0.

3. **End-to-end** (both alive):
   - Start server.
   - `csv2json-client fixture.csv` → stdout is valid JSON matching what the server returns for that body; exit 0.
   - `csv2json-client fixture.csv --no-header` → keys are `"0","1",...`.
   - Feed an empty file → exit 5, stderr contains `empty_body`.
   - Feed a malformed CSV (e.g. unbalanced quote) → exit 5, stderr contains `malformed_csv`.

4. **Contract conformance check**:
   - Diff QA's observed error bodies against `design/contracts.md` error table. Any drift = HANDOFF back to the responsible coder.

QA fixtures live under `reports/fixtures/` (QA-owned) so neither coder is blocked on test data.

## Done criteria

- Both `pytest` suites green.
- All contract rows demonstrated end-to-end.
- `BUILD_LOG.json` has entries from both coders and from QA.
- `reports/results.md` exists with pass/fail summary and any deviations called out.
