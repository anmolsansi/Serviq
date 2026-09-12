from __future__ import annotations

import asyncio
import logging

import pytest

import app.modules.knowledge.cleanup_scheduler as cleanup_scheduler


def test_cleanup_scheduler_runs_sweep_and_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop_event = asyncio.Event()
    calls = 0

    async def fake_sweep() -> tuple[object, ...]:
        nonlocal calls
        calls += 1
        stop_event.set()
        return ()

    monkeypatch.setattr(
        cleanup_scheduler,
        "run_knowledge_upload_cleanup_sweep",
        fake_sweep,
    )

    asyncio.run(
        cleanup_scheduler.run_knowledge_upload_cleanup_scheduler(
            stop_event,
            interval_seconds=0.001,
        )
    )

    assert calls == 1


def test_cleanup_scheduler_recovers_after_sweep_failure_without_logging_secret(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stop_event = asyncio.Event()
    calls = 0
    secret = "postgresql://user:password@example.invalid/serviq"

    async def flaky_sweep() -> tuple[object, ...]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError(secret)
        stop_event.set()
        return ()

    monkeypatch.setattr(
        cleanup_scheduler,
        "run_knowledge_upload_cleanup_sweep",
        flaky_sweep,
    )

    with caplog.at_level(logging.ERROR):
        asyncio.run(
            cleanup_scheduler.run_knowledge_upload_cleanup_scheduler(
                stop_event,
                interval_seconds=0.001,
            )
        )

    assert calls == 2
    assert "knowledge_upload_cleanup_sweep_failed" in caplog.text
    assert secret not in caplog.text


def test_cleanup_scheduler_rejects_non_positive_interval() -> None:
    stop_event = asyncio.Event()

    with pytest.raises(ValueError, match="interval must be positive"):
        asyncio.run(
            cleanup_scheduler.run_knowledge_upload_cleanup_scheduler(
                stop_event,
                interval_seconds=0,
            )
        )
