from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


def test_readiness_endpoint_reaches_real_postgres() -> None:
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
