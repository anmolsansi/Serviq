# CCR-006 — Durable knowledge upload cleanup intent

## Status

Approved for V1.3.04A / OPE-308.

## Date

2026-08-24

## Change type

Additive internal database and recovery contract. No public API contract change.

## Trigger

OPE-303's file-upload flow can create an untracked raw object when both the `knowledge_sources` database write and the compensating S3-compatible delete fail.

ADR-018 selects a pre-upload durable cleanup intent so every possible raw object is known to PostgreSQL before object storage is called.

## Existing frozen contracts preserved

The following remain unchanged:

- knowledge-source upload path and multipart/JSON request contracts;
- successful and error HTTP envelopes/status behavior;
- PDF/Markdown/text type and size limits;
- generated raw object-key layout;
- `knowledge_sources` source/document/chunk schema and source lifecycle values;
- OPE-301 S3-compatible adapter and idempotent delete semantics;
- tenant/RBAC ownership rules;
- parsing/indexing/retrieval scope.

## New table

V1.3.04A adds:

```text
knowledge_upload_cleanups
```

Columns:

```text
id               uuid primary key default uuidv7()
tenant_id        uuid not null -> tenants(id) ON DELETE RESTRICT
source_id        uuid not null
object_id        uuid not null
object_key       text not null
status           text not null
attempt_count    integer not null default 0
next_attempt_at  timestamptz null
last_error_code  text null
resolved_at      timestamptz null
created_at       timestamptz not null default now()
updated_at       timestamptz not null default now()
```

`source_id` and `object_id` are deliberately not foreign keys. The cleanup record is created before the `knowledge_sources` row, and a failed upload may correctly end with no source row at all. Persisting both IDs lets trusted recovery regenerate the typed OPE-301 raw key and compare it with the stored key before any destructive storage action.

## Constraints

- `status IN ('prepared','pending','referenced','succeeded','exhausted')`.
- `attempt_count BETWEEN 0 AND 3`.
- `(tenant_id, source_id)` is unique.
- `object_key` is unique. Generated OPE-301 keys are tenant-prefixed and one cleanup intent owns one generated object.
- `prepared` and `pending` require `next_attempt_at IS NOT NULL` and `resolved_at IS NULL`.
- `referenced`, `succeeded`, and `exhausted` require `next_attempt_at IS NULL` and `resolved_at IS NOT NULL`.

Indexes:

```text
(tenant_id, status, next_attempt_at)
(status, next_attempt_at)
```

The tenant-leading index supports trusted tenant/operator inspection. The due-work index supports bounded internal reconciliation without scanning terminal history.

## State semantics

### prepared

Committed before object storage. The initial `next_attempt_at` is 15 minutes after creation. A successful source transaction changes it to `referenced`. A generic PUT error remains `prepared` because its server-side outcome is ambiguous. If the process/database becomes unavailable before a later transition, the stored deadline still makes the upload discoverable to reconciliation.

### pending

Cleanup is known to be required, normally because PUT success was confirmed but source persistence failed. The first background retry is scheduled 30 seconds after that failure is armed.

### referenced

A durable `knowledge_sources` row owns this object. Cleanup must never delete it.

### succeeded

The object was safely deleted after a confirmed object outcome. Replays are successful no-ops.

### exhausted

Three reconciliation attempts were consumed without safe confirmation of cleanup. This is the V1.3.04A DLQ-equivalent durable state. It remains operator-visible and is not automatically purged.

## Retry and ambiguous-PUT contract

The request-time immediate delete is not counted as a background retry.

Known cleanup failures use:

```text
arm failure -> first retry due in 30 seconds
attempt 1 failure -> retry due in 5 minutes
attempt 2 failure -> retry due in 30 minutes
attempt 3 failure -> exhausted
```

A generic PUT error is treated conservatively. The cleanup remains `prepared` until its 15-minute stale-preparation deadline, which exceeds the S3 adapter's configured 5-second connect and 30-second read timeouts. A due `prepared` cleanup performs a typed metadata existence check before destructive action. If the object is absent or storage is unavailable, absence is not treated as terminal proof. The bounded observation budget advances and unresolved ambiguity eventually becomes `exhausted` rather than disappearing.

Claiming uses `SELECT ... FOR UPDATE` in a short transaction. The claim increments `attempt_count` and advances `next_attempt_at` before storage I/O. Storage HEAD/DELETE operations are always outside the database transaction.

## Upload transaction contract

The normal success path is:

```text
transaction A:
  create cleanup status=prepared
commit

object storage PUT

transaction B:
  insert knowledge_sources status=pending
  cleanup prepared -> referenced
commit

return success
```

If transaction B fails, neither source creation nor `referenced` commits. The original cleanup row remains recoverable.

## Immediate recovery contract

### Generic PUT error or ambiguous PUT result

1. keep the cleanup `prepared` with its original 15-minute deadline;
2. perform one idempotent DELETE outside a DB transaction as a fast recovery attempt;
3. do not mark `succeeded` from this immediate DELETE alone;
4. later reconciliation confirms object visibility/absence through the typed storage boundary and uses the bounded observation budget.

### Confirmed PUT success followed by source persistence failure

1. best-effort arm `prepared -> pending` with first retry due in 30 seconds and a bounded source-persistence error code;
2. perform one idempotent DELETE outside a DB transaction;
3. if delete succeeds, best-effort mark `succeeded`;
4. if delete fails, leave the row recoverable as `pending`, or as the original `prepared` row if PostgreSQL is unavailable during the arm.

A failure to update cleanup state never deletes the durable intent. A failure to mark a successful delete is safe because later delete replay is idempotent.

## Tenant and authorization contract

- Cleanup IDs and keys are server-owned.
- Repository/replay lookup uses both `tenant_id` and cleanup ID.
- Recovery regenerates the typed raw key from `tenant_id`, `source_id`, and `object_id` and exhausts safely if it does not match the persisted key.
- Foreign-tenant cleanup lookup/replay returns no object key and fails closed.
- No tenant-facing cleanup CRUD route is created.
- Trusted worker/platform operations may consume the internal cleanup state.

## Operator visibility

V1.3.04A exposes an internal count contract grouped by cleanup status. Platform/DLQ work can inspect prepared, pending, referenced, succeeded, and exhausted counts without returning object keys to tenant users.

Safe logs may include cleanup ID, tenant ID, status, attempt number, bounded error code, and timing. They must not include object keys, raw filenames, document bodies, tokens, credentials, bucket names, or storage endpoints.

## Retention

- Active `prepared`/`pending`: retain until terminal.
- `exhausted`: retain until operator-reviewed recovery resolves it.
- `referenced`/`succeeded`: eligible for later purge after 14 days.
- This ticket does not implement a purge job.

## Migration

Create additive Alembic revision `20260824_0010` after `20260819_0009`.

The upgrade creates only `knowledge_upload_cleanups` plus its constraints and indexes.

The downgrade must refuse to drop the table when any row has status `prepared`, `pending`, or `exhausted`. Terminal `referenced` and `succeeded` rows contain historical operator evidence only and may be dropped by an explicitly requested downgrade after the unresolved-work gate passes.

## Rollback

1. Stop new V1.3.04A upload traffic or deploy a version that no longer creates new cleanup intents.
2. Inspect cleanup counts.
3. Resolve every `prepared`, `pending`, and `exhausted` row through trusted recovery.
4. Confirm the unresolved count is zero.
5. Downgrade `20260824_0010` only then.
6. Understand that rolling application code back to OPE-303 reintroduces the original store-first double-failure orphan risk.

## Compatibility and later outbox integration

V1.3.06 may schedule or publish reconciliation from this durable state. It must not require a public API change or change the pre-PUT durability invariant. V1.10.09 DLQ operations may use the `exhausted` state and status-count contract as their inspection input.
