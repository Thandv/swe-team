# Architect Review — csv2json-service

**Verdict: CLEAN — ship it.**

## Scope of this pass
Skim of `repo/server/app/` and `repo/client/csv2json_client/`; cross-checked against `design/contracts.md`; confirmed QA's 43/43 in `reports/results.md`.

## Contract conformance

Every row in `design/contracts.md` is implemented and exercised:

- `POST /convert` Content-Type accepts `text/csv` with parameters (case-insensitive primary type) — `main._check_content_type` does `split(";",1)[0].strip().lower()`. Correct.
- `no_header` query parsing is case-insensitive `true`/`false`; anything else raises `400 wrong_query` — `main._parse_no_header`. Correct.
- Empty body → `400 empty_body`; UTF-8 decode failure → `400 malformed_csv`; `csv.Error` → `400 malformed_csv`; unhandled exception → `500 internal` via FastAPI exception handler with no leaked detail. Correct.
- Header mode: ragged rows omit missing keys (`if i < len(row): obj[key] = row[i]`); extra cells dropped (loop bounded by header). Header-only CSV → `[]` (rows[1:] empty). Correct.
- `no_header=true`: per-row width preserved via `enumerate(row)`. Correct.
- Error JSON shape: `{error, code, detail}` exactly, three keys, no extras — built directly in `_error_response`. Correct.
- Client exit codes 0/2/3/4/5 all implemented in `cli.main`. Non-2xx HTTPError captured as `HttpResult` (not network error) in `http_client.post_csv`. Stdout body written via `sys.stdout.buffer.write` verbatim. Correct.
- `--server` trailing slash stripped before joining. `--no-header` appends `?no_header=true`. Correct.

## Code-quality observations

1. **Server is tight.** Three small modules (`main`, `convert`, `errors`), one custom exception class with status + code + detail, two exception handlers. No dead code, no leakage in the 500 path, no shared state. Stateless as the brief requires.
2. **Client transport layer cleanly separated** from CLI layer. `NetworkError` is the single transport-failure signal; `HTTPError` correctly returned as `HttpResult` so the CLI maps it to exit 5, not 4. `_format_server_error` defensively handles non-dict / missing-key JSON.
3. **No security surface added.** Brief explicitly excluded auth; service is stateless; no filesystem or shell exposure on the server; 500 handler returns a fixed string instead of `repr(exc)`.

## Minor follow-ups (non-blocking, do NOT loop the team for these)

- v1 has no body-size limit (called out in contract as out of scope; uvicorn defaults apply). If this ever faces untrusted input, add an `if len(body) > N: 413` guard.
- `cli._read_file` opens without a max-size cap. Same risk class as the server; fine for the stated CLI-utility use case.
- No `405` test was needed because the framework handles it; QA confirmed via `test_get_on_convert_returns_405`. Good.

## Architectural concerns
None. Design split (FastAPI server, stdlib client, contract as sync point) worked exactly as planned — no cross-coder coordination needed, no contract drift.

HANDOFF: done
