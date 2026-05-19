import csv
import io

from .errors import CsvError, MALFORMED_CSV


def csv_to_records(text: str, no_header: bool) -> list[dict[str, str]]:
    """Parse CSV text into a list of row-objects.

    no_header=False: first non-empty row supplies keys; subsequent rows are values.
    no_header=True:  every row is data; keys are stringified column indices.
    """
    buf = io.StringIO(text)
    try:
        reader = csv.reader(buf)
        rows = list(reader)
    except csv.Error as exc:
        raise CsvError(MALFORMED_CSV, f"csv parser error: {exc}", 400) from exc

    if not rows:
        return []

    if no_header:
        return [
            {str(i): cell for i, cell in enumerate(row)}
            for row in rows
        ]

    header = rows[0]
    out: list[dict[str, str]] = []
    for row in rows[1:]:
        obj: dict[str, str] = {}
        for i, key in enumerate(header):
            if i < len(row):
                obj[key] = row[i]
        out.append(obj)
    return out
