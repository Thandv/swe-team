# csv2json-client

CLI for the csv2json HTTP service. Stdlib only.

## Install

```
pip install -e .
```

This installs the `csv2json-client` script on `$PATH`.

## Usage

```
csv2json-client <csv-path> [--no-header] [--server URL]
```

- `<csv-path>` — path to a local CSV file (required; stdin not supported).
- `--no-header` — treat every row as data; keys become `"0"`, `"1"`, ...
- `--server URL` — base URL (default `http://localhost:8000`).

## Examples

```
csv2json-client data.csv
csv2json-client data.csv --no-header
csv2json-client data.csv --server http://my-host:8000
```

## Exit codes

`0` success · `2` bad args · `3` file unreadable · `4` server unreachable · `5` server returned non-2xx.

## Tests

```
pip install -e .[dev]
pytest
```
