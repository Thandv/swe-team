EMPTY_BODY = "empty_body"
WRONG_CONTENT_TYPE = "wrong_content_type"
WRONG_QUERY = "wrong_query"
MALFORMED_CSV = "malformed_csv"
INTERNAL = "internal"

_TITLES = {
    EMPTY_BODY: "Empty body",
    WRONG_CONTENT_TYPE: "Unsupported content type",
    WRONG_QUERY: "Invalid query parameter",
    MALFORMED_CSV: "Malformed CSV",
    INTERNAL: "Internal error",
}


class CsvError(Exception):
    def __init__(self, code: str, detail: str, status: int):
        self.code = code
        self.detail = detail
        self.status = status
        super().__init__(detail)

    @property
    def title(self) -> str:
        return _TITLES.get(self.code, "Error")
