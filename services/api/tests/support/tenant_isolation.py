"""Reusable real-PostgreSQL tenant-isolation fixture and assertions."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class TenantIsolationFixture:
    """Known tenant A/B identities deliberately containing overlapping values."""

    tenant_a: UUID
    tenant_b: UUID
    owner_a: UUID
    owner_b: UUID
    member_a: UUID
    member_b: UUID
    owner_membership_a: UUID
    owner_membership_b: UUID
    member_membership_a: UUID
    member_membership_b: UUID
    role_a: UUID
    role_b: UUID

    @classmethod
    def new(cls) -> TenantIsolationFixture:
        return cls(*(uuid4() for _ in range(12)))


async def seed_tenant_isolation_fixture(
    session: AsyncSession,
    fixture: TenantIsolationFixture,
) -> None:
    """Create two independent tenants with intentionally similar human-facing data."""

    f = fixture
    await session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, status, default_locale)
            VALUES (:tenant_a, :slug_a, 'Shared Organization', 'active', 'en'),
                   (:tenant_b, :slug_b, 'Shared Organization', 'active', 'en')
            """
        ),
        {
            "tenant_a": f.tenant_a,
            "tenant_b": f.tenant_b,
            "slug_a": f"isolation-a-{f.tenant_a.hex[:12]}",
            "slug_b": f"isolation-b-{f.tenant_b.hex[:12]}",
        },
    )

    for user_id, subject_suffix in (
        (f.owner_a, "owner-a"),
        (f.owner_b, "owner-b"),
        (f.member_a, "member-a"),
        (f.member_b, "member-b"),
    ):
        await session.execute(
            text(
                """
                INSERT INTO users (
                    id, oidc_issuer, oidc_subject, email, display_name, status
                ) VALUES (
                    :id, 'https://tenant-isolation.test', :subject,
                    'shared-person@example.com', 'Shared Person', 'active'
                )
                """
            ),
            {"id": user_id, "subject": f"{subject_suffix}-{user_id.hex}"},
        )

    await session.execute(
        text(
            """
            INSERT INTO roles (id, tenant_id, key, display_name, is_system)
            VALUES (:role_a, :tenant_a, :role_key_a, 'Shared Agent', false),
                   (:role_b, :tenant_b, :role_key_b, 'Shared Agent', false)
            """
        ),
        {
            "role_a": f.role_a,
            "role_b": f.role_b,
            "tenant_a": f.tenant_a,
            "tenant_b": f.tenant_b,
            "role_key_a": f"shared-agent-{f.tenant_a.hex}",
            "role_key_b": f"shared-agent-{f.tenant_b.hex}",
        },
    )

    await session.execute(
        text(
            """
            INSERT INTO memberships (id, tenant_id, user_id, status)
            VALUES (:owner_membership_a, :tenant_a, :owner_a, 'active'),
                   (:owner_membership_b, :tenant_b, :owner_b, 'active'),
                   (:member_membership_a, :tenant_a, :member_a, 'active'),
                   (:member_membership_b, :tenant_b, :member_b, 'active')
            """
        ),
        f.__dict__,
    )

    await session.execute(
        text(
            """
            INSERT INTO membership_roles (membership_id, role_id)
            SELECT :owner_membership_a, id FROM roles
              WHERE tenant_id IS NULL AND is_system=true AND key='owner'
            UNION ALL
            SELECT :owner_membership_b, id FROM roles
              WHERE tenant_id IS NULL AND is_system=true AND key='owner'
            UNION ALL SELECT :member_membership_a, :role_a
            UNION ALL SELECT :member_membership_b, :role_b
            """
        ),
        f.__dict__,
    )


async def cleanup_tenant_isolation_fixture(
    session: AsyncSession,
    fixture: TenantIsolationFixture,
) -> None:
    """Remove only rows owned by this fixture, leaving shared role bootstrap untouched."""

    f = fixture
    # V1.3.04B reservations deliberately RESTRICT tenant deletion so production
    # cleanup cannot silently discard possible raw-object obligations. Test fixtures
    # explicitly own their synthetic reservations and may remove them first.
    await session.execute(
        text(
            "DELETE FROM knowledge_upload_reservations "
            "WHERE tenant_id IN (:tenant_a, :tenant_b)"
        ),
        f.__dict__,
    )
    await session.execute(
        text(
            """
            DELETE FROM membership_roles
            WHERE membership_id IN (
              :owner_membership_a, :owner_membership_b,
              :member_membership_a, :member_membership_b
            )
            """
        ),
        f.__dict__,
    )
    await session.execute(
        text(
            """
            DELETE FROM memberships
            WHERE id IN (
              :owner_membership_a, :owner_membership_b,
              :member_membership_a, :member_membership_b
            )
            """
        ),
        f.__dict__,
    )
    await session.execute(
        text("DELETE FROM roles WHERE id IN (:role_a, :role_b)"),
        f.__dict__,
    )
    await session.execute(
        text("DELETE FROM users WHERE id IN (:owner_a, :owner_b, :member_a, :member_b)"),
        f.__dict__,
    )
    await session.execute(
        text("DELETE FROM tenants WHERE id IN (:tenant_a, :tenant_b)"),
        f.__dict__,
    )


def assert_list_excludes_foreign[T](
    items: Iterable[T],
    *,
    foreign_id: UUID,
    id_of: Callable[[T], UUID],
) -> None:
    """Prove a tenant-scoped list contains no known foreign resource UUID."""

    assert foreign_id not in {id_of(item) for item in items}


def assert_foreign_resource_hidden(status_code: int) -> None:
    """Use for get/update/delete attacks with a known foreign UUID."""

    assert status_code == 404


def assert_value_unchanged[T](*, before: T, after: T) -> None:
    """Prove a rejected foreign mutation did not alter persisted data."""

    assert after == before
