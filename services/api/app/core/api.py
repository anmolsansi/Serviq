"""Python mirrors of Serviq's frozen baseline API envelopes."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class SuccessEnvelope(BaseModel, Generic[T]):
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
