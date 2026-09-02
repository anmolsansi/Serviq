from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.modules.knowledge.service as knowledge_service
from app.core.config import load_settings
from app.core.database import (
    create_database_engine,
    create_database_session_factory,
    get_database_session,
)
from app.core.principal import require_tenant_id, require_workforce_user_id
from app.main import app
from tests.support.tenant_isolation import (
    TenantIsolationFixture,
    cleanup_tenant_isolation_fixture,
    seed_tenant_isolation_fixture,
)

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


def _install_overrides(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    tenant_id: UUID,
) -> None:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_database_session] = override_session
    app.dependency_overrides[require_workforce_user_id] = lambda: user_id
    app.dependency_overrides[require_tenant_id] = lambda: tenant_id


def _clear_overrides() -> None:
    for dependency in (
        get_database_session,
        require_workforce_user_id,
        require_tenant_id,
    ):
        app.dependency_overrides.pop(dependency, None)


async def _seed_source(
    session: AsyncSession,
    *,
    source_id: UUID,
    tenant_id: UUID,
    created_by: UUID,
    source_type: str = "url",
    status: str = "ready",
    sync_version: int = 0,
) -> None:
    source_uri = (
        "https://docs.example.com/help"
        if source_type in {"url", "sitemap"}
        else None
    )
    object_key = (
        "knowledge/test/source/raw/file.txt"
        if source_type not in {"url", "sitemap"}
        else None
    )
    await session.execute(
        text(
            """
            INSERT INTO knowledge_sources (
              id, tenant_id, source_type, name, source_uri, object_key, access_scope,
              status, sync_version, last_synced_at, last_error_code, created_by
            ) VALUES (
              :id, :tenant_id, :source_type, 'Sync Source', :source_uri, :object_key,
              'customer', :status, :sync_version, NULL, 'OLD_ERROR', :created_by
            )
            """
        ),
        {
            "id": source_id,
            "tenant_id": tenant_id,
            "source_type": source_type,
            "source_uri": source_uri,
            "object_key": object_key,
            "status": status,
            "sync_version": sync_version,
            "created_by": created_by,
        },
    )


async def _cleanup(
    session: AsyncSession,
    *,
    fixture: TenantIsolationFixture,
) -> None:
    await session.execute(
        text("DELETE FROM outbox_events WHERE tenant_id IN (:a, :b)"),
        {"a": fixture.tenant_a, "b": fixture.tenant_b},
    )
    await session.execute(
        text("DELETE FROM knowledge_sources WHERE tenant_id IN (:a, :b)"),
        {"a": fixture.tenant_a, "b": fixture.tenant_b},
    )


def test_source_sync_contract_and_tenant_isolation() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        fixture = TenantIsolationFixture.new()
        url_id = uuid4()
        file_id = uuid4()
        disabled_id = uuid4()
        foreign_id = uuid4()
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        seeded = False
        try:
            async with session_factory() as session, session.begin():
                await seed_tenant_isolation_fixture(session, fixture)
                await _seed_source(
                    session,
                    source_id=url_id,
                    tenant_id=fixture.tenant_a,
                    created_by=fixture.owner_a,
                )
                await _seed_source(
                    session,
                    source_id=file_id,
                    tenant_id=fixture.tenant_a,
                    created_by=fixture.owner_a,
                    source_type="text",
                )
                await _seed_source(
                    session,
                    source_id=disabled_id,
                    tenant_id=fixture.tenant_a,
                    created_by=fixture.owner_a,
                    status="disabled",
                )
                await _seed_source(
                    session,
                    source_id=foreign_id,
                    tenant_id=fixture.tenant_b,
                    created_by=fixture.owner_b,
                )
                seeded = True

            _install_overrides(
                session_factory,
                user_id=fixture.owner_a,
                tenant_id=fixture.tenant_a,
            )
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                synced = await client.post(
                    f"/api/v1/knowledge-sources/{url_id}/sync",
                    headers={"X-Request-ID": "req-sync-123"},
                )
                assert synced.status_code == 202
                synced_data = synced.json()["data"]
                assert UUID(synced_data["id"]) == url_id
                assert synced_data["status"] == "syncing"
                assert synced_data["syncVersion"] == 1
                assert synced_data["lastSyncedAt"] is None
                assert synced_data["lastErrorCode"] is None

                file_synced = await client.post(
                    f"/api/v1/knowledge-sources/{file_id}/sync"
                )
                assert file_synced.status_code == 202
                assert file_synced.json()["data"]["syncVersion"] == 1

                disabled = await client.post(
                    f"/api/v1/knowledge-sources/{disabled_id}/sync"
                )
                assert disabled.status_code == 409
                assert disabled.json() == {
                    "error": {
                        "code": "KNOWLEDGE_SOURCE_DISABLED",
                        "message": "Knowledge source is disabled.",
                    }
                }

                missing = await client.post(
                    f"/api/v1/knowledge-sources/{uuid4()}/sync"
                )
                assert missing.status_code == 404
                assert missing.json()["error"]["code"] == "KNOWLEDGE_SOURCE_NOT_FOUND"

                foreign = await client.post(
                    f"/api/v1/knowledge-sources/{foreign_id}/sync"
                )
                assert foreign.status_code == 404
                assert foreign.json() == missing.json()

            async with session_factory() as session:
                event = (
                    await session.execute(
                        text(
                            """
                            SELECT tenant_id, event_type, schema_version, aggregate_type,
                                   aggregate_id, payload, correlation_id, causation_id,
                                   status, attempts, next_attempt_at, published_at
                            FROM outbox_events
                            WHERE tenant_id=:tenant AND aggregate_id=:aggregate_id
                            """
                        ),
                        {"tenant": fixture.tenant_a, "aggregate_id": str(url_id)},
                    )
                ).one()
                assert event.tenant_id == fixture.tenant_a
                assert event.event_type == "serviq.knowledge.sync.v1"
                assert event.schema_version == 1
                assert event.aggregate_type == "knowledge_source"
                assert event.aggregate_id == str(url_id)
                assert event.payload == {
                    "tenantId": str(fixture.tenant_a),
                    "sourceId": str(url_id),
                    "syncVersion": 1,
                }
                assert event.correlation_id == "req-sync-123"
                assert event.causation_id is None
                assert event.status == "pending"
                assert event.attempts == 0
                assert event.next_attempt_at is not None
                assert event.published_at is None

                disabled_state = (
                    await session.execute(
                        text(
                            "SELECT status, sync_version, last_error_code "
                            "FROM knowledge_sources WHERE id=:id"
                        ),
                        {"id": disabled_id},
                    )
                ).one()
                assert disabled_state.status == "disabled"
                assert disabled_state.sync_version == 0
                assert disabled_state.last_error_code == "OLD_ERROR"

                disabled_events = int(
                    (
                        await session.execute(
                            text(
                                "SELECT count(*) FROM outbox_events "
                                "WHERE aggregate_id=:id"
                            ),
                            {"id": str(disabled_id)},
                        )
                    ).scalar_one()
                )
                assert disabled_events == 0

                generated_correlation = (
                    await session.execute(
                        text(
                            "SELECT correlation_id FROM outbox_events "
                            "WHERE tenant_id=:tenant AND aggregate_id=:aggregate_id"
                        ),
                        {"tenant": fixture.tenant_a, "aggregate_id": str(file_id)},
                    )
                ).scalar_one()
                assert str(UUID(generated_correlation)) == generated_correlation

            _install_overrides(
                session_factory,
                user_id=fixture.member_a,
                tenant_id=fixture.tenant_a,
            )
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                denied = await client.post(
                    f"/api/v1/knowledge-sources/{url_id}/sync"
                )
                assert denied.status_code == 403
                assert denied.json()["error"]["code"] == "FORBIDDEN"
        finally:
            _clear_overrides()
            if seeded:
                async with session_factory() as session, session.begin():
                    await _cleanup(session, fixture=fixture)
                    await cleanup_tenant_isolation_fixture(session, fixture)
            await engine.dispose()

    asyncio.run(scenario())


def test_concurrent_source_sync_allocates_distinct_versions() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        fixture = TenantIsolationFixture.new()
        source_id = uuid4()
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        seeded = False
        try:
            async with session_factory() as session, session.begin():
                await seed_tenant_isolation_fixture(session, fixture)
                await _seed_source(
                    session,
                    source_id=source_id,
                    tenant_id=fixture.tenant_a,
                    created_by=fixture.owner_a,
                    sync_version=7,
                )
                seeded = True

            _install_overrides(
                session_factory,
                user_id=fixture.owner_a,
                tenant_id=fixture.tenant_a,
            )
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                responses = await asyncio.gather(
                    client.post(f"/api/v1/knowledge-sources/{source_id}/sync"),
                    client.post(f"/api/v1/knowledge-sources/{source_id}/sync"),
                )
            assert [response.status_code for response in responses] == [202, 202]
            response_versions = sorted(
                response.json()["data"]["syncVersion"] for response in responses
            )
            assert response_versions == [8, 9]

            async with session_factory() as session:
                version = (
                    await session.execute(
                        text("SELECT sync_version FROM knowledge_sources WHERE id=:id"),
                        {"id": source_id},
                    )
                ).scalar_one()
                assert version == 9
                event_versions = (
                    await session.execute(
                        text(
                            "SELECT (payload->>'syncVersion')::int "
                            "FROM outbox_events WHERE aggregate_id=:id ORDER BY 1"
                        ),
                        {"id": str(source_id)},
                    )
                ).scalars().all()
                assert event_versions == [8, 9]
        finally:
            _clear_overrides()
            if seeded:
                async with session_factory() as session, session.begin():
                    await _cleanup(session, fixture=fixture)
                    await cleanup_tenant_isolation_fixture(session, fixture)
            await engine.dispose()

    asyncio.run(scenario())


def test_source_sync_rolls_back_when_outbox_staging_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        fixture = TenantIsolationFixture.new()
        source_id = uuid4()
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        seeded = False
        try:
            async with session_factory() as session, session.begin():
                await seed_tenant_isolation_fixture(session, fixture)
                await _seed_source(
                    session,
                    source_id=source_id,
                    tenant_id=fixture.tenant_a,
                    created_by=fixture.owner_a,
                    sync_version=3,
                )
                seeded = True

            def fail_outbox(*_args: object, **_kwargs: object) -> None:
                raise RuntimeError("forced outbox failure")

            monkeypatch.setattr(knowledge_service, "add_outbox_event", fail_outbox)
            _install_overrides(
                session_factory,
                user_id=fixture.owner_a,
                tenant_id=fixture.tenant_a,
            )
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                response = await client.post(
                    f"/api/v1/knowledge-sources/{source_id}/sync"
                )
            assert response.status_code == 500

            async with session_factory() as session:
                source = (
                    await session.execute(
                        text(
                            "SELECT status, sync_version, last_error_code "
                            "FROM knowledge_sources WHERE id=:id"
                        ),
                        {"id": source_id},
                    )
                ).one()
                assert source.status == "ready"
                assert source.sync_version == 3
                assert source.last_error_code == "OLD_ERROR"
                count = int(
                    (
                        await session.execute(
                            text(
                                "SELECT count(*) FROM outbox_events "
                                "WHERE aggregate_id=:id"
                            ),
                            {"id": str(source_id)},
                        )
                    ).scalar_one()
                )
                assert count == 0
        finally:
            _clear_overrides()
            if seeded:
                async with session_factory() as session, session.begin():
                    await _cleanup(session, fixture=fixture)
                    await cleanup_tenant_isolation_fixture(session, fixture)
            await engine.dispose()

    asyncio.run(scenario())
