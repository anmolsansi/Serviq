# ADR-028 — Worker-owned knowledge upload cleanup scheduler

## Status

Accepted for V1.3.04D.

## Date

2026-09-12

## Context

ADR-018 and CCR-006 already define the durable `knowledge_upload_cleanups` state machine, tenant/key safety, three-attempt retry policy, conservative handling of ambiguous PUT outcomes, reservation release rules, and operator-visible exhaustion. The API implements request-time cleanup and the replay algorithm, but the audited production composition had no caller that continuously executed due cleanup work.

Serviq already has a durable worker process that owns outbox publication and knowledge-sync consumption. V1.3.04D must activate cleanup recovery without changing the public knowledge-source API, adding a new service, or making cleanup availability depend on FastAPI process uptime.

## Options considered

### Option A — FastAPI lifespan task

Start a periodic task from `services/api/app/main.py`.

Rejected. Cleanup would stop whenever the API process was unavailable, and durable reconciliation would become coupled to HTTP serving despite the repository already having a worker process for background work.

### Option B — Worker imports API cleanup modules

Reuse `services/api/app/modules/knowledge/cleanup.py` directly from the worker.

Rejected. API and worker are separate Python projects with independent frozen environments. A cross-service source import would create an undeclared deployment/runtime dependency and blur ownership.

### Option C — New Kafka cleanup topic

Publish each cleanup obligation to Kafka and consume it in the worker.

Rejected for V1.3.04D. The PostgreSQL cleanup table is already the durable source of truth and ADR-018 explicitly does not require a broker-specific cleanup architecture. A topic would add dual scheduling state and failure modes without solving a missing contract.

### Option D — Worker-owned table scheduler

The worker claims bounded due rows directly from the existing cleanup table, performs storage checks/deletes outside database transactions, records retry/exhaustion back into the same durable state, and repeats continuously.

Selected.

## Decision

`services/worker/app/jobs/knowledge_upload_cleanup.py` owns production cleanup scheduling.

The worker:

1. Selects at most a bounded batch of due `prepared`/`pending` rows using `FOR UPDATE SKIP LOCKED`.
2. Reconstructs the only valid generated raw key from tenant/source/object UUIDs and exhausts mismatches without touching storage.
3. In the short claim transaction, increments the attempt count, changes the row to `pending`, and advances `next_attempt_at` to the existing ADR-018 lease deadline.
4. Commits before any object-storage request.
5. For ambiguous outcomes, performs HEAD/exists first. Absence or HEAD failure consumes a bounded observation attempt rather than claiming cleanup success.
6. Performs idempotent DELETE only for a validated claim that is safe to clean.
7. In a new short transaction, records success and releases the matching tenant-scoped upload reservation, or records retry/exhaustion while preserving unresolved quota holds.
8. Repeats from the durable table after a bounded poll interval. Process restart needs no in-memory recovery state.

The worker object-storage boundary gains only `exists(key)` and `delete_object(key)`. No list/prefix operation is added.

## Concurrency and restart safety

Multiple worker processes may run the scheduler. `FOR UPDATE SKIP LOCKED` prevents one due row from being claimed by two schedulers in the same claim window. The claim advances `next_attempt_at` before storage I/O, so a crash after claim leaves a durable future deadline. A later worker can recover the row when that deadline becomes due.

A source-persistence transaction and cleanup claim serialize on the same cleanup row. If successful source persistence marks the row `referenced` first, it is no longer eligible. If cleanup claims an abandoned `prepared` row first, the status becomes `pending`, so a later source transaction cannot silently mark an object referenced after cleanup has started.

## Observability

Safe worker logs contain cleanup/tenant IDs, attempt count, bounded outcome, and aggregate batch counts. They never include object keys, bucket names, storage endpoints, credentials, filenames, upload bodies, or exception text from infrastructure failures.

`exhausted` remains durable operator state. The scheduler does not auto-requeue or purge exhausted rows.

## Compatibility

This decision changes no public route, request/response shape, database schema, retry count, object-key layout, RBAC rule, file limit, or cleanup retention policy. API request-time cleanup remains in place as a fast-path optimization.

## Rollback

The scheduler can be removed from worker composition without a database migration. Doing so leaves unresolved cleanup rows durable but stops automatic recovery, recreating V1.3.04D. Rolling back must therefore be paired with operator awareness of pending/prepared rows. The additive worker storage methods are safe to leave in place.