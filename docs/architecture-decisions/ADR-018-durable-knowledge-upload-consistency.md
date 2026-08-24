# ADR-018 — Durable knowledge upload consistency

## Status

Accepted for V1.3.04A / OPE-308.

## Date

2026-08-24

## Context

OPE-303 stores a generated raw knowledge object before committing its `knowledge_sources` row. If that database write fails, the request tries to delete the object, but object-storage deletion can fail independently. The current service suppresses that second failure, so a raw object can exist without a durable source row or a durable cleanup obligation.

V1.3.04A strengthens the invariant to:

> Before Serviq can attempt a raw-object PUT, PostgreSQL must already contain a durable, tenant-owned record that lets a trusted recovery process find the generated object key without relying on request logs or object-store listing.

The public knowledge-source API must remain compatible. A failed upload must not create a tenant-visible `knowledge_sources` row merely to solve an internal cleanup problem.

The repository also does not yet have the general durable outbox/worker implementation planned for V1.3.06, so this ticket must not invent a broker-specific cleanup architecture.

## Options considered

### Option A — Keep store-first plus best-effort delete

This is the OPE-303 behavior. It is simple on the success path, but simultaneous database and delete failures can leave an object with no durable owner or cleanup record.

Rejected because it is the defect this ticket exists to remove.

### Option B — Create the user-visible knowledge source before object storage

The source row could be written first in a failed/incomplete state, then promoted to `pending` after the object PUT succeeds. That makes every possible object discoverable through a source row without adding a table.

Rejected because it changes the observable data contract: failed file uploads that previously created no source would become visible through `GET /api/v1/knowledge-sources`. It also overloads the knowledge-source lifecycle with an operator-only cross-store cleanup concern and still does not provide durable retry count, retry schedule, or exhausted/DLQ state.

### Option C — Reconcile by listing raw objects and comparing them with PostgreSQL

A periodic sweep could enumerate tenant raw-object prefixes and delete objects with no source row.

Rejected because the current `ObjectStorage` contract intentionally has no list operation. Adding listing, pagination, stale/in-flight grace rules, and prefix-scan cost would widen the storage contract and create a larger race surface than necessary.

### Option D — Persist a cleanup intent before object storage

Create a small PostgreSQL cleanup-intent row before the PUT. On successful source persistence, atomically mark the cleanup intent `referenced` in the same transaction as the new source. On failure, the intent remains recoverable and can drive bounded idempotent deletion.

Selected.

## Decision

Serviq adds the tenant-owned `knowledge_upload_cleanups` table frozen by CCR-006.

A file upload uses this ordering:

1. Resolve the trusted tenant/user and require `knowledge.sources.manage`.
2. Validate the complete file using the existing OPE-303 limits and content rules.
3. Generate the server-owned `source_id`, `object_id`, and existing OPE-301 raw object key.
4. Commit one `knowledge_upload_cleanups` row **before object storage I/O** with status `prepared`, attempt count `0`, and a stale-preparation reconciliation time 15 minutes in the future.
5. Only after that commit may Serviq call `ObjectStorage.put_object`.
6. After a successful PUT, open one PostgreSQL transaction that creates the normal file-backed `knowledge_sources` row with status `pending` and changes the cleanup row from `prepared` to `referenced`.
7. Return the existing successful upload response only after that transaction commits.

The raw object is therefore never created before PostgreSQL knows its exact generated key and tenant/source identity.

## Cleanup state machine

`knowledge_upload_cleanups.status` is one of:

- `prepared` — committed before PUT. A row still unresolved after 15 minutes is treated as abandoned/ambiguous and is eligible for reconciliation.
- `pending` — the request concluded that the object must be cleaned up. `next_attempt_at` controls the bounded retry schedule.
- `referenced` — the source row committed successfully and now durably owns the raw object. Cleanup must not delete it.
- `succeeded` — deletion succeeded or the object was already absent. Replay is a no-op.
- `exhausted` — the three reconciliation attempts were consumed without confirmed deletion. The row is operator-visible and must not be silently dropped.

`referenced`, `succeeded`, and `exhausted` are terminal for this ticket. A later operator workflow may explicitly requeue an exhausted item under a separately reviewed contract.

## Failure handling

### Cleanup-intent insert fails

No object PUT is attempted. The request fails and this attempt cannot create an untracked object.

### PUT fails or its outcome is ambiguous

The public request keeps the existing storage-failure behavior and creates no `knowledge_sources` row.

Serviq best-effort transitions the durable intent from `prepared` to `pending` and schedules the first reconciliation retry for 30 seconds later. It also performs one immediate idempotent delete outside a database transaction as a fast recovery optimization.

If the state transition fails because PostgreSQL is unavailable, the already committed `prepared` row remains discoverable and becomes eligible through its 15-minute stale-preparation deadline.

If the immediate delete succeeds, Serviq best-effort marks the intent `succeeded`. If that final database update fails, later reconciliation can safely delete the already-absent object again.

### PUT succeeds but source persistence fails

The `knowledge_sources` insert and cleanup `referenced` transition are in one transaction. If that transaction fails, neither change commits. The original cleanup intent remains durable.

Serviq then follows the same pending-arm plus immediate-delete path. A simultaneous database failure and delete failure therefore leaves a durable `prepared` or `pending` cleanup obligation and never reports success.

### Process crash

A crash can occur after the intent commit and before any later transition. The `prepared` row is intentionally durable. After its 15-minute grace period, reconciliation treats it as abandoned/ambiguous and attempts idempotent deletion unless a successful source transaction already changed it to `referenced`.

## Bounded reconciliation and retry schedule

The request-time immediate delete is an optimization and does not consume the background retry budget.

Reconciliation has exactly three deletion attempts:

1. first retry: 30 seconds after cleanup is armed;
2. second retry: 5 minutes after the first failed reconciliation attempt;
3. third retry: 30 minutes after the second failed reconciliation attempt;
4. a third failed attempt transitions the row to `exhausted` instead of retrying forever.

A stale `prepared` row is first eligible at its stored 15-minute stale-preparation deadline. Claiming a row happens in a short PostgreSQL transaction using a row lock. The claim increments the attempt count and moves `next_attempt_at` forward before the storage call, which acts as a lease against concurrent workers. Object-storage deletion always occurs after the database transaction is closed.

If a worker crashes after claiming an attempt, the moved `next_attempt_at` eventually makes the row eligible again. If attempt count is already three when an unresolved row becomes due, reconciliation marks it `exhausted` without starting an unbounded fourth attempt.

## Idempotency

The OPE-301 delete contract already treats an absent object as a successful delete. Cleanup therefore converges safely when:

- a request-time delete succeeded but its database status update failed;
- two recovery executions observe the same historical obligation at different times;
- an object never existed because the PUT failed before acceptance.

A `referenced` row is never deleted by reconciliation. A `succeeded` row is a no-op.

## Tenant and trust boundary

- Tenant ID, source ID, object ID, cleanup ID, and generated object key are server-owned.
- Cleanup repository operations require both cleanup ID and tenant ID.
- Foreign-tenant lookup/replay fails closed and never returns the foreign object key.
- Reconciliation is an internal trusted worker/platform operation. No tenant-facing cleanup endpoint is created by this ticket.
- The object-key layout remains `tenants/{tenantId}/knowledge/{sourceId}/raw/{objectId}`.
- Object keys, bucket names, endpoints, credentials, raw filenames, document content, tokens, and upload bodies must not be emitted in user-facing responses or cleanup logs.

## Observability and operator contract

The durable table is the source of truth for cleanup status. V1.3.04A exposes an internal status-count query for `prepared`, `pending`, `referenced`, `succeeded`, and `exhausted` so V1.10 platform/DLQ work can consume counts without reading object keys.

Safe log events may contain only bounded identifiers and state, for example cleanup ID, tenant ID, attempt number, status/outcome, and timing. The API currently has no production Python metrics exporter, so this ticket does not add a new telemetry dependency solely for one feature. The durable status-count contract is the metric source until planned platform observability instrumentation consumes it.

## Retention

- `prepared` and `pending` rows remain until they reach a terminal state.
- `exhausted` rows are retained until an operator-reviewed recovery resolves them; they are not automatically purged by this ticket.
- `referenced` and `succeeded` rows are eligible for later retention cleanup after 14 days, matching the architecture's dead-letter evidence horizon. This ticket does not implement the purge job.

## Relationship to V1.3.06 durable outbox

This ticket deliberately does not create a broker topic, outbox publisher, or worker dependency stack.

V1.3.06 may publish or schedule cleanup work from the durable table, but it must preserve these invariants:

- cleanup intent exists before PUT;
- successful source creation and `referenced` transition are one DB transaction;
- storage deletion is outside DB transactions;
- retry is bounded and idempotent;
- tenant ownership is rechecked on every recovery operation.

## Compatibility

This decision does not change:

- `POST /api/v1/knowledge-sources` request formats;
- successful response fields or status codes;
- existing storage-error response shape;
- `GET /api/v1/knowledge-sources` source-list behavior for failed uploads;
- supported file types or size limits;
- generated object-key layout;
- tenant/RBAC rules;
- parsing, indexing, or retrieval behavior.

The cleanup table is internal operator state and is not serialized by the knowledge-source API.

## Rollback

The schema change is additive. Code can be rolled back only after there are no unresolved `prepared`, `pending`, or `exhausted` cleanup rows. The migration downgrade enforces that safety gate before dropping the table. Rolling back to OPE-303 store-first behavior reintroduces the orphan risk and therefore requires an explicit operational decision rather than a silent code revert.
