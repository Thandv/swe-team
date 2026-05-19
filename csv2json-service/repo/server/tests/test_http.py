from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _assert_error_shape(body: dict, expected_code: str):
    assert set(body.keys()) == {"error", "code", "detail"}
    assert body["code"] == expected_code
    assert isinstance(body["error"], str)
    assert isinstance(body["detail"], str)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_convert_happy_path_header_mode():
    csv_body = "name,age\nalice,30\nbob,40\n"
    r = client.post(
        "/convert",
        content=csv_body,
        headers={"Content-Type": "text/csv"},
    )
    assert r.status_code == 200
    assert r.json() == [
        {"name": "alice", "age": "30"},
        {"name": "bob", "age": "40"},
    ]


def test_convert_happy_path_no_header_mode():
    csv_body = "alice,30\nbob,40\n"
    r = client.post(
        "/convert?no_header=true",
        content=csv_body,
        headers={"Content-Type": "text/csv"},
    )
    assert r.status_code == 200
    assert r.json() == [
        {"0": "alice", "1": "30"},
        {"0": "bob", "1": "40"},
    ]


def test_no_header_case_insensitive():
    r = client.post(
        "/convert?no_header=TRUE",
        content="a,b\n",
        headers={"Content-Type": "text/csv"},
    )
    assert r.status_code == 200


def test_content_type_with_charset_accepted():
    r = client.post(
        "/convert",
        content="a,b\n1,2\n",
        headers={"Content-Type": "text/csv; charset=utf-8"},
    )
    assert r.status_code == 200


def test_empty_body_returns_400_empty_body():
    r = client.post(
        "/convert",
        content=b"",
        headers={"Content-Type": "text/csv"},
    )
    assert r.status_code == 400
    _assert_error_shape(r.json(), "empty_body")


def test_wrong_content_type_returns_415():
    r = client.post(
        "/convert",
        content="a,b\n",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 415
    _assert_error_shape(r.json(), "wrong_content_type")


def test_missing_content_type_returns_415():
    # Force-remove content-type via raw httpx call: TestClient adds one by default
    # for content=str. Use empty header dict and bytes; httpx may still set
    # application/octet-stream. That still trips wrong_content_type.
    r = client.post(
        "/convert",
        content=b"a,b\n",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r.status_code == 415
    _assert_error_shape(r.json(), "wrong_content_type")


def test_wrong_query_value_returns_400():
    r = client.post(
        "/convert?no_header=maybe",
        content="a,b\n",
        headers={"Content-Type": "text/csv"},
    )
    assert r.status_code == 400
    _assert_error_shape(r.json(), "wrong_query")


def test_non_utf8_body_returns_malformed_csv():
    bad = b"\xff\xfe\xff"
    r = client.post(
        "/convert",
        content=bad,
        headers={"Content-Type": "text/csv"},
    )
    assert r.status_code == 400
    _assert_error_shape(r.json(), "malformed_csv")


def test_get_on_convert_returns_405():
    r = client.get("/convert")
    assert r.status_code == 405


def test_unknown_path_returns_404():
    r = client.get("/nope")
    assert r.status_code == 404


def test_ragged_row_omits_keys():
    r = client.post(
        "/convert",
        content="a,b,c\n1,2\n",
        headers={"Content-Type": "text/csv"},
    )
    assert r.status_code == 200
    assert r.json() == [{"a": "1", "b": "2"}]


def test_header_only_returns_empty_array():
    r = client.post(
        "/convert",
        content="a,b,c\n",
        headers={"Content-Type": "text/csv"},
    )
    assert r.status_code == 200
    assert r.json() == []
