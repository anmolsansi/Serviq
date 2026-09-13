"""Public workforce-session API contracts."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkforceSessionView(BaseModel):
    """Browser-safe view of the current server-side workforce session."""

    model_config = ConfigDict(populate_by_name=True)

    user_id: UUID = Field(alias="userId")
    email: str | None = None
    display_name: str | None = Field(default=None, alias="displayName")
    active_tenant_id: UUID | None = Field(default=None, alias="activeTenantId")
    csrf_token: str = Field(alias="csrfToken")


class TenantSwitchRequest(BaseModel):
    """Request to select one already-authorized active tenant membership."""

    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    tenant_id: UUID = Field(alias="tenantId")
