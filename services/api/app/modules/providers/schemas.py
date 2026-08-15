"""Strict provider request models and safe response projections."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

ProviderKey = Literal["openai", "anthropic", "gemini", "openrouter"]
ProviderStatus = Literal["untested", "active", "invalid", "disabled"]


class ProviderCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    provider: ProviderKey
    display_name: str = Field(alias="displayName", min_length=1, max_length=80)
    api_key: SecretStr = Field(alias="apiKey", min_length=1, max_length=4096)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("displayName must not be blank")
        return normalized


class ProviderUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    display_name: str | None = Field(
        default=None,
        alias="displayName",
        min_length=1,
        max_length=80,
    )
    api_key: SecretStr | None = Field(
        default=None,
        alias="apiKey",
        min_length=1,
        max_length=4096,
    )

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("displayName must not be blank")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> ProviderUpdateRequest:
        if self.display_name is None and self.api_key is None:
            raise ValueError("At least one mutable provider field is required")
        return self


class ProviderView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    id: UUID
    provider: ProviderKey
    display_name: str = Field(alias="displayName")
    status: ProviderStatus
    last_tested_at: datetime | None = Field(alias="lastTestedAt")
    last_error_code: str | None = Field(alias="lastErrorCode")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
