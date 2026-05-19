# Test Plan — csv2json-service

Each row maps to a contract item from `design/contracts.md`. Three sections: server unit/contract tests, client unit tests, integration (server + client end-to-end).

## Server (`repo/server/tests/`)

Executed with `.venv-qa/bin/pytest repo/server/tests -v`.

| Contract item | Test file::test | Expected |
| --- | --- | --- |
| POST /convert 200 header mode | `test_http.py::test_convert_happy_path_header_mode` | 200, array of objects keyed by header |
| POST /convert 200 no_header=true | `test_http.py::test_convert_happy_path_no_header_mode` | 200, keys `"0"`,`"1"` |
| no_header case-insensitive | `test_http.py::test_no_header_case_insensitive` | 200 with `?no_header=TRUE` |
| Content-Type with parameters accepted | `test_http.py::test_content_type_with_charset_accepted` | 200 with `text/csv; charset=utf-8` |
| 400 empty_body | `test_http.py::test_empty_body_returns_400_empty_body` | 400, code=`empty_body`, error shape valid |
| 415 wrong_content_type | `test_http.py::test_wrong_content_type_returns_415` | 415, code=`wrong_content_type` |
| 415 wrong_content_type (octet-stream) | `test_http.py::test_missing_content_type_returns_415` | 415, code=`wrong_content_type` |
| 400 wrong_query | `test_http.py::test_wrong_query_value_returns_400` | 400, code=`wrong_query` |
| 400 malformed_csv (non-UTF8) | `test_http.py::test_non_utf8_body_returns_malformed_csv` | 400, code=`malformed_csv` |
| 405 on GET /convert | `test_http.py::test_get_on_convert_returns_405` | 405 |
| 404 unknown path | `test_http.py::test_unknown_path_returns_404` | 404 |
| Ragged row omits missing keys | `test_http.py::test_ragged_row_omits_keys` | `[{"a":"1","b":"2"}]` |
| Header-only CSV → `[]` | `test_http.py::test_header_only_returns_empty_array` | `[]` |
| GET /healthz | `test_http.py::test_healthz` | 200, `{"ok": true}` |
| Convert unit: empty string | `test_convert.py::test_empty_string_returns_empty_list` | `[]` |
| Convert unit: header-only | `test_convert.py::test_header_only_returns_empty_list` | `[]` |
| Convert unit: header mode | `test_convert.py::test_basic_header_mode` | parsed records |
| Convert unit: no-header mode | `test_convert.py::test_basic_no_header_mode` | indexed records |
| Convert unit: ragged row | `test_convert.py::test_ragged_row_omits_missing_keys` | missing keys omitted |
| Convert unit: extra columns | `test_convert.py::test_extra_columns_dropped` | extras dropped |
| Convert unit: no-header variable width | `test_convert.py::test_no_header_variable_width` | per-row width keys |
| Convert unit: quoted comma | `test_convert.py::test_quoted_field_with_comma` | embedded comma preserved |
| Convert unit: quoted newline | `test_convert.py::test_quoted_field_with_newline` | embedded newline preserved |
| Convert unit: tolerant of weird bytes | `test_convert.py::test_malformed_csv_raises` | does not crash |
| Convert unit: csv.Error → CsvError(malformed_csv) | `test_convert.py::test_malformed_csv_via_strict_path` | raises `CsvError` w/ code |

## Client (`repo/client/tests/`)

Executed with `.venv-qa/bin/pytest repo/client/tests -v`.

| Contract item | Test file::test | Expected |
| --- | --- | --- |
| URL join: trailing slash stripped | `test_cli.py::test_build_url_strips_trailing_slash` | `/convert` path |
| URL join: `--no-header` appends query | `test_cli.py::test_build_url_no_header_true` | `?no_header=true` |
| Success: response body printed verbatim, exit 0 | `test_cli.py::test_success_prints_body_verbatim` | exit 0, stdout = body |
| `--no-header` flag appends query in request | `test_cli.py::test_no_header_appends_query` | `/convert?no_header=true` sent |
| `--server` trailing slash handling at CLI level | `test_cli.py::test_server_url_trailing_slash_stripped` | path = `/convert` |
| Exit 3: file not found | `test_cli.py::test_file_not_found_exit_3` | exit 3, stderr "cannot read" |
| Exit 3: path is directory | `test_cli.py::test_directory_path_exit_3` | exit 3 |
| Exit 2: argparse missing positional | `test_cli.py::test_missing_positional_exit_2` | SystemExit 2 |
| Exit 0: `--help` | `test_cli.py::test_help_exits_zero` | SystemExit 0 |
| Exit 4: connection refused | `test_cli.py::test_network_failure_exit_4` | exit 4, stderr "cannot reach <server>" |
| Exit 5: server 400 JSON error body | `test_cli.py::test_server_error_json_body_exit_5` | exit 5, stderr contains code+detail |
| Exit 5: server 415 JSON error body | `test_cli.py::test_server_error_415_wrong_content_type` | exit 5, stderr "wrong_content_type" |
| Exit 5: server 500 non-JSON body | `test_cli.py::test_server_error_non_json_body_exit_5` | exit 5, stderr "non-JSON body" |
| Exit 5: server JSON body missing required keys | `test_cli.py::test_server_error_json_but_missing_keys` | exit 5, stderr "non-JSON body" |

## Integration (live server + live client)

Executed by `reports/run-tests.sh`. Server booted with `uvicorn app.main:app --port 8765` from `repo/server/` (so the `app` package is importable). Client invoked via `.venv-qa/bin/csv2json-client`. Server killed at the end of the step.

| Contract item | Step | Expected |
| --- | --- | --- |
| End-to-end POST /convert (header mode) | `csv2json-client reports/fixtures/basic.csv --server http://localhost:8765` | exit 0, stdout `[{"name":"alice","age":"30"},{"name":"bob","age":"40"}]` |
| End-to-end POST /convert?no_header=true | `csv2json-client reports/fixtures/no_header.csv --server http://localhost:8765 --no-header` | exit 0, stdout `[{"0":"alice","1":"30"},{"0":"bob","1":"40"}]` |
| End-to-end empty body → exit 5 / `empty_body` | `csv2json-client reports/fixtures/empty.csv ...` | exit 5, stderr contains `empty_body` |
| End-to-end healthz reachable | `curl http://localhost:8765/healthz` | 200, body `{"ok":true}` |
