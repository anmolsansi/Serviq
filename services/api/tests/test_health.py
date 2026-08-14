from __future__ import annotations

import asyncio
import logging
import time

from fastapi.testclient import TestClient

from app.main import app
from app.modules.health import router as health_router
from app.modules.health.service import DATABASE_READINESS_TIMEOUT_SECONDS, database_is_ready

client = TestClient(app)


def test_healthy_database_returns_200_ready(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def ready() -> bool:
        return True

    monkeypatch.setattr(health_router, "database_is_ready", ready)

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_database_exception_returns_503_not_ready(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def not_ready() -> bool:
        return False

    monkeypatch.setattr(health_router, "database_is_ready", not_ready)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "dependency": "database"}


def test_database_timeout_returns_503_within_budget() -> None:
    async def slow_ping() -> None:
        await asyncio.sleep(1)

    started = time.monotonic()
    result = asyncio.run(database_is_ready(slow_ping, timeout_seconds=0.01))
    elapsed = time.monotonic() - started

    assert DATABASE_READINESS_TIMEOUT_SECONDS == 2.0
    assert result is False
    assert elapsed < 0.2


def test_readiness_does_not_leak_database_details(caplog) -> None:  # type: ignore[no-untyped-def]
    sentinel_url = "postgresql://user:super-secret@private-db.example:5432/serviq"

    async def broken_ping() -> None:
        raise RuntimeError(f"connection refused for {sentinel_url}; SELECT 1")

    with caplog.at_level(logging.WARNING, logger="serviq.health"):
        result = asyncio.run(database_is_ready(broken_ping))

    assert result is False
    captured = caplog.text
    assert "database_readiness_failed" in captured
    assert "super-secret" not in captured
    assert "private-db.example" not in captured
    assert "postgresql://" not in captured
    assert "SELECT 1" not in captured


def test_liveness_does_not_depend_on_database(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def must_not_be_called() -> bool:
        raise AssertionError("database readiness was called by liveness")

    monkeypatch.setattr(health_router, "database_is_ready", must_not_be_called)

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}
