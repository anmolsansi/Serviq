"""Organization API request and response schemas."""

import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")


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
        normalized = value.strip()
        if not 1 <= len(normalized) <= 120:
            raise ValueError("displayName must be 1-120 characters after trimming")
        return normalized


class OrganizationView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    id: UUID
    slug: str
    display_name: str = Field(alias="displayName")
    status: str
    default_locale: str = Field(alias="defaultLocale")
