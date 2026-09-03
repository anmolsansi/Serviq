# ADR-022: Transactional outbox publication to Kafka-compatible brokers

**Status:** Accepted
**Date:** 2026-09-03
**Linear:** OPE-314
**GitHub:** #199

## Context

Serviq already persists durable domain events in PostgreSQL `outbox_events`, but no runtime component publishes those rows to the Kafka-compatible broker. That leaves accepted commands such as `serviq.knowledge.sync.v1` durable but undeliverable to background workers.

The existing outbox schema has only `pending|published|failed`, `attempts`, `next_attempt_at`, and `published_at`. This ticket must therefore implement publication without inventing a lease column, processing state, or second queue table.

## Decision

### Delivery model

Publication is **at least once**.

A publisher selects due `pending` rows using PostgreSQL `FOR UPDATE SKIP LOCKED`. The row lock is held only through serialization, broker delivery acknowledgement, and the final outbox status update. A successful Kafka acknowledgement is required before `status` changes to `published` and `published_at` is set.

If the process dies after Kafka acknowledges the record but before PostgreSQL commits the published state, the row can be published again. This duplicate window is deliberate and is why every durable consumer must enforce its own frozen idempotency contract.

No claim/lease column or schema migration is introduced by this ticket.

### Topic and partition key

- Kafka topic is exactly `outbox_events.event_type`.
- Kafka key is UTF-8 `aggregate_id`.
- The key preserves per-aggregate partition ordering when a topic has multiple partitions.
- Topic names are therefore owned by versioned event names such as `serviq.knowledge.sync.v1`.

### Wire envelope

The Kafka value is UTF-8 JSON with exactly these camelCase fields:

```json
{
  "id": "<outbox UUID>",
  "eventType": "<event type>",
  "schemaVersion": 1,
  "tenantId": "<tenant UUID or null>",
  "aggregateType": "<aggregate type>",
  "aggregateId": "<aggregate id>",
  "payload": {},
  "correlationId": "<bounded correlation id>",
  "causationId": "<outbox/event id or null>"
}
```

The publisher does not add timestamps, retry metadata, source URLs, object keys, raw content, credentials, or user PII to the generic envelope.

Serialization is deterministic JSON with UTF-8 output and compact separators. A row that cannot satisfy this contract is terminally marked `failed`; its raw payload is not logged.

### Producer contract

The production adapter uses the existing `KAFKA_BOOTSTRAP_SERVERS` setting and a Kafka-compatible producer configured with:

- `acks=all`;
- idempotent producer mode enabled;
- bounded delivery timeout;
- no application-level producer retries beyond the library's idempotent delivery behavior.

The adapter exposes one small `publish(topic, key, value)` boundary. Feature jobs do not depend on the Kafka SDK directly.

### Publisher retry contract

Broker/transport delivery failure leaves the event `pending`, increments `attempts` once, and sets `next_attempt_at` using:

```text
min(5 * 2^(attempts_after_failure - 1), 300) seconds
```

The resulting sequence is 5s, 10s, 20s, 40s, 80s, 160s, then 300s for every later failure.

Publisher retries are continuous because the durable event remains pending. This is distinct from bounded consumer retry/DLQ policies, which belong to each consumer contract.

### Concurrency

- A publisher invocation processes at most 100 rows.
- Default batch size is 20.
- `FOR UPDATE SKIP LOCKED` prevents two publisher transactions from working the same row concurrently.
- Rows are ordered by `next_attempt_at`, then `id` for deterministic claiming.
- Publication inside one claimed batch is sequential so one database session never has concurrent operations.

### Database boundary

The worker adopts the same SQLAlchemy 2 + Psycopg 3 async engine/session pattern already frozen for the API. `DATABASE_URL` remains the external variable name and normal `postgresql://` URLs are adapted internally to `postgresql+psycopg://`.

Repositories/jobs receive an `AsyncSession`; they do not create engines themselves.

### Process boundary

The worker process owns a continuous publisher loop. An empty poll sleeps for a bounded one second. Successful work immediately polls again. Shutdown cancels the loop, closes the Kafka producer, and disposes the database engine.

## Alternatives rejected

### Publish directly from API requests

Rejected. It would reintroduce the dual-write problem the transactional outbox was created to avoid.

### Add a `processing` state and lease columns

Rejected for this ticket. It would require a new migration and recovery semantics when the existing row-lock approach is sufficient for the current V1 throughput.

### Mark the row published before Kafka acknowledgement

Rejected. A process or broker failure could permanently lose an accepted durable event.

### Exactly-once distributed transaction

Rejected. Coordinating PostgreSQL and Kafka transactions would add substantial complexity while downstream idempotency is already required by the architecture.

## Failure and observability rules

Logs/metrics may contain only bounded event ID, event type, aggregate type/ID, attempt count, outcome code, and timing. They must not include raw `payload`, knowledge content, credentials, or broker error bodies.

Stable outcome classes are:

- `OUTBOX_PUBLISHED`;
- `OUTBOX_BROKER_UNAVAILABLE`;
- `OUTBOX_SERIALIZATION_FAILED`.

## Security consequences

The publisher never interprets event payloads and cannot widen tenant authorization. It transports only the already-persisted event contract. Broker bootstrap configuration comes only from validated server environment settings.

## Deployment and rollback

1. Deploy code and dependency lock with the publisher disabled from traffic until database migrations through `20260902_0012` are present.
2. Start the worker publisher against the existing outbox table.
3. Observe pending depth, publish outcomes, and retry attempts.

Rollback stops the worker publisher. Pending rows remain durable in PostgreSQL and can be published after redeployment. No schema rollback is required.

## Verification

Required coverage includes exact envelope serialization, topic/key mapping, successful acknowledgement, broker failure/backoff, terminal serialization failure, row locking/skip-locked behavior against real PostgreSQL, empty polling, and safe shutdown.
