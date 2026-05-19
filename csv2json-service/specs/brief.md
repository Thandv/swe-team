# Brief — csv2json-service

## Goals

- Provide a small, stateless HTTP service that converts CSV documents into JSON arrays of objects.
- Provide a Python CLI client that sends a local CSV file to the service and prints the resulting JSON to stdout.
- Backend and client must agree on a shared wire contract (request body shape, query parameters, response shape, error semantics) so they can be developed in parallel.
- Keep dependencies minimal: stdlib plus a single HTTP framework on the server side; stdlib-only on the client side where reasonable.

## Non-goals

- Authentication / authorization of any kind.
- Streaming uploads or chunked CSV processing.
- Persistence: the server holds no state between requests.
- Format auto-detection beyond standard CSV (e.g. no TSV, no Excel quirks, no encoding sniffing).
- A graphical UI, batch processing UI, or multi-file uploads.

## Users

- Developers who need a quick local utility to turn CSV files into JSON for downstream tooling.
- Automation scripts that want to POST CSV content to a known endpoint and consume JSON.

## Success criteria

- `POST /convert` with a CSV body returns a JSON array of objects, one per data row, with keys taken from the first row by default.
- `POST /convert?no_header=true` returns a JSON array of objects keyed by stringified column indices (`"0"`, `"1"`, ...).
- `GET /healthz` returns `{"ok": true}` with HTTP 200.
- Malformed input or unsupported content yields a non-2xx response with a JSON error body the client can surface.
- `csv2json-client path/to/file.csv` prints the same JSON the server returns when given that file body, and exits 0.
- `csv2json-client` exits non-zero with a human-readable error when the server is unreachable or returns a non-2xx status.
- `--no-header` and `--server URL` flags behave as described in the idea.
- Backend and client can be implemented independently against the contract document the architect produces.

## Scope — Server

- HTTP endpoints:
  - `POST /convert` (Content-Type: `text/csv`), optional query `no_header=true|false` (default `false`).
  - `GET /healthz`.
- CSV parsing via the Python stdlib `csv` module.
- One HTTP framework, picked by the architect (stdlib `http.server` is acceptable; FastAPI/Flask are acceptable). No other runtime dependencies.
- Stateless: every request is self-contained.
- Sensible error responses for: empty body, malformed CSV, wrong content type. Error body is JSON with a stable shape.
- Default bind: `0.0.0.0:8000` (architect may revisit).

## Scope — Client

- Python CLI installed/runnable as `csv2json-client`.
- Arguments: positional `<csv-path>`, flags `--no-header` and `--server URL` (default `http://localhost:8000`).
- Reads the file from disk, POSTs the bytes to `<server>/convert` with `Content-Type: text/csv`, appending `?no_header=true` when the flag is set.
- Prints the response body to stdout on 2xx.
- On connection failure or non-2xx response: writes a clear message to stderr and exits with a non-zero code. The message must include the server URL and, when available, the server's error body.
- Stdlib-only is preferred (`urllib.request`, `argparse`); architect may approve `requests` if there's a reason.

## Notes for downstream roles

- The wire contract (exact error JSON shape, status codes per failure class, behavior on empty CSV vs. header-only CSV) is the architect's call and must live in `design/contracts.md` so both coders can target it without coordination.
- Two parallel coder tracks are expected: `coder-backend` (server) and `coder-python` (client). The contract doc is the synchronization point.
