"""Tests for csv2json-client CLI.

Uses a tiny stdlib http.server fixture for end-to-end behavior and direct
calls to main() for argparse/file/error-path coverage.
"""

from __future__ import annotations

import io
import json
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional, Tuple

import pytest

from csv2json_client import cli, http_client


# ---------- Stub HTTP server fixture ---------------------------------------


class _StubHandler(BaseHTTPRequestHandler):
    # Set by the fixture below.
    responder: Optional[Callable[["_StubHandler"], None]] = None

    def log_message(self, *_args, **_kwargs):  # quiet
        return

    def do_POST(self):  # noqa: N802
        if _StubHandler.responder is None:
            self.send_response(500)
            self.end_headers()
            return
        _StubHandler.responder(self)

    def do_GET(self):  # noqa: N802
        self.do_POST()


@pytest.fixture
def stub_server():
    """Yields a (base_url, set_responder) pair.

    set_responder(fn) installs an fn(handler) that writes the response.
    """
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def set_responder(fn):
        _StubHandler.responder = fn

    try:
        yield f"http://{host}:{port}", set_responder
    finally:
        server.shutdown()
        server.server_close()
        _StubHandler.responder = None


def _write_csv(tmp_path, body: bytes = b"name,age\nalice,30\n") -> str:
    p = tmp_path / "data.csv"
    p.write_bytes(body)
    return str(p)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------- build_url -------------------------------------------------------


def test_build_url_strips_trailing_slash():
    assert (
        http_client.build_url("http://localhost:8000/", no_header=False)
        == "http://localhost:8000/convert"
    )


def test_build_url_no_header_true():
    assert (
        http_client.build_url("http://localhost:8000", no_header=True)
        == "http://localhost:8000/convert?no_header=true"
    )


# ---------- happy path ------------------------------------------------------


def test_success_prints_body_verbatim(tmp_path, stub_server, capsysbinary):
    url, set_responder = stub_server
    payload = b'[{"name":"alice","age":"30"}]'
    received: dict = {}

    def respond(h):
        received["path"] = h.path
        received["content_type"] = h.headers.get("Content-Type", "")
        received["body"] = h.rfile.read(int(h.headers.get("Content-Length", "0")))
        h.send_response(200)
        h.send_header("Content-Type", "application/json")
        h.send_header("Content-Length", str(len(payload)))
        h.end_headers()
        h.wfile.write(payload)

    set_responder(respond)

    csv_path = _write_csv(tmp_path)
    rc = cli.main([csv_path, "--server", url])
    assert rc == 0

    out = capsysbinary.readouterr()
    assert out.out == payload
    assert received["path"] == "/convert"
    assert received["content_type"].startswith("text/csv")
    assert received["body"] == b"name,age\nalice,30\n"


def test_no_header_appends_query(tmp_path, stub_server, capsysbinary):
    url, set_responder = stub_server
    captured: dict = {}

    def respond(h):
        captured["path"] = h.path
        h.rfile.read(int(h.headers.get("Content-Length", "0")))
        body = b'[{"0":"a","1":"1"}]'
        h.send_response(200)
        h.send_header("Content-Type", "application/json")
        h.send_header("Content-Length", str(len(body)))
        h.end_headers()
        h.wfile.write(body)

    set_responder(respond)
    csv_path = _write_csv(tmp_path, b"a,1\n")
    rc = cli.main([csv_path, "--server", url, "--no-header"])
    assert rc == 0
    assert captured["path"] == "/convert?no_header=true"


def test_server_url_trailing_slash_stripped(tmp_path, stub_server, capsysbinary):
    url, set_responder = stub_server
    captured: dict = {}

    def respond(h):
        captured["path"] = h.path
        h.rfile.read(int(h.headers.get("Content-Length", "0")))
        h.send_response(200)
        h.send_header("Content-Type", "application/json")
        h.send_header("Content-Length", "2")
        h.end_headers()
        h.wfile.write(b"[]")

    set_responder(respond)
    csv_path = _write_csv(tmp_path)
    rc = cli.main([csv_path, "--server", url + "/"])
    assert rc == 0
    assert captured["path"] == "/convert"


# ---------- error: file --------------------------------------------------


def test_file_not_found_exit_3(capsys):
    rc = cli.main(["/no/such/path/does/not/exist.csv", "--server", "http://localhost:1"])
    assert rc == 3
    err = capsys.readouterr().err
    assert "csv2json-client: cannot read" in err
    assert "/no/such/path/does/not/exist.csv" in err


def test_directory_path_exit_3(tmp_path, capsys):
    rc = cli.main([str(tmp_path), "--server", "http://localhost:1"])
    assert rc == 3
    err = capsys.readouterr().err
    assert "csv2json-client: cannot read" in err


# ---------- error: argparse ---------------------------------------------


def test_missing_positional_exit_2(capsys):
    with pytest.raises(SystemExit) as ei:
        cli.main([])
    assert ei.value.code == 2


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as ei:
        cli.main(["--help"])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert "csv2json-client" in out


# ---------- error: network ----------------------------------------------


def test_network_failure_exit_4(tmp_path, capsys):
    csv_path = _write_csv(tmp_path)
    port = _find_free_port()
    server = f"http://127.0.0.1:{port}"
    rc = cli.main([csv_path, "--server", server])
    assert rc == 4
    err = capsys.readouterr().err
    assert "csv2json-client: cannot reach" in err
    assert server in err


# ---------- error: server non-2xx with JSON body -------------------------


def test_server_error_json_body_exit_5(tmp_path, stub_server, capsys):
    url, set_responder = stub_server
    err_body = json.dumps(
        {"error": "Empty body", "code": "empty_body", "detail": "request body is empty"}
    ).encode("utf-8")

    def respond(h):
        h.rfile.read(int(h.headers.get("Content-Length", "0")))
        h.send_response(400)
        h.send_header("Content-Type", "application/json")
        h.send_header("Content-Length", str(len(err_body)))
        h.end_headers()
        h.wfile.write(err_body)

    set_responder(respond)
    csv_path = _write_csv(tmp_path, b"")
    rc = cli.main([csv_path, "--server", url])
    assert rc == 5
    err = capsys.readouterr().err
    assert "returned 400" in err
    assert "empty_body" in err
    assert "request body is empty" in err


def test_server_error_415_wrong_content_type(tmp_path, stub_server, capsys):
    url, set_responder = stub_server
    err_body = json.dumps(
        {"error": "Unsupported Media Type", "code": "wrong_content_type", "detail": "need text/csv"}
    ).encode("utf-8")

    def respond(h):
        h.rfile.read(int(h.headers.get("Content-Length", "0")))
        h.send_response(415)
        h.send_header("Content-Type", "application/json")
        h.send_header("Content-Length", str(len(err_body)))
        h.end_headers()
        h.wfile.write(err_body)

    set_responder(respond)
    csv_path = _write_csv(tmp_path)
    rc = cli.main([csv_path, "--server", url])
    assert rc == 5
    err = capsys.readouterr().err
    assert "returned 415" in err
    assert "wrong_content_type" in err


# ---------- error: server non-2xx with non-JSON body ---------------------


def test_server_error_non_json_body_exit_5(tmp_path, stub_server, capsys):
    url, set_responder = stub_server
    body = b"<html>500 oops</html>"

    def respond(h):
        h.rfile.read(int(h.headers.get("Content-Length", "0")))
        h.send_response(500)
        h.send_header("Content-Type", "text/html")
        h.send_header("Content-Length", str(len(body)))
        h.end_headers()
        h.wfile.write(body)

    set_responder(respond)
    csv_path = _write_csv(tmp_path)
    rc = cli.main([csv_path, "--server", url])
    assert rc == 5
    err = capsys.readouterr().err
    assert "returned 500" in err
    assert "non-JSON body" in err
    assert "<html>500 oops</html>" in err


def test_server_error_json_but_missing_keys(tmp_path, stub_server, capsys):
    """JSON body that doesn't match error shape → non-JSON branch."""
    url, set_responder = stub_server
    body = b'{"unexpected": true}'

    def respond(h):
        h.rfile.read(int(h.headers.get("Content-Length", "0")))
        h.send_response(500)
        h.send_header("Content-Type", "application/json")
        h.send_header("Content-Length", str(len(body)))
        h.end_headers()
        h.wfile.write(body)

    set_responder(respond)
    csv_path = _write_csv(tmp_path)
    rc = cli.main([csv_path, "--server", url])
    assert rc == 5
    err = capsys.readouterr().err
    assert "non-JSON body" in err
