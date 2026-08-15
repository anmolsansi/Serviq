"""Trusted internal workforce service result types."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InternalWorkforceUser(BaseModel):
    """Stable internal user identity returned to downstream Serviq services."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    oidc_issuer: str
    oidc_subject: str
    email: str
    display_name: str
    status: str
