"""Python mirrors of Serviq's frozen baseline API envelopes."""

from pydantic import BaseModel, ConfigDict


class SuccessEnvelope[T](BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: T


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    fields: dict[str, str] | None = None


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail
