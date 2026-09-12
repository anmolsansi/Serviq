from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.core.config import load_settings
from app.core.database import create_database_engine, create_database_session_factory
from app.core.rate_limits import RateLimitDecision
from app.modules.knowledge import router as knowledge_router
from app.modules.knowledge.errors import (
    KnowledgeStorageQuotaExceededError,
    KnowledgeUploadConcurrencyLimitedError,
)
from app.modules.knowledge.quota import (
    MAX_KNOWLEDGE_FILE_BYTES,
    finalize_file_upload_reservation,
    release_unlinked_reservation,
    reserve_file_upload,
)
from starlette.requests import Request
from starlette.types import Message
from tests.support.tenant_isolation import (
    TenantIsolationFixture,
    cleanup_tenant_isolation_fixture,
    seed_tenant_isolation_fixture,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


class _AlwaysAllowLimiter:
    async def check_and_consume(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
    ) -> RateLimitDecision:
        del tenant_id, user_id
        return RateLimitDecision(allowed=True)


def test_zero_byte_admission_finalizes_exact_bytes_and_rejects_over_quota() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        fixture = TenantIsolationFixture.new()
        seeded = False
        try:
            async with session_factory() as session, session.begin():
                await seed_tenant_isolation_fixture(session, fixture)
                seeded = True

            async with session_factory() as session:
                admission = await reserve_file_upload(
                    session,
                    tenant_id=fixture.tenant_a,
                    source_id=uuid4(),
                    reserved_bytes=0,
                )
                finalized = await finalize_file_upload_reservation(
                    session,
                    tenant_id=fixture.tenant_a,
                    admission=admission,
                    reserved_bytes=1234,
                )
                assert finalized.reserved_bytes == 1234
                row = (
                    await session.execute(
                        text(
                            "SELECT reserved_bytes FROM knowledge_upload_reservations "
                            "WHERE tenant_id=:tenant AND id=:reservation_id"
                        ),
                        {
                            "tenant": fixture.tenant_a,
                            "reservation_id": admission.reservation_id,
                        },
                    )
                ).one()
                assert row.reserved_bytes == 1234
                await session.rollback()
                await release_unlinked_reservation(
                    session,
                    tenant_id=fixture.tenant_a,
                    reservation_id=admission.reservation_id,
                )

            async with session_factory() as session, session.begin():
                for index in range(40):
                    source_id = uuid4()
                    await session.execute(
                        text(
                            """
                            INSERT INTO knowledge_sources (
                              id, tenant_id, source_type, name, source_uri, object_key,
                              object_size_bytes, access_scope, status, sync_version,
                              last_synced_at, last_error_code, created_by, created_at, updated_at
                            ) VALUES (
                              :id, :tenant, 'pdf', :name, NULL, :object_key,
                              :size, 'customer', 'pending', 0,
                              NULL, NULL, :created_by, now(), now()
                            )
                            """
                        ),
                        {
                            "id": source_id,
                            "tenant": fixture.tenant_a,
                            "name": f"admission-byte-{index}",
                            "object_key": (
                                f"tenants/{fixture.tenant_a}/knowledge/{source_id}/raw/{uuid4()}"
                            ),
                            "size": MAX_KNOWLEDGE_FILE_BYTES,
                            "created_by": fixture.owner_a,
                        },
                    )

            async with session_factory() as session:
                admission = await reserve_file_upload(
                    session,
                    tenant_id=fixture.tenant_a,
                    source_id=uuid4(),
                    reserved_bytes=0,
                )
                with pytest.raises(KnowledgeStorageQuotaExceededError):
                    await finalize_file_upload_reservation(
                        session,
                        tenant_id=fixture.tenant_a,
                        admission=admission,
                        reserved_bytes=MAX_KNOWLEDGE_FILE_BYTES,
                    )
                row = (
                    await session.execute(
                        text(
                            "SELECT reserved_bytes FROM knowledge_upload_reservations "
                            "WHERE tenant_id=:tenant AND id=:reservation_id"
                        ),
                        {
                            "tenant": fixture.tenant_a,
                            "reservation_id": admission.reservation_id,
                        },
                    )
                ).one()
                assert row.reserved_bytes == 0
                await session.rollback()
                await release_unlinked_reservation(
                    session,
                    tenant_id=fixture.tenant_a,
                    reservation_id=admission.reservation_id,
                )
        finally:
            if seeded:
                async with session_factory() as session, session.begin():
                    await session.execute(
                        text(
                            "DELETE FROM knowledge_upload_reservations "
                            "WHERE tenant_id IN (:a, :b)"
                        ),
                        {"a": fixture.tenant_a, "b": fixture.tenant_b},
                    )
                    await session.execute(
                        text(
                            "DELETE FROM knowledge_sources "
                            "WHERE tenant_id=:tenant AND name LIKE 'admission-byte-%'"
                        ),
                        {"tenant": fixture.tenant_a},
                    )
                    await cleanup_tenant_isolation_fixture(session, fixture)
            await engine.dispose()

    asyncio.run(scenario())


def test_fourth_concurrent_upload_is_rejected_before_body_receive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        fixture = TenantIsolationFixture.new()
        seeded = False
        try:
            async with session_factory() as session, session.begin():
                await seed_tenant_isolation_fixture(session, fixture)
                seeded = True

            claims = []
            async with session_factory() as session:
                for _ in range(3):
                    claims.append(
                        await reserve_file_upload(
                            session,
                            tenant_id=fixture.tenant_a,
                            source_id=uuid4(),
                            reserved_bytes=0,
                        )
                    )

            body_received = False

            async def receive() -> Message:
                nonlocal body_received
                body_received = True
                raise AssertionError("multipart body must not be consumed before admission")

            request = Request(
                {
                    "type": "http",
                    "http_version": "1.1",
                    "method": "POST",
                    "scheme": "http",
                    "path": "/api/v1/knowledge-sources",
                    "raw_path": b"/api/v1/knowledge-sources",
                    "query_string": b"",
                    "headers": [
                        (b"content-type", b"multipart/form-data; boundary=serviq-boundary")
                    ],
                    "client": ("127.0.0.1", 1234),
                    "server": ("test", 80),
                },
                receive,
            )
            monkeypatch.setattr(
                knowledge_router,
                "get_knowledge_object_storage",
                lambda: object(),
            )

            async with session_factory() as session:
                response = await knowledge_router._create_file_knowledge_source(
                    request,
                    session=session,
                    user_id=fixture.owner_a,
                    tenant_id=fixture.tenant_a,
                    upload_rate_limiter=_AlwaysAllowLimiter(),
                )
            assert response.status_code == 429
            payload = json.loads(response.body)
            assert payload["error"]["code"] == "KNOWLEDGE_UPLOAD_CONCURRENCY_LIMITED"
            assert not body_received

            async with session_factory() as session:
                with pytest.raises(KnowledgeUploadConcurrencyLimitedError):
                    await reserve_file_upload(
                        session,
                        tenant_id=fixture.tenant_a,
                        source_id=uuid4(),
                        reserved_bytes=0,
                    )
        finally:
            if seeded:
                async with session_factory() as session, session.begin():
                    await session.execute(
                        text(
                            "DELETE FROM knowledge_upload_reservations "
                            "WHERE tenant_id IN (:a, :b)"
                        ),
                        {"a": fixture.tenant_a, "b": fixture.tenant_b},
                    )
                    await cleanup_tenant_isolation_fixture(session, fixture)
            await engine.dispose()

    asyncio.run(scenario())
