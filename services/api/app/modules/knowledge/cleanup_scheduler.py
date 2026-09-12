"""Process-owned scheduler for durable knowledge-upload cleanup obligations."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from app.core.database import get_database_session_factory
from app.core.object_storage import ObjectStorage
from app.modules.knowledge.cleanup import CleanupReplayResult, reconcile_due_upload_cleanups
from app.modules.knowledge.storage import get_knowledge_object_storage

logger = logging.getLogger(__name__)

CLEANUP_SWEEP_INTERVAL_SECONDS = 30.0
CLEANUP_SWEEP_BATCH_SIZE = 100


async def run_knowledge_upload_cleanup_sweep(
    *,
    storage_factory: Callable[[], ObjectStorage] = get_knowledge_object_storage,
) -> tuple[CleanupReplayResult, ...]:
    """Run one bounded sweep with a fresh database session and storage boundary."""

    storage = storage_factory()
    session_factory = get_database_session_factory()
    async with session_factory() as session:
        results = await reconcile_due_upload_cleanups(
            session,
            storage=storage,
            limit=CLEANUP_SWEEP_BATCH_SIZE,
        )

    exhausted = sum(result.outcome == "exhausted" for result in results)
    if exhausted:
        logger.error(
            "knowledge_upload_cleanup_sweep_exhausted",
            extra={
                "cleanup_exhausted_count": exhausted,
                "cleanup_sweep_count": len(results),
            },
        )
    elif results:
        logger.info(
            "knowledge_upload_cleanup_sweep_completed",
            extra={"cleanup_sweep_count": len(results)},
        )
    return results


async def run_knowledge_upload_cleanup_scheduler(
    stop_event: asyncio.Event,
    *,
    interval_seconds: float = CLEANUP_SWEEP_INTERVAL_SECONDS,
) -> None:
    """Continuously reconcile due cleanup work until graceful process shutdown."""

    if interval_seconds <= 0:
        raise ValueError("Cleanup sweep interval must be positive.")

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            return
        except TimeoutError:
            pass

        try:
            await run_knowledge_upload_cleanup_sweep()
        except asyncio.CancelledError:
            raise
        except Exception:
            # Cleanup failures are retried by the durable state machine on the next
            # sweep. Do not log exception text because database/storage errors can
            # contain infrastructure details.
            logger.error("knowledge_upload_cleanup_sweep_failed")
