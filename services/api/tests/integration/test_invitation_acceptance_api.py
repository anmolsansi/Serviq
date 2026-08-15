from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.modules.tenancy.service as tenancy_service
from app.core.auth import VerifiedWorkforceIdentity
from app.core.config import load_settings
from app.core.database import (
    create_database_engine,
    create_database_session_factory,
    get_database_session,
)
from app.core.principal import (
    require_verified_workforce_identity,
    require_workforce_user_id,
)
from app.main import app
from app.modules.invitations.schemas import InvitationAcceptRequest
from app.modules.invitations.security import hash_invitation_token
from app.modules.invitations.service import accept_invitation

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)

ACCEPT_PATH = "/api/v1/invitations/accept"
ISSUER = "https://ope286.test"


def _identity(email: str | None, *, verified: bool = True) -> VerifiedWorkforceIdentity:
    return VerifiedWorkforceIdentity(
        issuer=ISSUER,
        subject=f"subject-{uuid4().hex}",
        email=email,
        email_verified=verified,
        display_name="Invitee",
    )


def _install_overrides(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: UUID | None,
    identity: VerifiedWorkforceIdentity | None,
) -> None:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_database_session] = override_session
    if user_id is None:
        app.dependency_overrides.pop(require_workforce_user_id, None)
    else:
        app.dependency_overrides[require_workforce_user_id] = lambda: user_id
    if identity is None:
        app.dependency_overrides.pop(require_verified_workforce_identity, None)
    else:
        app.dependency_overrides[require_verified_workforce_identity] = lambda: identity


def _clear_overrides() -> None:
    app.dependency_overrides.pop(get_database_session, None)
    app.dependency_overrides.pop(require_workforce_user_id, None)
    app.dependency_overrides.pop(require_verified_workforce_identity, None)


def _ids() -> dict[str, UUID]:
    names = (
        "tenant_a",
        "tenant_b",
        "inviter",
        "invitee",
        "wrong_user",
        "concurrent_user",
        "suspended_user",
        "rollback_user",
        "role_a",
        "role_b",
        "existing_role",
        "suspended_membership",
    )
    return {name: uuid4() for name in names}


async def _seed_base(session: AsyncSession, ids: dict[str, UUID]) -> None:
    await session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, status, default_locale)
            VALUES (:tenant_a, :slug_a, 'Acceptance Tenant A', 'active', 'en'),
                   (:tenant_b, :slug_b, 'Acceptance Tenant B', 'active', 'en')
            """
        ),
        {
            **ids,
            "slug_a": f"ope286-a-{ids['tenant_a'].hex[:10]}",
            "slug_b": f"ope286-b-{ids['tenant_b'].hex[:10]}",
        },
    )
    for key, email in (
        ("inviter", "inviter@example.com"),
        ("invitee", "invitee@example.com"),
        ("wrong_user", "wrong@example.com"),
        ("concurrent_user", "concurrent@example.com"),
        ("suspended_user", "suspended@example.com"),
        ("rollback_user", "rollback@example.com"),
    ):
        await session.execute(
            text(
                """
                INSERT INTO users (id, oidc_issuer, oidc_subject, email, display_name, status)
                VALUES (:id, :issuer, :subject, :email, :display_name, 'active')
                """
            ),
            {
                "id": ids[key],
                "issuer": ISSUER,
                "subject": f"{key}-{ids[key].hex}",
                "email": email,
                "display_name": key.replace("_", " ").title(),
            },
        )
    await session.execute(
        text(
            """
            INSERT INTO roles (id, tenant_id, key, display_name, is_system)
            VALUES (:role_a, :tenant_a, :role_a_key, 'Tenant A Invite Role', false),
                   (:role_b, :tenant_b, :role_b_key, 'Tenant B Foreign Role', false),
                   (:existing_role, :tenant_a, :existing_role_key, 'Existing Role', false)
            """
        ),
        {
            **ids,
            "role_a_key": f"invite-a-{ids['role_a'].hex}",
            "role_b_key": f"invite-b-{ids['role_b'].hex}",
            "existing_role_key": f"existing-{ids['existing_role'].hex}",
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO memberships (id, tenant_id, user_id, status)
            VALUES (:suspended_membership, :tenant_a, :suspended_user, 'suspended')
            """
        ),
        ids,
    )
    await session.execute(
        text(
            """
            INSERT INTO membership_roles (membership_id, role_id)
            VALUES (:suspended_membership, :existing_role)
            """
        ),
        ids,
    )


async def _insert_invitation(
    session: AsyncSession,
    ids: dict[str, UUID],
    *,
    token: str,
    email: str,
    role_id: UUID | None = None,
    status: str = "pending",
    expires_at: datetime | None = None,
    accepted_by_user_id: UUID | None = None,
) -> UUID:
    invitation_id = uuid4()
    now = datetime.now(UTC)
    accepted = status == "accepted"
    await session.execute(
        text(
            """
            INSERT INTO organization_invitations (
                id, tenant_id, email_normalized, token_hash, status,
                invited_by_user_id, accepted_by_user_id, expires_at,
                accepted_at, revoked_at
            )
            VALUES (
                :id, :tenant_id, :email, :token_hash, :status,
                :inviter, :accepted_by, :expires_at,
                :accepted_at, :revoked_at
            )
            """
        ),
        {
            "id": invitation_id,
            "tenant_id": ids["tenant_a"],
            "email": email,
            "token_hash": hash_invitation_token(token),
            "status": status,
            "inviter": ids["inviter"],
            "accepted_by": accepted_by_user_id,
            "expires_at": expires_at or now + timedelta(days=7),
            "accepted_at": now if accepted else None,
            "revoked_at": now if status == "revoked" else None,
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO organization_invitation_roles (invitation_id, role_id)
            VALUES (:invitation_id, :role_id)
            """
        ),
        {"invitation_id": invitation_id, "role_id": role_id or ids["role_a"]},
    )
    return invitation_id


async def _cleanup(session: AsyncSession, ids: dict[str, UUID]) -> None:
    await session.execute(
        text(
            """
            DELETE FROM membership_roles
            WHERE membership_id IN (
                SELECT id FROM memberships
                WHERE tenant_id IN (:tenant_a, :tenant_b)
            )
            """
        ),
        ids,
    )
    await session.execute(
        text(
            """
            DELETE FROM memberships
            WHERE tenant_id IN (:tenant_a, :tenant_b)
            """
        ),
        ids,
    )
    await session.execute(
        text(
            """
            DELETE FROM organization_invitation_roles
            WHERE invitation_id IN (
                SELECT id FROM organization_invitations
                WHERE tenant_id IN (:tenant_a, :tenant_b)
            )
            """
        ),
        ids,
    )
    await session.execute(
        text(
            """
            DELETE FROM organization_invitations
            WHERE tenant_id IN (:tenant_a, :tenant_b)
            """
        ),
        ids,
    )
    await session.execute(
        text("DELETE FROM roles WHERE id IN (:role_a, :role_b, :existing_role)"),
        ids,
    )
    for key in (
        "inviter",
        "invitee",
        "wrong_user",
        "concurrent_user",
        "suspended_user",
        "rollback_user",
    ):
        await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": ids[key]})
    await session.execute(
        text("DELETE FROM tenants WHERE id IN (:tenant_a, :tenant_b)"),
        ids,
    )


def test_invitation_acceptance_security_and_atomicity(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        ids = _ids()
        transport = httpx.ASGITransport(app=app)
        tokens: list[str] = []
        try:
            async with session_factory() as session, session.begin():
                await _seed_base(session, ids)

            valid_token = f"valid-{uuid4().hex}"
            tokens.append(valid_token)
            async with session_factory() as session, session.begin():
                valid_invitation_id = await _insert_invitation(
                    session,
                    ids,
                    token=valid_token,
                    email="invitee@example.com",
                )

            _install_overrides(
                session_factory,
                ids["invitee"],
                _identity(" INVITEE@EXAMPLE.COM "),
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                accepted = await client.post(ACCEPT_PATH, json={"token": valid_token})
                assert accepted.status_code == 200
                payload = accepted.json()["data"]
                assert payload["id"] == str(valid_invitation_id)
                assert payload["status"] == "accepted"
                assert payload["acceptedByUserId"] == str(ids["invitee"])
                assert valid_token not in accepted.text
                assert hash_invitation_token(valid_token) not in accepted.text

                repeated = await client.post(ACCEPT_PATH, json={"token": valid_token})
                assert repeated.status_code == 409
                assert repeated.json()["error"]["code"] == "INVITATION_ACCEPTANCE_REJECTED"
                assert valid_token not in repeated.text

            async with session_factory() as session:
                row = (
                    await session.execute(
                        text(
                            """
                            SELECT m.id, m.status, m.created_by_invitation_id,
                                   i.status AS invitation_status,
                                   COUNT(mr.id) AS role_count
                            FROM memberships m
                            JOIN organization_invitations i ON i.id = :invitation_id
                            LEFT JOIN membership_roles mr ON mr.membership_id = m.id
                            WHERE m.tenant_id = :tenant_id AND m.user_id = :user_id
                            GROUP BY m.id, i.status
                            """
                        ),
                        {
                            "invitation_id": valid_invitation_id,
                            "tenant_id": ids["tenant_a"],
                            "user_id": ids["invitee"],
                        },
                    )
                ).one()
                assert row.status == "active"
                assert row.created_by_invitation_id == valid_invitation_id
                assert row.invitation_status == "accepted"
                assert row.role_count == 1

            wrong_token = f"wrong-email-{uuid4().hex}"
            tokens.append(wrong_token)
            async with session_factory() as session, session.begin():
                wrong_invitation_id = await _insert_invitation(
                    session,
                    ids,
                    token=wrong_token,
                    email="invitee@example.com",
                )
            _install_overrides(
                session_factory,
                ids["wrong_user"],
                _identity("wrong@example.com"),
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                wrong_email = await client.post(ACCEPT_PATH, json={"token": wrong_token})
                assert wrong_email.status_code == 409
                assert wrong_email.json()["error"]["code"] == "INVITATION_ACCEPTANCE_REJECTED"

            _install_overrides(
                session_factory,
                ids["wrong_user"],
                _identity("invitee@example.com", verified=False),
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                unverified = await client.post(ACCEPT_PATH, json={"token": wrong_token})
                assert unverified.status_code == 403
                assert unverified.json()["error"]["code"] == "VERIFIED_EMAIL_REQUIRED"

            invalid_token = f"invalid-{uuid4().hex}"
            tokens.append(invalid_token)
            _install_overrides(
                session_factory,
                ids["wrong_user"],
                _identity("wrong@example.com"),
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                invalid = await client.post(ACCEPT_PATH, json={"token": invalid_token})
                assert invalid.status_code == 409
                assert invalid_token not in invalid.text

            for lifecycle_status in ("revoked", "accepted"):
                lifecycle_token = f"{lifecycle_status}-{uuid4().hex}"
                tokens.append(lifecycle_token)
                async with session_factory() as session, session.begin():
                    await _insert_invitation(
                        session,
                        ids,
                        token=lifecycle_token,
                        email="wrong@example.com",
                        status=lifecycle_status,
                        accepted_by_user_id=(
                            ids["wrong_user"] if lifecycle_status == "accepted" else None
                        ),
                    )
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    rejected = await client.post(
                        ACCEPT_PATH,
                        json={"token": lifecycle_token},
                    )
                    assert rejected.status_code == 409

            expired_token = f"expired-{uuid4().hex}"
            tokens.append(expired_token)
            async with session_factory() as session, session.begin():
                await _insert_invitation(
                    session,
                    ids,
                    token=expired_token,
                    email="wrong@example.com",
                    expires_at=datetime.now(UTC) - timedelta(seconds=1),
                )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                expired = await client.post(ACCEPT_PATH, json={"token": expired_token})
                assert expired.status_code == 409

            foreign_role_token = f"foreign-role-{uuid4().hex}"
            tokens.append(foreign_role_token)
            async with session_factory() as session, session.begin():
                await _insert_invitation(
                    session,
                    ids,
                    token=foreign_role_token,
                    email="wrong@example.com",
                    role_id=ids["role_b"],
                )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                corrupted = await client.post(
                    ACCEPT_PATH,
                    json={"token": foreign_role_token},
                )
                assert corrupted.status_code == 409

            concurrent_token = f"concurrent-{uuid4().hex}"
            tokens.append(concurrent_token)
            async with session_factory() as session, session.begin():
                concurrent_invitation_id = await _insert_invitation(
                    session,
                    ids,
                    token=concurrent_token,
                    email="concurrent@example.com",
                )
            _install_overrides(
                session_factory,
                ids["concurrent_user"],
                _identity("concurrent@example.com"),
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                first, second = await asyncio.gather(
                    client.post(ACCEPT_PATH, json={"token": concurrent_token}),
                    client.post(ACCEPT_PATH, json={"token": concurrent_token}),
                )
            assert sorted((first.status_code, second.status_code)) == [200, 409]
            async with session_factory() as session:
                counts = (
                    await session.execute(
                        text(
                            """
                            SELECT
                              (SELECT COUNT(*) FROM memberships
                               WHERE tenant_id=:tenant AND user_id=:user_id) AS memberships,
                              (SELECT COUNT(*) FROM membership_roles mr
                               JOIN memberships m ON m.id=mr.membership_id
                               WHERE m.tenant_id=:tenant AND m.user_id=:user_id) AS roles,
                              (SELECT status FROM organization_invitations
                               WHERE id=:invitation_id) AS invitation_status
                            """
                        ),
                        {
                            "tenant": ids["tenant_a"],
                            "user_id": ids["concurrent_user"],
                            "invitation_id": concurrent_invitation_id,
                        },
                    )
                ).one()
                assert counts.memberships == 1
                assert counts.roles == 1
                assert counts.invitation_status == "accepted"

            suspended_token = f"suspended-{uuid4().hex}"
            tokens.append(suspended_token)
            async with session_factory() as session, session.begin():
                suspended_invitation_id = await _insert_invitation(
                    session,
                    ids,
                    token=suspended_token,
                    email="suspended@example.com",
                )
            _install_overrides(
                session_factory,
                ids["suspended_user"],
                _identity("suspended@example.com"),
            )
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                activated = await client.post(ACCEPT_PATH, json={"token": suspended_token})
                assert activated.status_code == 200
            async with session_factory() as session:
                suspended = (
                    await session.execute(
                        text(
                            """
                            SELECT m.status, m.created_by_invitation_id, COUNT(mr.id) AS role_count
                            FROM memberships m
                            LEFT JOIN membership_roles mr ON mr.membership_id=m.id
                            WHERE m.id=:membership_id
                            GROUP BY m.id
                            """
                        ),
                        {"membership_id": ids["suspended_membership"]},
                    )
                ).one()
                assert suspended.status == "active"
                assert suspended.created_by_invitation_id is None
                assert suspended.role_count == 2
            async with session_factory() as session:
                accepted_status = await session.scalar(
                    text("SELECT status FROM organization_invitations WHERE id=:id"),
                    {"id": suspended_invitation_id},
                )
                assert accepted_status == "accepted"

            rollback_token = f"rollback-{uuid4().hex}"
            tokens.append(rollback_token)
            async with session_factory() as session, session.begin():
                rollback_invitation_id = await _insert_invitation(
                    session,
                    ids,
                    token=rollback_token,
                    email="rollback@example.com",
                )

            original_add_membership_role = tenancy_service.add_membership_role

            def fail_role_mapping(*args: object, **kwargs: object) -> object:
                raise RuntimeError("forced role mapping failure")

            monkeypatch.setattr(tenancy_service, "add_membership_role", fail_role_mapping)
            async with session_factory() as session:
                with pytest.raises(RuntimeError, match="forced role mapping failure"):
                    await accept_invitation(
                        session,
                        user_id=ids["rollback_user"],
                        identity=_identity("rollback@example.com"),
                        request=InvitationAcceptRequest(token=rollback_token),
                    )
            monkeypatch.setattr(
                tenancy_service,
                "add_membership_role",
                original_add_membership_role,
            )
            async with session_factory() as session:
                rollback_state = (
                    await session.execute(
                        text(
                            """
                            SELECT
                              (SELECT status FROM organization_invitations WHERE id=:invitation_id)
                                AS invitation_status,
                              (SELECT COUNT(*) FROM memberships
                               WHERE tenant_id=:tenant AND user_id=:user_id) AS membership_count
                            """
                        ),
                        {
                            "invitation_id": rollback_invitation_id,
                            "tenant": ids["tenant_a"],
                            "user_id": ids["rollback_user"],
                        },
                    )
                ).one()
                assert rollback_state.invitation_status == "pending"
                assert rollback_state.membership_count == 0

            async with session_factory() as session:
                wrong_status = await session.scalar(
                    text("SELECT status FROM organization_invitations WHERE id=:id"),
                    {"id": wrong_invitation_id},
                )
                assert wrong_status == "pending"

            for token in tokens:
                assert token not in caplog.text
                assert hash_invitation_token(token) not in caplog.text
        finally:
            _clear_overrides()
            async with session_factory() as session, session.begin():
                await _cleanup(session, ids)
            await engine.dispose()

    asyncio.run(scenario())
