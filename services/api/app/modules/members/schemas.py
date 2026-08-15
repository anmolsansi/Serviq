"""Strict member-management request and safe response schemas."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

MembershipStatus = Literal["active", "suspended"]


class MemberRoleView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    id: UUID
    key: str
    display_name: str = Field(alias="displayName")


class MemberView(BaseModel):
    """Tenant-safe workforce view; intentionally excludes OIDC issuer/subject."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    membership_id: UUID = Field(alias="membershipId")
    user_id: UUID = Field(alias="userId")
    email: str
    display_name: str = Field(alias="displayName")
    status: MembershipStatus
    roles: tuple[MemberRoleView, ...]


class MemberUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    role_ids: list[UUID] | None = Field(
        default=None,
        alias="roleIds",
        min_length=1,
        max_length=20,
    )
    status: MembershipStatus | None = None

    @model_validator(mode="after")
    def validate_update(self) -> "MemberUpdateRequest":
        if self.role_ids is None and self.status is None:
            raise ValueError("At least one of roleIds or status is required")
        if self.role_ids is not None and len(self.role_ids) != len(set(self.role_ids)):
            raise ValueError("roleIds must not contain duplicates")
        return self
