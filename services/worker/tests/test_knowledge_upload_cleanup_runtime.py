from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.jobs.knowledge_upload_cleanup as cleanup_job
import app.main as worker_main
from app.core.object_storage import RawObjectStorage


class _FakeSessionContext:
    async def __aenter__(self) -> AsyncSession:
        return cast(AsyncSession, object())

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None


class _FakeSessionFactory:
    def __call__(self) -> _FakeSessionContext:
        return _FakeSessionContext()


def _session_factory() -> async_sessionmaker[AsyncSession]:
    return cast(async_sessionmaker[AsyncSession], _FakeSessionFactory())


def test_cleanup_loop_reuses_fresh_session_boundary_and_propagates_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def fake_reconcile(
        session: AsyncSession,
        storage: RawObjectStorage,
        *,
        now: object = None,
        batch_size: int = cleanup_job.DEFAULT_BATCH_SIZE,
    ) -> cleanup_job.CleanupBatchResult:
        nonlocal calls
        del session, storage, now, batch_size
        calls += 1
        return cleanup_job.CleanupBatchResult(0, 0, 0, 0)

    async def stop_after_first_cycle(delay: float) -> None:
        del delay
        raise asyncio.CancelledError

    monkeypatch.setattr(cleanup_job, "reconcile_due_upload_cleanups", fake_reconcile)
    monkeypatch.setattr(cleanup_job.asyncio, "sleep", stop_after_first_cycle)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            cleanup_job.run_knowledge_upload_cleanup_loop(
                _session_factory(),
                cast(RawObjectStorage, object()),
                poll_seconds=0.001,
            )
        )

    assert calls == 1


def test_cleanup_loop_does_not_log_infrastructure_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "postgresql://user:private-password@internal.example/serviq"

    async def failing_reconcile(
        session: AsyncSession,
        storage: RawObjectStorage,
        *,
        now: object = None,
        batch_size: int = cleanup_job.DEFAULT_BATCH_SIZE,
    ) -> cleanup_job.CleanupBatchResult:
        del session, storage, now, batch_size
        raise RuntimeError(secret)

    async def stop_after_failure(delay: float) -> None:
        del delay
        raise asyncio.CancelledError

    monkeypatch.setattr(cleanup_job, "reconcile_due_upload_cleanups", failing_reconcile)
    monkeypatch.setattr(cleanup_job.asyncio, "sleep", stop_after_failure)

    with caplog.at_level(logging.ERROR), pytest.raises(asyncio.CancelledError):
        asyncio.run(
            cleanup_job.run_knowledge_upload_cleanup_loop(
                _session_factory(),
                cast(RawObjectStorage, object()),
                poll_seconds=0.001,
            )
        )

    assert "knowledge_upload_cleanup_loop_failed" in caplog.text
    assert secret not in caplog.text
    assert "private-password" not in caplog.text


def test_worker_composes_cleanup_with_existing_durable_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[str] = []
    closed: list[str] = []

    class FakeEngine:
        async def dispose(self) -> None:
            closed.append("engine")

    class FakePublisher:
        def close(self) -> None:
            closed.append("publisher")

    class FakeConsumer:
        async def run_forever(self) -> None:
            started.append("sync")

        def close(self) -> None:
            closed.append("consumer")

    async def fake_outbox(session_factory: Any, publisher: Any) -> None:
        del session_factory, publisher
        started.append("outbox")

    async def fake_cleanup(session_factory: Any, storage: Any) -> None:
        del session_factory, storage
        started.append("cleanup")

    settings = object()
    engine = FakeEngine()
    session_factory = object()
    publisher = FakePublisher()
    storage = object()
    consumer = FakeConsumer()

    monkeypatch.setattr(worker_main, "load_settings", lambda: settings)
    monkeypatch.setattr(worker_main, "create_database_engine", lambda value: engine)
    monkeypatch.setattr(
        worker_main,
        "create_database_session_factory",
        lambda value: session_factory,
    )
    monkeypatch.setattr(worker_main, "KafkaEventPublisher", lambda value: publisher)
    monkeypatch.setattr(worker_main, "build_object_storage", lambda value: storage)
    monkeypatch.setattr(
        worker_main,
        "KnowledgeSyncConsumer",
        lambda *args: consumer,
    )
    monkeypatch.setattr(worker_main, "_run_outbox_publisher", fake_outbox)
    monkeypatch.setattr(
        worker_main,
        "run_knowledge_upload_cleanup_loop",
        fake_cleanup,
    )

    asyncio.run(worker_main.run_worker())

    assert sorted(started) == ["cleanup", "outbox", "sync"]
    assert closed == ["consumer", "publisher", "engine"]
