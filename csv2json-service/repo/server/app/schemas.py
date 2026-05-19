from pydantic import BaseModel


class ErrorBody(BaseModel):
    error: str
    code: str
    detail: str


class HealthBody(BaseModel):
    ok: bool
