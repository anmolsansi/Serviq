from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import text

from app.core.config import load_settings
from app.core.database import create_database_engine, create_database_session_factory

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


def test_owner_and_admin_receive_knowledge_source_management_capability() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        try:
            async with session_factory() as session:
                rows = await session.execute(
                    text(
                        """
                        SELECT r.key
                        FROM roles r
                        JOIN role_permissions rp ON rp.role_id = r.id
                        WHERE r.tenant_id IS NULL
                          AND r.is_system = true
                          AND r.key IN ('owner', 'admin')
                          AND rp.permission_key = 'knowledge.sources.manage'
                        """
                    )
                )
                assert set(rows.scalars().all()) == {"owner", "admin"}
        finally:
            await engine.dispose()

    asyncio.run(scenario())
