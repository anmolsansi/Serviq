from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.config import load_settings
from app.core.database import create_database_engine, create_database_session_factory
from app.core.object_storage import build_object_storage, knowledge_raw_key
from app.modules.knowledge.quota import reconcile_legacy_file_sizes, reserve_file_upload
from tests.support.tenant_isolation import (
    TenantIsolationFixture,
    cleanup_tenant_isolation_fixture,
    seed_tenant_isolation_fixture,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_KNOWLEDGE_QUOTA_REAL_STACK") != "1",
    reason="requires real PostgreSQL, Valkey, and S3-compatible integration services",
)


def test_legacy_file_size_reconciliation_uses_real_postgres_and_s3_before_reservation() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        fixture = TenantIsolationFixture.new()
        storage = build_object_storage(load_settings())
        source_id = uuid4()
        object_id = uuid4()
        key = knowledge_raw_key(
            tenant_id=fixture.tenant_a,
            source_id=source_id,
            object_id=object_id,
        )
        payload = b"legacy quota reconciliation evidence"
        seeded = False
        storage.delete_object(key)
        try:
            async with session_factory() as session, session.begin():
                await seed_tenant_isolation_fixture(session, fixture)
                seeded = True
                await session.execute(
                    text(
                        """
                        INSERT INTO knowledge_sources (
                          id, tenant_id, source_type, name, source_uri, object_key,
                          object_size_bytes, access_scope, status, sync_version,
                          last_synced_at, last_error_code, created_by, created_at, updated_at
                        ) VALUES (
                          :id, :tenant, 'text', 'Legacy file', NULL, :object_key,
                          NULL, 'customer', 'pending', 0,
                          NULL, NULL, :created_by, now(), now()
                        )
                        """
                    ),
                    {
                        "id": source_id,
                        "tenant": fixture.tenant_a,
                        "object_key": key.value,
                        "created_by": fixture.owner_a,
                    },
                )

            storage.put_object(
                key,
                payload,
                content_type="text/plain",
                metadata={"original-filename": "legacy.txt"},
            )

            async with session_factory() as session:
                reconciled = await reconcile_legacy_file_sizes(
                    session,
                    storage=storage,
                    tenant_id=fixture.tenant_a,
                )
                assert reconciled == 1

            async with session_factory() as session:
                size = (
                    await session.execute(
                        text(
                            "SELECT object_size_bytes FROM knowledge_sources "
                            "WHERE tenant_id=:tenant AND id=:source"
                        ),
                        {"tenant": fixture.tenant_a, "source": source_id},
                    )
                ).scalar_one()
                assert size == len(payload)

            async with session_factory() as session:
                claim = await reserve_file_upload(
                    session,
                    tenant_id=fixture.tenant_a,
                    source_id=uuid4(),
                    reserved_bytes=128,
                )
                assert claim.reserved_bytes == 128
        finally:
            storage.delete_object(key)
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
                            "DELETE FROM knowledge_upload_cleanups "
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
