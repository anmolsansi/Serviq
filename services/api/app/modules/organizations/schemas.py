"""Organization API request and response schemas."""

import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")


def _normalize_display_name(value: str) -> str:
    normalized = value.strip()
    if not 1 <= len(normalized) <= 120:
        raise ValueError("displayName must be 1-120 characters after trimming")
    return normalized


class OrganizationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    slug: str
    display_name: str = Field(alias="displayName")

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        if not 3 <= len(value) <= 63 or _SLUG_PATTERN.fullmatch(value) is None:
            raise ValueError(
                "slug must be 3-63 lowercase characters using only a-z, 0-9, and hyphens, "
                "without a leading or trailing hyphen"
            )
        return value

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return _normalize_display_name(value)


class OrganizationUpdateRequest(BaseModel):
    """Only V1-safe mutable organization settings."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    display_name: str | None = Field(default=None, alias="displayName")
    default_locale: Literal["en"] | None = Field(default=None, alias="defaultLocale")

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_display_name(value)

    @model_validator(mode="after")
    def require_change(self) -> "OrganizationUpdateRequest":
        if self.display_name is None and self.default_locale is None:
            raise ValueError("At least one organization setting must be supplied")
        return self


class OrganizationView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    id: UUID
    slug: str
    display_name: str = Field(alias="displayName")
    status: str
    default_locale: str = Field(alias="defaultLocale")
