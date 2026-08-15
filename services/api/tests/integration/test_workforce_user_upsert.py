from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update

from app.core.auth import VerifiedWorkforceIdentity
from app.core.config import load_settings
from app.core.database import create_database_engine, create_database_session_factory
from app.modules.workforce.errors import (
    DisabledWorkforceUserError,
    WorkforceIdentityProfileError,
)
from app.modules.workforce.models import User
from app.modules.workforce.schemas import InternalWorkforceUser
from app.modules.workforce.service import upsert_verified_workforce_user

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)

TEST_ISSUER_PREFIX = "https://ope281.test/"


def _identity(
    *,
    issuer: str,
    subject: str,
    email: str | None = "first@example.com",
    display_name: str | None = "First User",
) -> VerifiedWorkforceIdentity:
    return VerifiedWorkforceIdentity(
        issuer=issuer,
        subject=subject,
        email=email,
        email_verified=True,
        display_name=display_name,
    )


def test_verified_workforce_user_lifecycle_and_identity_key() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        suffix = uuid4().hex
        issuer_a = f"{TEST_ISSUER_PREFIX}issuer-a-{suffix}"
        issuer_b = f"{TEST_ISSUER_PREFIX}issuer-b-{suffix}"
        subject = f"subject-{suffix}"
        try:
            async with session_factory() as session:
                first = await upsert_verified_workforce_user(
                    session,
                    _identity(issuer=issuer_a, subject=subject),
                )
                repeated = await upsert_verified_workforce_user(
                    session,
                    _identity(
                        issuer=issuer_a,
                        subject=subject,
                        email="updated@example.com",
                        display_name="Updated User",
                    ),
                )
                second_issuer = await upsert_verified_workforce_user(
                    session,
                    _identity(
                        issuer=issuer_b,
                        subject=subject,
                        email="other@example.com",
                        display_name="Other Issuer User",
                    ),
                )

            assert repeated.id == first.id
            assert repeated.email == "updated@example.com"
            assert repeated.display_name == "Updated User"
            assert second_issuer.id != first.id

            async with session_factory() as session:
                count = await session.scalar(
                    select(func.count(User.id)).where(
                        User.oidc_issuer.in_([issuer_a, issuer_b]),
                        User.oidc_subject == subject,
                    )
                )
                assert count == 2
        finally:
            async with session_factory() as session, session.begin():
                await session.execute(
                    delete(User).where(User.oidc_issuer.like(f"{TEST_ISSUER_PREFIX}%"))
                )
            await engine.dispose()

    asyncio.run(scenario())


def test_disabled_user_fails_closed_and_is_not_reenabled() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        suffix = uuid4().hex
        issuer = f"{TEST_ISSUER_PREFIX}disabled-{suffix}"
        subject = f"disabled-{suffix}"
        identity = _identity(issuer=issuer, subject=subject)
        try:
            async with session_factory() as session:
                created = await upsert_verified_workforce_user(session, identity)

            async with session_factory() as session, session.begin():
                await session.execute(
                    update(User).where(User.id == created.id).values(status="disabled")
                )

            async with session_factory() as session:
                with pytest.raises(DisabledWorkforceUserError):
                    await upsert_verified_workforce_user(session, identity)

            async with session_factory() as session:
                status = await session.scalar(select(User.status).where(User.id == created.id))
                assert status == "disabled"
        finally:
            async with session_factory() as session, session.begin():
                await session.execute(delete(User).where(User.oidc_issuer == issuer))
            await engine.dispose()

    asyncio.run(scenario())


def test_concurrent_first_login_resolves_one_stable_user() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        suffix = uuid4().hex
        issuer = f"{TEST_ISSUER_PREFIX}race-{suffix}"
        subject = f"race-{suffix}"
        identity = _identity(issuer=issuer, subject=subject)

        async def login_once() -> InternalWorkforceUser:
            async with session_factory() as session:
                return await upsert_verified_workforce_user(session, identity)

        try:
            first, second = await asyncio.gather(login_once(), login_once())
            assert first.id == second.id

            async with session_factory() as session:
                count = await session.scalar(
                    select(func.count(User.id)).where(
                        User.oidc_issuer == issuer,
                        User.oidc_subject == subject,
                    )
                )
                assert count == 1
        finally:
            async with session_factory() as session, session.begin():
                await session.execute(delete(User).where(User.oidc_issuer == issuer))
            await engine.dispose()

    asyncio.run(scenario())


def test_missing_verified_email_fails_before_database_write() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        suffix = uuid4().hex
        issuer = f"{TEST_ISSUER_PREFIX}missing-email-{suffix}"
        subject = f"missing-email-{suffix}"
        try:
            async with session_factory() as session:
                with pytest.raises(WorkforceIdentityProfileError):
                    await upsert_verified_workforce_user(
                        session,
                        _identity(issuer=issuer, subject=subject, email=None),
                    )

            async with session_factory() as session:
                count = await session.scalar(
                    select(func.count(User.id)).where(User.oidc_issuer == issuer)
                )
                assert count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())
