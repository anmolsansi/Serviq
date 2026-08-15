"""Typed tenant membership and capability results."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ResolvedTenantMembership(BaseModel):
    """Active tenant membership plus its effective deduplicated capability keys."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    membership_id: UUID
    tenant_id: UUID
    user_id: UUID
    status: str
    permissions: tuple[str, ...]
