from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.core.config import load_settings
from app.core.database import create_database_engine, create_database_session_factory

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)

EXPECTED_TABLES = {
    "alembic_version",
    "tenants",
    "users",
    "memberships",
    "roles",
    "role_permissions",
    "membership_roles",
    "organization_invitations",
    "organization_invitation_roles",
    "provider_connections",
    "model_configurations",
    "model_configuration_references",
    "knowledge_sources",
    "knowledge_documents",
    "knowledge_chunks",
    "knowledge_upload_cleanups",
}


def _table_names(connection: Connection) -> list[str]:
    return inspect(connection).get_table_names(schema="public")


def test_async_session_connects_to_real_postgres_with_expected_schema() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        try:
            async with session_factory() as session:
                result = await session.execute(text("SELECT 1"))
                assert result.scalar_one() == 1

            async with engine.connect() as connection:
                tables = await connection.run_sync(_table_names)

            assert set(tables) == EXPECTED_TABLES
        finally:
            await engine.dispose()

    asyncio.run(scenario())
