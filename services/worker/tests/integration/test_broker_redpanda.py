from __future__ import annotations

import asyncio
import os
import time
from typing import Any
from uuid import uuid4

import confluent_kafka
import pytest

from app.core.broker import KafkaEventPublisher
from app.core.config import load_settings

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_KAFKA_INTEGRATION") != "1",
    reason="requires the real Kafka-compatible integration environment",
)


def test_real_redpanda_publish_preserves_topic_key_and_value() -> None:
    settings = load_settings()
    publisher = KafkaEventPublisher(settings)
    topic = f"serviq.integration.outbox.{uuid4().hex}"
    key = b"aggregate-123"
    value = b'{"eventType":"serviq.integration.outbox.v1"}'
    consumer: Any = confluent_kafka.Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": f"serviq-integration-{uuid4().hex}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    try:
        asyncio.run(publisher.publish(topic=topic, key=key, value=value))
        consumer.subscribe([topic])

        deadline = time.monotonic() + 10.0
        message: Any | None = None
        while time.monotonic() < deadline:
            candidate: Any = consumer.poll(1.0)
            if candidate is None:
                continue
            if candidate.error() is not None:
                continue
            message = candidate
            break

        assert message is not None
        assert message.topic() == topic
        assert message.key() == key
        assert message.value() == value
    finally:
        consumer.close()
        publisher.close()
