"""HTTP transport for the csv2json client.

Stdlib only: urllib.request + urllib.error. The CLI layer turns the
exceptions raised here into exit codes per design/contracts.md.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from urllib import error as urlerror
from urllib import request as urlrequest


class NetworkError(Exception):
    """Raised when the server cannot be reached (DNS, refused, timeout, ...).

    The CLI maps this to exit code 4.
    """


@dataclass
class HttpResult:
    status: int
    body: bytes
    content_type: str


def _normalize_server(server: str) -> str:
    return server.rstrip("/")


def build_url(server: str, no_header: bool) -> str:
    base = _normalize_server(server) + "/convert"
    if no_header:
        return base + "?no_header=true"
    return base


def post_csv(
    server: str,
    csv_bytes: bytes,
    no_header: bool,
    timeout: float = 30.0,
) -> HttpResult:
    """POST csv_bytes to {server}/convert.

    Returns HttpResult for any HTTP response (including non-2xx).
    Raises NetworkError when the request could not complete at the
    transport level (connection refused, DNS failure, timeout, ...).
    """
    url = build_url(server, no_header)
    req = urlrequest.Request(
        url=url,
        data=csv_bytes,
        method="POST",
        headers={"Content-Type": "text/csv"},
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            return HttpResult(status=status, body=body, content_type=content_type)
    except urlerror.HTTPError as e:
        # Server replied with a non-2xx; this is NOT a network error.
        body = e.read() if hasattr(e, "read") else b""
        content_type = ""
        if e.headers is not None:
            content_type = e.headers.get("Content-Type", "") or ""
        return HttpResult(status=e.code, body=body, content_type=content_type)
    except urlerror.URLError as e:
        raise NetworkError(str(e.reason)) from e
    except socket.timeout as e:
        raise NetworkError(f"timed out after {timeout}s") from e
    except (ConnectionError, OSError) as e:
        raise NetworkError(str(e)) from e
