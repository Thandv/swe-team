# System Design — csv2json-service

## Overview

Two independent components communicating over HTTP:

- **Server** (`repo/server/`) — FastAPI app exposing `POST /convert` and `GET /healthz`. Stateless. Stdlib `csv` for parsing.
- **Client** (`repo/client/`) — Python CLI `csv2json-client` using stdlib only (`argparse`, `urllib.request`).

The wire contract (see `contracts.md`) is the only shared surface. Neither side imports from the other; they live in sibling directories under `repo/`.

## Framework choice — Server: FastAPI

The brief allows stdlib `http.server`, Flask, or FastAPI. Picking **FastAPI** because:

- Built-in JSON serialization, request body handling for `text/csv`, and clear error responses via `HTTPException` / custom exception handlers.
- Auto-generated OpenAPI is a free QA aid.
- `uvicorn` gives a single-command server (`uvicorn app.main:app --host 0.0.0.0 --port 8000`).
- Trivial to test with `fastapi.testclient.TestClient` (sync, no event loop boilerplate).

Runtime deps: `fastapi`, `uvicorn[standard]`. Nothing else.

## Framework choice — Client: stdlib

`argparse` + `urllib.request` + `sys`. No `requests`. The brief prefers stdlib and there's no reason to deviate (no auth, no retries, no streaming).

## Module layout

### Server — `repo/server/`

```
repo/server/
  pyproject.toml          # fastapi, uvicorn[standard]; ruff/pytest as dev
  app/
    __init__.py
    main.py               # FastAPI app instance, route registration, exception handlers
    convert.py            # csv_to_records(text: str, no_header: bool) -> list[dict]
    errors.py             # CsvError exception class + error code constants
    schemas.py            # ErrorBody pydantic model (for OpenAPI; runtime uses dict)
  tests/
    test_convert.py       # unit tests for csv_to_records
    test_http.py          # TestClient integration: routes, status codes, error bodies
  README.md               # how to run
```

### Client — `repo/client/`

```
repo/client/
  pyproject.toml          # no runtime deps; entry point csv2json-client = csv2json_client.cli:main
  csv2json_client/
    __init__.py
    cli.py                # argparse + main(); exit codes per contract
    http_client.py        # post_csv(server, path, no_header) -> (status, body_bytes, content_type)
  tests/
    test_cli.py           # uses unittest.mock + a stub HTTP server fixture
  README.md
```

## Key types

### Server

```python
# app/errors.py
class CsvError(Exception):
    def __init__(self, code: str, detail: str, status: int):
        self.code = code
        self.detail = detail
        self.status = status

# Error codes (string constants)
EMPTY_BODY        = "empty_body"
WRONG_CONTENT_TYPE = "wrong_content_type"
MALFORMED_CSV     = "malformed_csv"
INTERNAL          = "internal"
```

```python
# app/convert.py
def csv_to_records(text: str, no_header: bool) -> list[dict[str, str]]:
    """Parse CSV text into list of row-objects.
    - no_header=False: first row supplies keys; data rows mapped by position.
    - no_header=True:  keys are stringified column indices "0","1",...
    - Empty input -> []; header-only (no_header=False) -> [].
    Raises CsvError(MALFORMED_CSV, ...) on csv.Error.
    """
```

```python
# app/schemas.py
class ErrorBody(BaseModel):
    error: str       # short slug, e.g. "Malformed CSV"
    code: str        # stable machine code from errors.py
    detail: str      # human-readable specifics
```

### Client

```python
# csv2json_client/http_client.py
@dataclass
class HttpResult:
    status: int
    body: bytes
    content_type: str

def post_csv(server: str, csv_bytes: bytes, no_header: bool) -> HttpResult:
    """POST csv_bytes to {server}/convert. Raises ConnectionError on network failure."""

# csv2json_client/cli.py
def main(argv: list[str] | None = None) -> int:
    """Returns exit code per contracts.md."""
```

## Cross-cutting decisions

- **Encoding**: CSV body is decoded as UTF-8 with `errors="replace"` rejected → on `UnicodeDecodeError` the server returns `malformed_csv`. Client sends raw bytes from disk unchanged.
- **Content-Type check**: server requires the request header to start with `text/csv` (allowing parameters like `;charset=utf-8`). Anything else → `wrong_content_type`.
- **Empty body**: explicit `empty_body` error (not `[]`) — the brief calls it out as a failure class.
- **Header-only CSV** (no data rows, `no_header=false`): success, returns `[]`.
- **Ragged rows**: if a data row has fewer columns than the header, missing keys are omitted from that row's object. Extra columns are dropped. This is deterministic and matches what stdlib `csv.DictReader` does.
- **Bind**: server defaults to `0.0.0.0:8000`. Configurable via env later if needed; not in v1.
