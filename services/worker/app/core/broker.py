"""Small Kafka-compatible broker boundary owned by the worker."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Protocol

import confluent_kafka

from app.core.config import PlatformSettings

_DELIVERY_TIMEOUT_SECONDS = 10.0


class BrokerUnavailableError(RuntimeError):
    """Safe delivery failure that never exposes broker details."""

    def __init__(self) -> None:
        super().__init__("Kafka-compatible broker delivery failed.")


class EventPublisher(Protocol):
    """Minimal publishing boundary used by durable worker jobs."""

    async def publish(self, *, topic: str, key: bytes, value: bytes) -> None: ...

    def close(self) -> None: ...


class KafkaEventPublisher:
    """Confluent Kafka adapter with idempotent producer semantics."""

    def __init__(self, settings: PlatformSettings) -> None:
        self._producer: Any = confluent_kafka.Producer(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "acks": "all",
                "enable.idempotence": True,
                "delivery.timeout.ms": int(_DELIVERY_TIMEOUT_SECONDS * 1000),
                "client.id": "serviq-worker-outbox-publisher",
            }
        )

    async def publish(self, *, topic: str, key: bytes, value: bytes) -> None:
        await asyncio.to_thread(self._publish_sync, topic, key, value)

    def _publish_sync(self, topic: str, key: bytes, value: bytes) -> None:
        delivered = False
        delivery_failed = False

        def on_delivery(error: Any, _message: Any) -> None:
            nonlocal delivered, delivery_failed
            delivered = True
            delivery_failed = error is not None

        try:
            callback: Callable[[Any, Any], None] = on_delivery
            self._producer.produce(
                topic=topic,
                key=key,
                value=value,
                on_delivery=callback,
            )
            remaining = int(self._producer.flush(_DELIVERY_TIMEOUT_SECONDS))
        except (BufferError, RuntimeError):
            raise BrokerUnavailableError from None

        if remaining != 0 or not delivered or delivery_failed:
            raise BrokerUnavailableError

    def close(self) -> None:
        """Best-effort bounded flush during controlled worker shutdown."""

        try:
            self._producer.flush(1.0)
        except Exception:
            # Shutdown must never expose raw broker exceptions or mask process exit.
            return
