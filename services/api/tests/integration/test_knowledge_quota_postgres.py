from __future__ import annotations

import asyncio
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.core.config import load_settings
from app.core.database import create_database_engine, create_database_session_factory
from app.modules.knowledge.errors import (
    KnowledgeSourceQuotaExceededError,
    KnowledgeStorageQuotaExceededError,
    KnowledgeUploadConcurrencyLimitedError,
)
from app.modules.knowledge.quota import (
    KNOWLEDGE_STORED_BYTE_LIMIT,
    MAX_KNOWLEDGE_FILE_BYTES,
    KnowledgeUploadReservationClaim,
    reserve_file_upload,
)
from tests.support.tenant_isolation import (
    TenantIsolationFixture,
    cleanup_tenant_isolation_fixture,
    seed_tenant_isolation_fixture,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


def test_postgres_quota_reservations_are_atomic_and_tenant_scoped() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        fixture = TenantIsolationFixture.new()
        seeded = False
        try:
            async with session_factory() as session, session.begin():
                await seed_tenant_isolation_fixture(session, fixture)
                seeded = True

            async def reserve_one() -> KnowledgeUploadReservationClaim:
                async with session_factory() as session:
                    return await reserve_file_upload(
                        session,
                        tenant_id=fixture.tenant_a,
                        source_id=uuid4(),
                        reserved_bytes=1024,
                    )

            results = await asyncio.gather(*(reserve_one() for _ in range(4)), return_exceptions=True)
            claims = [result for result in results if isinstance(result, KnowledgeUploadReservationClaim)]
            rejected = [
                result
                for result in results
                if isinstance(result, KnowledgeUploadConcurrencyLimitedError)
            ]
            assert len(claims) == 3
            assert len(rejected) == 1

            async with session_factory() as session, session.begin():
                active_count = (
                    await session.execute(
                        text(
                            "SELECT count(*) FROM knowledge_upload_reservations "
                            "WHERE tenant_id=:tenant AND lease_expires_at > now()"
                        ),
                        {"tenant": fixture.tenant_a},
                    )
                ).scalar_one()
                assert active_count == 3
                await session.execute(
                    text("DELETE FROM knowledge_upload_reservations WHERE tenant_id=:tenant"),
                    {"tenant": fixture.tenant_a},
                )

            # Forty 25-MiB committed files consume 1,000 MiB, leaving less than one
            # additional maximum-size file under the frozen 1-GiB byte ceiling.
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
                            "name": f"quota-byte-{index}",
                            "object_key": (
                                f"tenants/{fixture.tenant_a}/knowledge/{source_id}/raw/{uuid4()}"
                            ),
                            "size": MAX_KNOWLEDGE_FILE_BYTES,
                            "created_by": fixture.owner_a,
                        },
                    )

            assert 40 * MAX_KNOWLEDGE_FILE_BYTES < KNOWLEDGE_STORED_BYTE_LIMIT
            assert 41 * MAX_KNOWLEDGE_FILE_BYTES > KNOWLEDGE_STORED_BYTE_LIMIT
            async with session_factory() as session:
                with pytest.raises(KnowledgeStorageQuotaExceededError):
                    await reserve_file_upload(
                        session,
                        tenant_id=fixture.tenant_a,
                        source_id=uuid4(),
                        reserved_bytes=MAX_KNOWLEDGE_FILE_BYTES,
                    )

            # Foreign tenant capacity is independent even while tenant A is near its byte cap.
            async with session_factory() as session:
                foreign_claim = await reserve_file_upload(
                    session,
                    tenant_id=fixture.tenant_b,
                    source_id=uuid4(),
                    reserved_bytes=MAX_KNOWLEDGE_FILE_BYTES,
                )
                assert foreign_claim.reserved_bytes == MAX_KNOWLEDGE_FILE_BYTES

            async with session_factory() as session, session.begin():
                await session.execute(
                    text("DELETE FROM knowledge_upload_reservations WHERE tenant_id=:tenant"),
                    {"tenant": fixture.tenant_b},
                )
                await session.execute(
                    text(
                        "DELETE FROM knowledge_sources "
                        "WHERE tenant_id=:tenant AND name LIKE 'quota-byte-%'"
                    ),
                    {"tenant": fixture.tenant_a},
                )

                for index in range(100):
                    await session.execute(
                        text(
                            """
                            INSERT INTO knowledge_sources (
                              id, tenant_id, source_type, name, source_uri, object_key,
                              object_size_bytes, access_scope, status, sync_version,
                              last_synced_at, last_error_code, created_by, created_at, updated_at
                            ) VALUES (
                              :id, :tenant, 'url', :name, :uri, NULL,
                              NULL, 'customer', 'pending', 0,
                              NULL, NULL, :created_by, now(), now()
                            )
                            """
                        ),
                        {
                            "id": uuid4(),
                            "tenant": fixture.tenant_a,
                            "name": f"quota-source-{index}",
                            "uri": f"https://example.test/quota/{index}",
                            "created_by": fixture.owner_a,
                        },
                    )

            async with session_factory() as session:
                with pytest.raises(KnowledgeSourceQuotaExceededError):
                    await reserve_file_upload(
                        session,
                        tenant_id=fixture.tenant_a,
                        source_id=uuid4(),
                        reserved_bytes=1,
                    )

            async with session_factory() as session, session.begin():
                await session.execute(
                    text(
                        "DELETE FROM knowledge_sources "
                        "WHERE tenant_id=:tenant AND name LIKE 'quota-source-%'"
                    ),
                    {"tenant": fixture.tenant_a},
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
                            "WHERE tenant_id IN (:a, :b)"
                        ),
                        {"a": fixture.tenant_a, "b": fixture.tenant_b},
                    )
                    await cleanup_tenant_isolation_fixture(session, fixture)
            await engine.dispose()

    asyncio.run(scenario())
