from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.core.database import dispose_database_engine
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


def test_readiness_endpoint_reaches_real_postgres() -> None:
    client = TestClient(app)

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}

    # The application engine is cached process-wide. Dispose it after this
    # integration test so the event loop created by TestClient is not reused.
    import asyncio

    asyncio.run(dispose_database_engine())
