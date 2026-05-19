# Wire Contract — csv2json-service

This is the single source of truth for the HTTP boundary. Both `coder-backend` and `coder-python` implement against this document without coordinating.

## Base

- Default server URL: `http://localhost:8000`
- All request and response bodies are UTF-8.
- All error responses use the **Error JSON shape** below.

## Endpoints

### `POST /convert`

Convert CSV to JSON.

**Request**

| Field | Value |
| --- | --- |
| Method | `POST` |
| Path | `/convert` |
| Query | `no_header` (optional) — `true` or `false` (case-insensitive). Default `false`. Any other value → `400 wrong_query`. |
| Header | `Content-Type: text/csv` (parameters like `; charset=utf-8` permitted). Anything else → `415 wrong_content_type`. |
| Body | Raw CSV bytes. May be empty. |

**Success response — 200**

- `Content-Type: application/json`
- Body: JSON array of objects.

`no_header=false` (default):
- First non-empty row supplies keys (strings).
- Each subsequent row becomes one object; values are strings.
- If a data row has fewer cells than the header, missing keys are **omitted** from that object.
- Extra cells beyond the header are **dropped**.
- Header-only CSV (no data rows) → `[]`.

`no_header=true`:
- Every row is data.
- Keys are stringified zero-based column indices: `"0"`, `"1"`, ...
- Per-row width is used (a row of 3 cells produces keys `"0","1","2"`; a row of 5 produces `"0".."4"`).

Examples:

```
# Request body (no_header=false):
name,age
alice,30
bob,40

# Response:
[{"name":"alice","age":"30"},{"name":"bob","age":"40"}]
```

```
# Request body (no_header=true):
alice,30
bob,40

# Response:
[{"0":"alice","1":"30"},{"0":"bob","1":"40"}]
```

**Error responses**

| Status | `code` | When |
| --- | --- | --- |
| 400 | `empty_body` | Request body is empty (zero bytes). |
| 400 | `malformed_csv` | `csv` module raises `csv.Error`, or body is not decodable as UTF-8. |
| 400 | `wrong_query` | `no_header` query param is present but not `true`/`false`. |
| 415 | `wrong_content_type` | `Content-Type` header missing or not `text/csv` (optionally with parameters). |
| 500 | `internal` | Anything else. Detail should not leak internals. |

### `GET /healthz`

**Request:** `GET /healthz`, no body, no headers required.

**Response — 200**, `Content-Type: application/json`:

```json
{"ok": true}
```

No error cases (a failing health check is the absence of any 2xx, e.g. connection refused).

## Error JSON shape

Every non-2xx response from `/convert` has this body:

```json
{
  "error": "<short human title>",
  "code":  "<stable machine slug>",
  "detail": "<human-readable specifics>"
}
```

- `error` — short title, e.g. `"Malformed CSV"`. For display.
- `code` — stable slug from the table above. Clients should branch on this, not on `error`.
- `detail` — specifics suitable for showing to a developer. May be empty string but key is always present.

The three keys are always present. No other top-level keys.

## Server status code summary

| Status | Meaning | Endpoints |
| --- | --- | --- |
| 200 | OK | `/convert`, `/healthz` |
| 400 | Bad request (empty body, malformed CSV, bad query) | `/convert` |
| 405 | Method not allowed | both, framework default |
| 415 | Unsupported media type | `/convert` |
| 500 | Internal error | `/convert` |

## Client exit codes

| Exit | When | Stderr message format |
| --- | --- | --- |
| 0 | 2xx response; stdout receives the response body verbatim. | (no stderr output) |
| 1 | Generic / unexpected client-side error. | `csv2json-client: error: <detail>` |
| 2 | Argument parsing error (argparse default). | argparse default |
| 3 | File not found or unreadable at `<csv-path>`. | `csv2json-client: cannot read '<path>': <os-error>` |
| 4 | Network failure: server unreachable, DNS failure, connection refused, timeout. | `csv2json-client: cannot reach <server>: <reason>` |
| 5 | Server returned non-2xx. | `csv2json-client: server <server> returned <status>: <code> — <detail>`<br>If the body wasn't valid JSON matching the error shape: `csv2json-client: server <server> returned <status> (non-JSON body): <first-200-chars>` |

Exit code 2 is argparse's built-in convention; we don't override it.

## Client CLI surface

```
csv2json-client <csv-path> [--no-header] [--server URL]
```

- `<csv-path>` — positional, required. Path to a local file. `-` is **not** supported in v1 (no stdin).
- `--no-header` — flag, default off. When set, client appends `?no_header=true` to the URL.
- `--server URL` — default `http://localhost:8000`. Trailing slash on URL is stripped before joining with `/convert`.
- `--help` — argparse default.

Request the client sends:
- Method `POST`, URL `{server}/convert[?no_header=true]`.
- Header `Content-Type: text/csv`.
- Body: raw bytes read from `<csv-path>`, unchanged.

On success, the client writes the response body bytes to stdout exactly as received (no re-serialization) and exits 0. On failure it writes to stderr per the table above.

## Out of scope (will return 4xx/5xx naturally)

- Other methods on `/convert` (GET/PUT/DELETE) → 405 from framework.
- Other paths → 404 from framework.
- Large bodies — no explicit limit in v1; FastAPI/uvicorn defaults apply.
