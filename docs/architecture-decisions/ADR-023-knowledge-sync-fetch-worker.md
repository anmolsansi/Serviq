# ADR-023 — Knowledge sync fetch worker

- Status: Accepted
- Date: 2026-09-03
- Linear: OPE-313
- GitHub: #198

## Context

ADR-020 established the fail-closed public HTTPS fetch boundary. ADR-021 made knowledge-source sync commands and their `serviq.knowledge.sync.v1` outbox event atomic. ADR-022 added the generic at-least-once PostgreSQL outbox publisher to the Kafka-compatible broker. V1.3.07 closes the next durable ingestion gap: consume one source/version, acquire raw bytes, create the versioned `knowledge_document`, and stage the parser obligation without implementing parsing itself.

## Decision

### Consumer

The worker consumes `serviq.knowledge.sync.v1` with group `serviq-worker-knowledge-sync-v1`. Kafka delivery is at-least-once and offsets are committed manually only after success/no-op or after a retry/DLQ record has been acknowledged by the broker.

The ADR-022 envelope and exact ADR-021 payload must validate. The Kafka key must equal the source aggregate ID. Invalid records go to `serviq.knowledge.sync.v1.dlq` with safe code `KNOWLEDGE_SYNC_EVENT_INVALID` and no source mutation when a trustworthy source identity cannot be established.

### Retry and DLQ

Retry timing is exactly 30 seconds, 5 minutes, then 30 minutes. Retry records use `serviq.knowledge.sync.v1.retry` with ASCII headers `serviq-attempt` and `serviq-not-before-ms`. Exhausted retryable failures and terminal failures go to `serviq.knowledge.sync.v1.dlq` with ASCII `serviq-error-code`. A retry/DLQ publish failure leaves the consumed record uncommitted.

Not-yet-due retry records pause only their Kafka partition. Due paused partitions are resumed while the consumer continues polling other partitions.

### Source and version semantics

All source reads and writes are tenant scoped.

- missing or cross-tenant source: terminal `KNOWLEDGE_SYNC_SOURCE_NOT_FOUND`;
- disabled source: terminal `KNOWLEDGE_SOURCE_DISABLED`;
- event version below current source version: acknowledge as stale no-op;
- equal version: process idempotently;
- event version above current source version: terminal `KNOWLEDGE_SYNC_VERSION_AHEAD`.

Network and object-storage work occurs without a database row lock. Before durable document/event persistence, the worker locks the source row and rechecks tenant, disabled state, and version.

### Raw content

For `url`, the exact registered hostname is the ADR-020 allowlist. Cross-host redirects therefore fail closed. The final safe URL becomes `canonical_uri`. Exact fetched bytes are stored at:

`tenants/{tenantId}/knowledge/{sourceId}/sync/{syncVersion}/raw`

For `pdf`, `markdown`, and `text`, the worker reads the existing `knowledge_sources.object_key` in place. The key must start with `tenants/{tenantId}/knowledge/{sourceId}/`. File documents use `canonical_uri = NULL`.

Sitemap traversal remains out of scope. A sitemap command fails terminally with `KNOWLEDGE_SYNC_SOURCE_TYPE_UNSUPPORTED`.

### Document contract

- `document_version = syncVersion`;
- `content_hash = sha256(exact raw bytes).hexdigest()` lowercase hex;
- `title = knowledge_sources.name`;
- new document status is `active`;
- `fetched_at = now()`.

A same-version replay with a different hash fails terminally as `KNOWLEDGE_SYNC_REPLAY_CONTENT_MISMATCH`; existing data is never overwritten. The source row lock serializes competing same-source persistence so duplicate delivery cannot create duplicate logical documents or parse obligations.

Older documents are not deprecated here because safe retrieval/index cutover is owned by later ingestion completion.

### Parse handoff

The worker inserts `serviq.knowledge.parse.v1` into the existing transactional outbox in the same transaction as document persistence and source success state.

Envelope metadata:

- schema version `1`;
- aggregate type `knowledge_document`;
- aggregate ID = document UUID;
- correlation ID inherited from the sync event;
- causation ID = sync event ID.

Payload is exactly:

```json
{
  "tenantId": "<uuid>",
  "sourceId": "<uuid>",
  "documentId": "<uuid>",
  "documentVersion": 1,
  "sourceType": "url|pdf|markdown|text",
  "rawObjectKey": "<tenant-scoped object key>",
  "canonicalUri": "<final URL or null>",
  "contentHash": "<lowercase sha256 hex>"
}
```

Raw content, credentials, remote error bodies, prompts, and user PII are not event fields.

### Source lifecycle

A successful fetch/document/parse-handoff transaction keeps source status `syncing`, sets `last_synced_at`, clears `last_error_code`, and updates `updated_at`. `ready` belongs to the completed downstream parse/chunk/embed/index pipeline.

Terminal or exhausted retryable failures set `status=failed` and a stable safe `last_error_code` only if the same tenant/source still has the failed `sync_version` and is not disabled. Older failures never overwrite newer sync state.

Database unavailability is retryable as `KNOWLEDGE_SYNC_DATABASE_UNAVAILABLE`. File object absence/storage failure is retryable as `KNOWLEDGE_SOURCE_OBJECT_UNAVAILABLE`. ADR-020 fetch failures preserve the helper's retryable classification.

## Consequences

The worker gains `botocore` behind its own small object-storage adapter, reusing the dependency family already approved by ADR-016. No public API or database migration changes. Parsing, chunking, embedding, indexing, sitemap traversal, and readiness transitions remain separate tickets.

## Validation

The implementation requires worker unit tests, real PostgreSQL persistence/idempotency tests, a real S3-compatible storage round trip, and an end-to-end Redpanda + S3-compatible storage + PostgreSQL test that proves the durable parse outbox handoff.

## Rollback

Stop the knowledge-sync consumer first. Kafka records remain durable. Revert worker code/dependencies/contracts; there is no schema downgrade. Deterministic raw objects, documents, and already-staged parse outbox events may remain as durable artifacts and must not be destructively deleted as part of rollback.
