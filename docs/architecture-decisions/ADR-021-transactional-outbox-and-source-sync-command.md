# ADR-021: Transactional outbox persistence and knowledge source sync command

**Status:** Accepted
**Date:** 2026-09-02
**Linear:** OPE-312
**GitHub:** #194

## Context

Serviq's architecture already freezes a PostgreSQL `outbox_events` contract and requires multi-table state transitions to publish through a transactional outbox. The knowledge-source roadmap requires `POST /api/v1/knowledge-sources/{sourceId}/sync` to increment the source sync version, transition the source to `syncing`, and record `serviq.knowledge.sync.v1` atomically.

The current code implements knowledge-source registration and upload durability but does not yet implement the generic outbox table or this sync command.

## Decision

V1.3.06 implements the existing architecture contract rather than inventing a knowledge-specific queue.

### API

`POST /api/v1/knowledge-sources/{sourceId}/sync`

- uses the existing trusted workforce user and server-resolved tenant dependencies;
- requires the existing `knowledge.sources.manage` capability;
- accepts no request body;
- returns `202 Accepted` with `SuccessEnvelope[KnowledgeSourceView]` after the command commits;
- returns `409 KNOWLEDGE_SOURCE_DISABLED` for a disabled source;
- returns `404 KNOWLEDGE_SOURCE_NOT_FOUND` for both an absent source and a source owned by another tenant;
- preserves the existing `403 FORBIDDEN` response for permission failure.

### Concurrency

The command selects the tenant-scoped source row with `SELECT ... FOR UPDATE` inside the same PostgreSQL transaction that mutates the source and inserts the outbox event.

Every accepted request therefore receives one new monotonic `sync_version`. Concurrent accepted requests serialize and produce distinct versions such as `N+1` and `N+2`.

The HTTP command is intentionally not request-idempotent. Durable downstream work is identified by the outbox event ID and by `tenantId:sourceId:syncVersion`.

### Source mutation

An accepted command:

1. locks the tenant-scoped source row;
2. increments `sync_version` exactly once;
3. sets `status` to `syncing`;
4. clears `last_error_code`;
5. preserves `last_synced_at`;
6. updates `updated_at`;
7. inserts one pending outbox event;
8. flushes and commits once.

If event persistence fails, the source mutation rolls back with it.

### Outbox schema

The migration implements the existing `docs/ARCHITECTURE.md` contract exactly:

```text
outbox_events
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NULL FK tenants RESTRICT
  event_type text NOT NULL
  schema_version integer NOT NULL DEFAULT 1
  aggregate_type text NOT NULL
  aggregate_id text NOT NULL
  payload jsonb NOT NULL
  correlation_id text NOT NULL
  causation_id text NULL
  status text NOT NULL CHECK pending|published|failed
  attempts integer NOT NULL DEFAULT 0
  next_attempt_at timestamptz NOT NULL DEFAULT now()
  published_at timestamptz NULL
Indexes: (status, next_attempt_at), (tenant_id, aggregate_type, aggregate_id)
```

The generic table keeps `tenant_id` nullable because platform events may not belong to a tenant. Knowledge-sync events always supply a tenant ID.

### Knowledge sync event

```text
event_type: serviq.knowledge.sync.v1
schema_version: 1
aggregate_type: knowledge_source
aggregate_id: <source UUID string>
payload:
  tenantId: <tenant UUID string>
  sourceId: <source UUID string>
  syncVersion: <new integer version>
causation_id: null
status: pending
attempts: 0
next_attempt_at: database default now()
```

The event contains no source URI, object-storage key, raw knowledge content, credentials, prompts, or user PII.

### Correlation ID

A trimmed inbound `X-Request-ID` is preserved only when it contains 1 to 128 printable ASCII characters with no spaces or control characters. Otherwise Serviq generates a UUID string. This keeps the durable event correlation value bounded and log-safe.

## Alternatives rejected

### FastAPI background task

Rejected because acknowledgement could occur before durable work exists and process failure could lose the sync request.

### Knowledge-specific queue table

Rejected because it duplicates the already-frozen generic outbox architecture and creates a second delivery abstraction.

### Optimistic update without row locking

Rejected because simultaneous requests could allocate the same source version or lose an increment.

## Scope boundary

This ADR does not implement the outbox publisher, Kafka/Redpanda integration, knowledge-sync consumer, crawler, parser, chunker, embedder, indexer, retry execution, or completion/failure transitions.

## Rollback

Application rollback removes the sync endpoint and producer code. Database downgrade drops `outbox_events` only after operators confirm that no pending event requires later delivery. Because this ticket has no publisher yet, any environment that has accepted sync commands must treat pending outbox rows as durable obligations before downgrade.
