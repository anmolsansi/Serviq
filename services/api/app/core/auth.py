"""Trusted authentication and tenant-context primitives.

This module owns the canonical server-side request context defined by Architecture
Contract C-1. It does not parse HTTP headers, validate OIDC tokens, create sessions,
or query memberships. Later trusted auth/tenant resolution code constructs this
model only after those checks succeed.
"""

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import MissingTenantContextError

NonEmptyString = Annotated[str, Field(min_length=1)]


class ActorType(StrEnum):
    """Strict actor categories allowed by Architecture Contract C-1."""

    TENANT_USER = "tenant_user"
    CUSTOMER = "customer"
    SERVICE = "service"
    PLATFORM_OPERATOR = "platform_operator"


class AssuranceLevel(StrEnum):
    """Strict identity-assurance levels allowed by Architecture Contract C-1."""

    ANONYMOUS = "anonymous"
    VERIFIED = "verified"
    WORKFORCE = "workforce"
    PLATFORM = "platform"


class RequestActor(BaseModel):
    """Trusted actor identity nested inside a request context."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    type: ActorType
    id: NonEmptyString


class RequestContext(BaseModel):
    """Immutable trusted request context matching Architecture Contract C-1.

    Python uses snake_case internally. Field aliases preserve the frozen camelCase
    wire/shared-contract names when the model is serialized with ``by_alias=True``.
    Permissions are stored as a tuple so trusted context cannot be mutated after
    construction. Their order and duplicates are preserved because Contract C-1
    does not authorize normalization or deduplication at this boundary.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    request_id: NonEmptyString = Field(alias="requestId")
    tenant_id: UUID = Field(alias="tenantId")
    actor: RequestActor
    user_id: UUID | None = Field(default=None, alias="userId")
    customer_id: UUID | None = Field(default=None, alias="customerId")
    permissions: tuple[str, ...] = ()
    assurance_level: AssuranceLevel = Field(alias="assuranceLevel")

    def has_permission(self, permission: str) -> bool:
        """Return whether the trusted capability set contains ``permission``."""

        return permission in self.permissions


def require_tenant_id(context: RequestContext | None) -> UUID:
    """Return trusted tenant ID or fail closed when no trusted context exists.

    Contract C-1 itself always contains a tenant UUID. This helper accepts ``None``
    so tenant-scoped service code can safely guard an unavailable/unresolved context
    without inventing a default tenant or reading arbitrary client input.
    """

    if context is None:
        raise MissingTenantContextError
    return context.tenant_id
