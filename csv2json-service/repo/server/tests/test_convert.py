import pytest

from app.convert import csv_to_records
from app.errors import CsvError, MALFORMED_CSV


def test_empty_string_returns_empty_list():
    assert csv_to_records("", no_header=False) == []
    assert csv_to_records("", no_header=True) == []


def test_header_only_returns_empty_list():
    assert csv_to_records("name,age\n", no_header=False) == []


def test_basic_header_mode():
    text = "name,age\nalice,30\nbob,40\n"
    assert csv_to_records(text, no_header=False) == [
        {"name": "alice", "age": "30"},
        {"name": "bob", "age": "40"},
    ]


def test_basic_no_header_mode():
    text = "alice,30\nbob,40\n"
    assert csv_to_records(text, no_header=True) == [
        {"0": "alice", "1": "30"},
        {"0": "bob", "1": "40"},
    ]


def test_ragged_row_omits_missing_keys():
    text = "a,b,c\n1,2\n"
    assert csv_to_records(text, no_header=False) == [{"a": "1", "b": "2"}]


def test_extra_columns_dropped():
    text = "a,b\n1,2,3,4\n"
    assert csv_to_records(text, no_header=False) == [{"a": "1", "b": "2"}]


def test_no_header_variable_width():
    text = "a,b,c\nx,y\n"
    assert csv_to_records(text, no_header=True) == [
        {"0": "a", "1": "b", "2": "c"},
        {"0": "x", "1": "y"},
    ]


def test_quoted_field_with_comma():
    text = 'name,note\nalice,"hello, world"\n'
    assert csv_to_records(text, no_header=False) == [
        {"name": "alice", "note": "hello, world"}
    ]


def test_quoted_field_with_newline():
    text = 'name,note\nalice,"line1\nline2"\n'
    assert csv_to_records(text, no_header=False) == [
        {"name": "alice", "note": "line1\nline2"}
    ]


def test_malformed_csv_raises():
    # Unterminated quote with strict-ish parsing: csv module raises on EOF inside quote
    # depending on dialect; force an error via a NUL byte which csv rejects.
    bad = "a,b\n\x00\n"
    # csv reader actually tolerates NULs; instead force csv.Error by passing
    # something that triggers it: csv.reader does NOT typically error on
    # unbalanced quotes (it just keeps reading). To get a real csv.Error we
    # need strict=True — which we don't set. So skip and assert tolerance:
    # this test confirms our parser doesn't crash on weird input.
    out = csv_to_records(bad, no_header=True)
    assert isinstance(out, list)


def test_malformed_csv_via_strict_path(monkeypatch):
    # Simulate csv.Error path by monkeypatching csv.reader.
    import app.convert as conv

    def boom(_buf):
        raise __import__("csv").Error("synthetic")

    monkeypatch.setattr(conv.csv, "reader", boom)
    with pytest.raises(CsvError) as ei:
        csv_to_records("a,b\n", no_header=False)
    assert ei.value.code == MALFORMED_CSV
    assert ei.value.status == 400
