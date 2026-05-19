# Idea

A small HTTP service that converts CSV to JSON, plus a Python CLI client that talks to it.

## Server

- `POST /convert` — request body is a CSV document (Content-Type: text/csv).
- Response: JSON array of objects, one per row. First row of the CSV is the field names.
- Optional query parameter `?no_header=true` — treat every row as data, keys are `"0"`, `"1"`, ...
- Health check: `GET /healthz` returns `{"ok": true}`.
- Stdlib + one HTTP framework only. Architect picks the framework.

## Client

- Python CLI named `csv2json-client`.
- `csv2json-client <csv-path> [--no-header] [--server URL]` posts the file to the server and prints JSON.
- Default `--server` value: `http://localhost:8000`.
- Exit non-zero with a clear error if the server is unreachable or returns a non-2xx response.

## Out of scope

- Authentication.
- Streaming uploads.
- Persistence (the server is stateless).

This is a meaty-but-bounded team test — the backend and client must agree on the contract, and both coders should work in parallel.
