# csv2json-server

Stateless FastAPI service that converts CSV to JSON.

## Install

```
cd repo/server
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Endpoints

- `POST /convert` — body: raw CSV (`Content-Type: text/csv`); query: `no_header=true|false`.
- `GET /healthz` — returns `{"ok": true}`.

See `design/contracts.md` for the full wire contract and error codes.

## Test

```
pytest
```
