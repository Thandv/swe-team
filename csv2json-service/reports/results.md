# Test Results — csv2json-service

**Status: PASS**

| Suite | Passed | Failed |
| --- | ---: | ---: |
| Server (`repo/server/tests/`) | 25 | 0 |
| Client (`repo/client/tests/`) | 14 | 0 |
| Integration (live server + live client) | 4 | 0 |
| **TOTAL** | **43** | **0** |

Executed via `bash reports/run-tests.sh` with the pre-built `.venv-qa/`. Pytest version 9.0.3, Python 3.14.5.

## Per-test status

### Server — 25/25 PASS

```
tests/test_convert.py::test_empty_string_returns_empty_list           PASS
tests/test_convert.py::test_header_only_returns_empty_list            PASS
tests/test_convert.py::test_basic_header_mode                         PASS
tests/test_convert.py::test_basic_no_header_mode                      PASS
tests/test_convert.py::test_ragged_row_omits_missing_keys             PASS
tests/test_convert.py::test_extra_columns_dropped                     PASS
tests/test_convert.py::test_no_header_variable_width                  PASS
tests/test_convert.py::test_quoted_field_with_comma                   PASS
tests/test_convert.py::test_quoted_field_with_newline                 PASS
tests/test_convert.py::test_malformed_csv_raises                      PASS
tests/test_convert.py::test_malformed_csv_via_strict_path             PASS
tests/test_http.py::test_healthz                                      PASS
tests/test_http.py::test_convert_happy_path_header_mode               PASS
tests/test_http.py::test_convert_happy_path_no_header_mode            PASS
tests/test_http.py::test_no_header_case_insensitive                   PASS
tests/test_http.py::test_content_type_with_charset_accepted           PASS
tests/test_http.py::test_empty_body_returns_400_empty_body            PASS
tests/test_http.py::test_wrong_content_type_returns_415               PASS
tests/test_http.py::test_missing_content_type_returns_415             PASS
tests/test_http.py::test_wrong_query_value_returns_400                PASS
tests/test_http.py::test_non_utf8_body_returns_malformed_csv          PASS
tests/test_http.py::test_get_on_convert_returns_405                   PASS
tests/test_http.py::test_unknown_path_returns_404                     PASS
tests/test_http.py::test_ragged_row_omits_keys                        PASS
tests/test_http.py::test_header_only_returns_empty_array              PASS
```

### Client — 14/14 PASS

```
tests/test_cli.py::test_build_url_strips_trailing_slash               PASS
tests/test_cli.py::test_build_url_no_header_true                      PASS
tests/test_cli.py::test_success_prints_body_verbatim                  PASS
tests/test_cli.py::test_no_header_appends_query                       PASS
tests/test_cli.py::test_server_url_trailing_slash_stripped            PASS
tests/test_cli.py::test_file_not_found_exit_3                         PASS
tests/test_cli.py::test_directory_path_exit_3                         PASS
tests/test_cli.py::test_missing_positional_exit_2                     PASS
tests/test_cli.py::test_help_exits_zero                               PASS
tests/test_cli.py::test_network_failure_exit_4                        PASS
tests/test_cli.py::test_server_error_json_body_exit_5                 PASS
tests/test_cli.py::test_server_error_415_wrong_content_type           PASS
tests/test_cli.py::test_server_error_non_json_body_exit_5             PASS
tests/test_cli.py::test_server_error_json_but_missing_keys            PASS
```

### Integration — 4/4 PASS

Server booted with `uvicorn app.main:app --host 127.0.0.1 --port 8765` from `repo/server/`. Killed on exit.

```
healthz returns {ok:true}                                              PASS
client basic.csv -> header mode JSON, exit 0                           PASS
client --no-header -> indexed JSON, exit 0                             PASS
client empty.csv -> exit 5 / empty_body                                PASS
```

## Contract conformance

All rows from `design/contracts.md` are demonstrated by the suites above:

- POST /convert 200 header mode, no_header=true mode — covered by server unit + integration.
- 400 empty_body / malformed_csv / wrong_query — server unit; empty_body also covered end-to-end.
- 415 wrong_content_type (both with-CT and unexpected-CT) — server unit.
- GET /healthz 200 `{"ok": true}` — server unit + integration.
- 405 on unsupported method, 404 on unknown path — server unit.
- Error JSON shape (`error`, `code`, `detail` exactly) — asserted in `_assert_error_shape` helper.
- Client exit codes 0 / 2 / 3 / 4 / 5 — all enumerated in client unit tests.
- `--server` trailing-slash stripping, `--no-header` query append — client unit + integration.
- Stdout body printed verbatim on 2xx — client unit (capsysbinary asserts equality) + integration (string equality on fixture).

No deviations observed.

## Artifacts

- `reports/server-pytest.log`
- `reports/client-pytest.log`
- `reports/integration.log`
- `reports/uvicorn.log`
- `reports/fixtures/basic.csv`, `reports/fixtures/no_header.csv`, `reports/fixtures/empty.csv`
