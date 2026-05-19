from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .convert import csv_to_records
from .errors import (
    CsvError,
    EMPTY_BODY,
    INTERNAL,
    MALFORMED_CSV,
    WRONG_CONTENT_TYPE,
    WRONG_QUERY,
)
from .schemas import ErrorBody, HealthBody

app = FastAPI(title="csv2json-service", version="0.1.0")


def _error_response(err: CsvError) -> JSONResponse:
    return JSONResponse(
        status_code=err.status,
        content={"error": err.title, "code": err.code, "detail": err.detail},
    )


@app.exception_handler(CsvError)
async def _csv_error_handler(_: Request, exc: CsvError) -> JSONResponse:
    return _error_response(exc)


@app.exception_handler(Exception)
async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    return _error_response(CsvError(INTERNAL, "unexpected server error", 500))


def _parse_no_header(raw: str | None) -> bool:
    if raw is None:
        return False
    norm = raw.strip().lower()
    if norm == "true":
        return True
    if norm == "false":
        return False
    raise CsvError(WRONG_QUERY, f"no_header must be 'true' or 'false', got {raw!r}", 400)


def _check_content_type(ct: str | None) -> None:
    if not ct:
        raise CsvError(WRONG_CONTENT_TYPE, "missing Content-Type header", 415)
    primary = ct.split(";", 1)[0].strip().lower()
    if primary != "text/csv":
        raise CsvError(
            WRONG_CONTENT_TYPE,
            f"expected Content-Type 'text/csv', got {ct!r}",
            415,
        )


@app.get("/healthz", response_model=HealthBody)
async def healthz() -> dict:
    return {"ok": True}


@app.post(
    "/convert",
    responses={
        200: {"content": {"application/json": {}}},
        400: {"model": ErrorBody},
        415: {"model": ErrorBody},
        500: {"model": ErrorBody},
    },
)
async def convert(request: Request) -> JSONResponse:
    _check_content_type(request.headers.get("content-type"))

    raw_q = request.query_params.get("no_header")
    no_header = _parse_no_header(raw_q)

    body = await request.body()
    if not body:
        raise CsvError(EMPTY_BODY, "request body is empty", 400)

    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CsvError(MALFORMED_CSV, f"body is not valid UTF-8: {exc}", 400) from exc

    records = csv_to_records(text, no_header)
    return JSONResponse(status_code=200, content=records)
