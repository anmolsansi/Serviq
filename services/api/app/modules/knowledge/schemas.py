"""Strict URL/sitemap knowledge-source request models and safe response projections."""

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

RegisterableKnowledgeSourceType = Literal["url", "sitemap"]
KnowledgeSourceType = Literal["url", "sitemap", "pdf", "markdown", "text"]
KnowledgeAccessScope = Literal["customer", "internal"]
KnowledgeSourceStatus = Literal["pending", "syncing", "ready", "failed", "disabled"]


class KnowledgeSourceCreateRequest(BaseModel):
    """Metadata-only registration request for public URL-backed sources."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source_type: RegisterableKnowledgeSourceType = Field(alias="sourceType")
    name: str = Field(min_length=1, max_length=160)
    source_uri: str = Field(alias="sourceUri", min_length=1)
    access_scope: KnowledgeAccessScope = Field(alias="accessScope")

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("source_uri", mode="before")
    @classmethod
    def validate_source_uri(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        normalized = value.strip()
        if not normalized:
            raise ValueError("sourceUri must not be blank")
        if "#" in normalized:
            raise ValueError("sourceUri must not contain a fragment")
        if any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in normalized
        ):
            raise ValueError("sourceUri contains invalid whitespace or control characters")

        try:
            parsed = urlsplit(normalized)
            hostname = parsed.hostname
            username = parsed.username
            password = parsed.password
            _ = parsed.port
        except ValueError as error:
            raise ValueError("sourceUri must be a valid absolute HTTPS URL") from error

        if parsed.scheme.lower() != "https":
            raise ValueError("sourceUri must use HTTPS")
        if not parsed.netloc or hostname is None:
            raise ValueError("sourceUri must be an absolute HTTPS URL")
        if username is not None or password is not None:
            raise ValueError("sourceUri must not contain credentials")

        return normalized


class KnowledgeSourceView(BaseModel):
    """Browser-safe metadata projection. Storage internals are deliberately omitted."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    id: UUID
    source_type: KnowledgeSourceType = Field(alias="sourceType")
    name: str
    source_uri: str | None = Field(alias="sourceUri")
    access_scope: KnowledgeAccessScope = Field(alias="accessScope")
    status: KnowledgeSourceStatus
    sync_version: int = Field(alias="syncVersion")
    last_synced_at: datetime | None = Field(alias="lastSyncedAt")
    last_error_code: str | None = Field(alias="lastErrorCode")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
