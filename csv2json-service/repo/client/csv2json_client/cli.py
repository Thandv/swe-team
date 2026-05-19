"""csv2json-client CLI entry point.

Exit codes (from design/contracts.md):
  0  2xx response; stdout receives the response body verbatim.
  1  Generic / unexpected client-side error.
  2  Argument parsing error (argparse default).
  3  File not found or unreadable.
  4  Network failure: server unreachable, DNS, refused, timeout.
  5  Server returned non-2xx.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence

from . import __version__
from .http_client import HttpResult, NetworkError, post_csv

PROG = "csv2json-client"
DEFAULT_SERVER = "http://localhost:8000"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=PROG,
        description="POST a CSV file to the csv2json service and print the JSON response.",
    )
    p.add_argument(
        "csv_path",
        metavar="<csv-path>",
        help="Path to a local CSV file. Stdin ('-') is not supported.",
    )
    p.add_argument(
        "--no-header",
        action="store_true",
        help="Treat every row as data; keys are stringified column indices.",
    )
    p.add_argument(
        "--server",
        default=DEFAULT_SERVER,
        metavar="URL",
        help=f"Base URL of the csv2json server (default: {DEFAULT_SERVER}).",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"{PROG} {__version__}",
    )
    return p


def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def _read_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _format_server_error(server: str, result: HttpResult) -> str:
    body_text = ""
    try:
        body_text = result.body.decode("utf-8", errors="replace")
    except Exception:
        body_text = ""

    parsed = None
    if body_text:
        try:
            parsed = json.loads(body_text)
        except (ValueError, json.JSONDecodeError):
            parsed = None

    if (
        isinstance(parsed, dict)
        and "error" in parsed
        and "code" in parsed
        and "detail" in parsed
    ):
        return (
            f"{PROG}: server {server} returned {result.status}: "
            f"{parsed['code']} — {parsed['detail']}"
        )

    snippet = body_text[:200]
    return (
        f"{PROG}: server {server} returned {result.status} "
        f"(non-JSON body): {snippet}"
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    server = args.server.rstrip("/")

    try:
        csv_bytes = _read_file(args.csv_path)
    except FileNotFoundError as e:
        _eprint(f"{PROG}: cannot read '{args.csv_path}': {e.strerror or 'No such file or directory'}")
        return 3
    except IsADirectoryError as e:
        _eprint(f"{PROG}: cannot read '{args.csv_path}': {e.strerror or 'Is a directory'}")
        return 3
    except PermissionError as e:
        _eprint(f"{PROG}: cannot read '{args.csv_path}': {e.strerror or 'Permission denied'}")
        return 3
    except OSError as e:
        _eprint(f"{PROG}: cannot read '{args.csv_path}': {e.strerror or str(e)}")
        return 3

    try:
        result = post_csv(server=server, csv_bytes=csv_bytes, no_header=args.no_header)
    except NetworkError as e:
        _eprint(f"{PROG}: cannot reach {server}: {e}")
        return 4
    except Exception as e:  # noqa: BLE001
        _eprint(f"{PROG}: error: {e}")
        return 1

    if 200 <= result.status < 300:
        try:
            sys.stdout.buffer.write(result.body)
            sys.stdout.flush()
        except AttributeError:
            # In case stdout has been replaced with a text-only stream in tests.
            sys.stdout.write(result.body.decode("utf-8", errors="replace"))
            sys.stdout.flush()
        return 0

    _eprint(_format_server_error(server, result))
    return 5


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
