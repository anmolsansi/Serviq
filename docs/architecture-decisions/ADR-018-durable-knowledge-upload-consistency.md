# ADR-018 — Durable knowledge upload consistency

## Status

Accepted for V1.3.04A / OPE-308.

## Date

2026-08-24

## Context

OPE-303 stores a generated raw knowledge object before committing its `knowledge_sources` row. If that database write fails, the request tries to delete the object, but object-storage deletion can fail independently. A simultaneous database and delete failure can therefore leave a raw object with no durable source row and no durable cleanup obligation.

V1.3.04A strengthens the invariant to:

> Before Serviq can attempt a raw-object PUT, PostgreSQL must already contain a durable, tenant-owned record that lets a trusted recovery process find the exact generated object without relying on request logs or object-store listing.

The public knowledge-source API must remain compatible. A failed upload must not create a tenant-visible `knowledge_sources` row merely to solve an internal cleanup problem.

The repository also does not yet have the general durable outbox/worker implementation planned for V1.3.06, so this ticket must not invent a broker-specific cleanup architecture.

## Options considered

### Option A — Keep store-first plus best-effort delete

This is the OPE-303 behavior. It is simple on the success path, but simultaneous database and delete failures can leave an object with no durable owner or cleanup record.

Rejected because it is the defect this ticket exists to remove.

### Option B — Create the user-visible knowledge source before object storage

The source row could be written first in a failed/incomplete state, then promoted to `pending` after the object PUT succeeds.

Rejected because it changes the observable data contract. Failed file uploads that previously created no source would become visible through `GET /api/v1/knowledge-sources`. It also overloads the customer-facing source lifecycle with an operator-only cleanup concern and still needs separate retry/exhaustion metadata.

### Option C — Reconcile by listing raw objects and comparing them with PostgreSQL

A periodic sweep could enumerate tenant raw-object prefixes and delete objects with no source row.

Rejected because the current `ObjectStorage` contract intentionally has no list operation. Adding listing, pagination, stale/in-flight grace rules, and prefix-scan cost would widen the storage contract and create a larger race surface than necessary.

### Option D — Persist a cleanup intent before object storage

Create a small PostgreSQL cleanup-intent row before the PUT. On successful source persistence, atomically mark the cleanup intent `referenced` in the same transaction as the new source. On failure, the intent remains recoverable and can drive bounded idempotent reconciliation.

Selected.

## Decision

Serviq adds the tenant-owned `knowledge_upload_cleanups` table frozen by CCR-006.

A file upload uses this ordering:

1. Resolve the trusted tenant/user and require `knowledge.sources.manage`.
2. Validate the complete file using the existing OPE-303 limits and content rules.
3. Generate the server-owned `source_id`, `object_id`, `cleanup_id`, and existing OPE-301 raw object key.
4. Commit one `knowledge_upload_cleanups` row **before object storage I/O** with status `prepared`, attempt count `0`, and a stale-preparation reconciliation time 15 minutes in the future.
5. Only after that commit may Serviq call `ObjectStorage.put_object`.
6. After a confirmed successful PUT, open one PostgreSQL transaction that creates the normal file-backed `knowledge_sources` row with status `pending` and changes the cleanup row from `prepared` to `referenced`.
7. Return the existing successful upload response only after that transaction commits.

The raw object is therefore never attempted before PostgreSQL knows its exact generated key and tenant/source/object identity.

## Why `prepared` has a 15-minute grace period

The S3-compatible adapter uses a 5-second connect timeout, a 30-second read timeout, and one total client attempt. A generic storage exception can still be ambiguous from the caller's perspective, for example a response can be lost after the server accepted the write.

Serviq therefore does not treat an immediate compensating DELETE after a generic PUT exception as proof that no object can appear later. The durable `prepared` row remains eligible after 15 minutes, which is deliberately far beyond the configured request timeout. Reconciliation then performs a metadata-only existence check before deciding whether deletion is appropriate.

## Cleanup state machine

`knowledge_upload_cleanups.status` is one of:

- `prepared` — committed before PUT. A row still unresolved after 15 minutes represents an abandoned or ambiguous request and is eligible for reconciliation.
- `pending` — cleanup is known to be required, normally because PUT success was confirmed but source persistence failed. `next_attempt_at` controls bounded retry.
- `referenced` — the source row committed successfully and now durably owns the raw object. Cleanup must never delete it.
- `succeeded` — deletion was confirmed after a known object outcome, or reconciliation observed the object and deleted it. Replay is a no-op.
- `exhausted` — three reconciliation attempts were consumed without safe confirmation of cleanup. The row remains operator-visible and is never silently dropped.

`referenced`, `succeeded`, and `exhausted` are terminal for this ticket. A later operator workflow may explicitly requeue an exhausted item under a separately reviewed contract.

## Failure handling

### Cleanup-intent insert fails

No object PUT is attempted. The request fails and this attempt cannot create an untracked object.

### PUT raises a generic storage error

The public request keeps the existing storage-failure behavior and creates no `knowledge_sources` row.

Because the PUT outcome is ambiguous, Serviq keeps the cleanup intent in `prepared` with its 15-minute deadline. It may attempt one immediate idempotent DELETE outside a database transaction as a fast recovery optimization, but it does **not** mark the cleanup `succeeded` from that DELETE alone.

When the `prepared` row becomes due, reconciliation first calls the typed storage `exists`/HEAD boundary:

- if the object is visible, it is safe to issue the idempotent DELETE and then mark `succeeded`;
- if the object is absent, Serviq does not claim success immediately because the original PUT outcome was ambiguous. It records another bounded observation attempt and retries according to the schedule below;
- if HEAD is unavailable, the attempt remains unresolved and follows the same bounded retry path;
- after the third unresolved observation/delete attempt, the row becomes `exhausted` and remains operator-visible.

### PUT succeeds but source persistence fails

The `knowledge_sources` insert and cleanup `referenced` transition are in one transaction. If that transaction fails, neither change commits. The original cleanup intent remains durable.

Here the PUT outcome is known, so Serviq best-effort arms the cleanup from `prepared` to `pending` with the first retry due in 30 seconds. It then attempts one immediate idempotent DELETE outside a database transaction. If that delete succeeds, Serviq best-effort marks the cleanup `succeeded`. If either the arm/update or delete fails, the already committed cleanup intent remains `prepared` or `pending` and is discoverable by reconciliation.

A simultaneous source-DB failure and delete failure therefore leaves durable cleanup work and never reports upload success.

### Process crash

A crash can occur after the intent commit and before any later transition. The `prepared` row is intentionally durable. After its 15-minute grace period, reconciliation treats it as abandoned/ambiguous and applies the metadata-confirmation behavior above unless a successful source transaction already changed it to `referenced`.

## Bounded reconciliation and retry schedule

The request-time immediate delete is an optimization and does not consume the background retry budget.

For a known cleanup failure, reconciliation uses exactly three attempts:

1. first retry: 30 seconds after cleanup is armed;
2. second retry: 5 minutes after the first failed reconciliation attempt;
3. third retry: 30 minutes after the second failed reconciliation attempt;
4. a third failed attempt transitions the row to `exhausted` instead of retrying forever.

A stale `prepared` row is first eligible at its stored 15-minute deadline and consumes the same three-attempt budget while preserving its ambiguous-outcome error code.

Claiming a row happens in a short PostgreSQL transaction using a row lock. The claim increments `attempt_count` and advances `next_attempt_at` before storage I/O. The advanced deadline acts as a bounded lease against concurrent workers. HEAD and DELETE operations always occur after the database transaction is closed.

If a worker crashes after claiming an attempt, the moved `next_attempt_at` eventually makes the row eligible again. If attempt count is already three when an unresolved row becomes due, reconciliation marks it `exhausted` without starting an unbounded fourth attempt.

## Idempotency

The OPE-301 delete contract already treats an absent object as a successful delete. Cleanup therefore converges safely when:

- a confirmed-source-failure delete succeeded but its database status update failed;
- two recovery executions observe the same historical obligation at different times;
- a worker crashes after claiming an attempt;
- a raw object has already been removed by an earlier trusted cleanup.

An ambiguous PUT is handled more conservatively: absence alone does not terminalize the cleanup until the bounded observation policy has established a safe outcome, and unresolved ambiguity becomes `exhausted` rather than disappearing.

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

Safe log events contain only bounded identifiers and state, such as cleanup ID, tenant ID, attempt number, status/outcome, and timing. The API currently has no production Python metrics exporter, so this ticket does not add a new telemetry dependency solely for one feature. The durable status-count contract is the metric source until planned platform observability instrumentation consumes it.

## Retention

- `prepared` and `pending` rows remain until they reach a terminal state.
- `exhausted` rows are retained until an operator-reviewed recovery resolves them. They are not automatically purged by this ticket.
- `referenced` and `succeeded` rows are eligible for later retention cleanup after 14 days, matching the architecture's dead-letter evidence horizon. This ticket does not implement the purge job.

## Relationship to V1.3.06 durable outbox

This ticket deliberately does not create a broker topic, outbox publisher, or new worker dependency stack.

V1.3.06 may publish or schedule cleanup work from the durable table, but it must preserve these invariants:

- cleanup intent exists before PUT;
- successful source creation and `referenced` transition are one DB transaction;
- storage HEAD/DELETE is outside DB transactions;
- retry is bounded and idempotent;
- ambiguous PUT outcomes remain conservative and operator-visible;
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

The schema change is additive. Code can be rolled back only after there are no unresolved `prepared`, `pending`, or `exhausted` cleanup rows. The migration downgrade enforces that safety gate before dropping the table. Rolling application code back to OPE-303 store-first behavior reintroduces the orphan risk and therefore requires an explicit operational decision rather than a silent code revert.
