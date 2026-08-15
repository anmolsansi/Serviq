from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.core.auth import (
    ActorType,
    AssuranceLevel,
    RequestActor,
    RequestContext,
    require_tenant_id,
)
from app.core.errors import MissingTenantContextError


def test_valid_workforce_context_preserves_contract_and_permissions() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    context = RequestContext(
        requestId="req-workforce-1",
        tenantId=tenant_id,
        actor=RequestActor(type=ActorType.TENANT_USER, id=str(user_id)),
        userId=user_id,
        permissions=("organization.read", "organization.settings.write"),
        assuranceLevel=AssuranceLevel.WORKFORCE,
    )

    assert context.tenant_id == tenant_id
    assert context.user_id == user_id
    assert context.customer_id is None
    assert context.has_permission("organization.settings.write")
    assert context.model_dump(mode="json", by_alias=True) == {
        "requestId": "req-workforce-1",
        "tenantId": str(tenant_id),
        "actor": {"type": "tenant_user", "id": str(user_id)},
        "userId": str(user_id),
        "customerId": None,
        "permissions": ["organization.read", "organization.settings.write"],
        "assuranceLevel": "workforce",
    }


def test_valid_verified_customer_context() -> None:
    customer_id = uuid4()
    context = RequestContext(
        requestId="req-customer-1",
        tenantId=uuid4(),
        actor=RequestActor(type=ActorType.CUSTOMER, id=str(customer_id)),
        customerId=customer_id,
        assuranceLevel=AssuranceLevel.VERIFIED,
    )

    assert context.user_id is None
    assert context.customer_id == customer_id
    assert context.assurance_level is AssuranceLevel.VERIFIED


def test_anonymous_customer_does_not_invent_user_identity() -> None:
    context = RequestContext(
        requestId="req-anonymous-1",
        tenantId=uuid4(),
        actor=RequestActor(type=ActorType.CUSTOMER, id="anonymous-session"),
        assuranceLevel=AssuranceLevel.ANONYMOUS,
    )

    assert context.user_id is None
    assert context.customer_id is None
    assert context.permissions == ()


def test_unknown_actor_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RequestActor.model_validate({"type": "unknown", "id": "actor-1"})


def test_unknown_assurance_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RequestContext.model_validate(
            {
                "requestId": "req-invalid-assurance",
                "tenantId": str(uuid4()),
                "actor": {"type": "service", "id": "service-1"},
                "userId": None,
                "customerId": None,
                "permissions": [],
                "assuranceLevel": "trusted-ish",
            }
        )


def test_required_tenant_helper_fails_closed_without_trusted_context() -> None:
    with pytest.raises(MissingTenantContextError) as exc_info:
        require_tenant_id(None)

    assert exc_info.value.error_code == "TENANT_CONTEXT_REQUIRED"
    assert "default" not in str(exc_info.value).lower()


def test_required_tenant_helper_returns_only_trusted_context_tenant() -> None:
    tenant_id = uuid4()
    context = RequestContext(
        requestId="req-tenant-1",
        tenantId=tenant_id,
        actor=RequestActor(type=ActorType.SERVICE, id="worker"),
        assuranceLevel=AssuranceLevel.WORKFORCE,
    )

    resolved: UUID = require_tenant_id(context)
    assert resolved == tenant_id


def test_context_and_nested_actor_are_immutable_after_construction() -> None:
    context = RequestContext(
        requestId="req-frozen",
        tenantId=uuid4(),
        actor=RequestActor(type=ActorType.SERVICE, id="service-1"),
        permissions=("audit.read",),
        assuranceLevel=AssuranceLevel.WORKFORCE,
    )

    with pytest.raises(ValidationError):
        context.request_id = "changed"

    with pytest.raises(ValidationError):
        context.actor.id = "changed"

    assert context.permissions == ("audit.read",)
