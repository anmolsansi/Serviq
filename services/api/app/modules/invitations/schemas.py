"""Invitation API request and safe response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.modules.invitations.security import (
    InvitationEmailError,
    normalize_invitation_email,
)


class InvitationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    email: str
    role_ids: list[UUID] = Field(alias="roleIds", min_length=1, max_length=20)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        try:
            return normalize_invitation_email(value)
        except InvitationEmailError as error:
            raise ValueError(str(error)) from None

    @field_validator("role_ids")
    @classmethod
    def validate_unique_role_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("roleIds must not contain duplicates")
        return value


class InvitationAcceptRequest(BaseModel):
    """One-time bearer token request with safe repr/serialization behavior."""

    model_config = ConfigDict(extra="forbid")

    token: SecretStr = Field(min_length=1, max_length=512)


class InvitationRoleView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    id: UUID
    key: str
    display_name: str = Field(alias="displayName")


class InvitationView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    id: UUID
    email: str
    status: str
    expires_at: datetime = Field(alias="expiresAt")
    roles: tuple[InvitationRoleView, ...]
    invited_by_user_id: UUID = Field(alias="invitedByUserId")
    accepted_by_user_id: UUID | None = Field(default=None, alias="acceptedByUserId")
    accepted_at: datetime | None = Field(default=None, alias="acceptedAt")
    revoked_at: datetime | None = Field(default=None, alias="revokedAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class InvitationCreateView(InvitationView):
    invite_url: str = Field(alias="inviteUrl")
