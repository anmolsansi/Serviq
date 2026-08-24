# Knowledge Upload Consistency Runbook

## Purpose

This runbook covers V1.3.04A durable cleanup/reconciliation for raw knowledge uploads whose request did not complete successfully.

The authoritative contracts are:

- `docs/architecture-decisions/ADR-018-durable-knowledge-upload-consistency.md`;
- `docs/contract-changes/CCR-006-durable-knowledge-upload-cleanup-intent.md`.

## Durable signal

The operator source of truth is `knowledge_upload_cleanups`, not tenant-visible `knowledge_sources` rows.

Investigate rows in these states:

- `prepared` — the cleanup intent committed before object storage, but no terminal source/cleanup transition completed. It becomes eligible after its stored 15-minute grace deadline.
- `pending` — cleanup is required and `next_attempt_at` controls the bounded retry schedule.
- `exhausted` — three reconciliation attempts failed. This is the V1.3.04A DLQ-equivalent state and requires operator review.

`referenced` means the normal source transaction committed and the raw object must not be deleted. `succeeded` means deletion succeeded or the object was already absent.

## Security boundary

Only trusted platform/worker operations may inspect or act on cleanup records.

Do not:

- expose cleanup IDs or `object_key` through tenant-facing APIs;
- paste object keys, filenames, document content, credentials, tokens, bucket names, endpoints, or request bodies into logs or tickets;
- use production customer content for failure injection;
- delete an object for a `referenced` cleanup record;
- run cleanup for a tenant other than the row's server-owned `tenant_id`.

Safe evidence is limited to bounded tenant/cleanup/source IDs, status, attempt count, error code, timestamps, outcome, duration, and correlation IDs.

## Detection

Use a trusted database session and inspect state without selecting object keys:

```sql
SELECT tenant_id, id AS cleanup_id, source_id, status, attempt_count,
       next_attempt_at, last_error_code, created_at, updated_at
FROM knowledge_upload_cleanups
WHERE status IN ('prepared', 'pending', 'exhausted')
ORDER BY next_attempt_at NULLS LAST, created_at, id;
```

For dashboard/alert inputs, use grouped counts only:

```sql
SELECT status, count(*)
FROM knowledge_upload_cleanups
GROUP BY status
ORDER BY status;
```

The API service exposes the same internal status-count contract without object keys. Alert thresholds are not frozen by this ticket.

## Request-time recovery

A file upload follows this durability order:

1. authorize and validate the upload;
2. generate the server-owned source/object identifiers and existing OPE-301 raw key;
3. commit a `prepared` cleanup intent before object storage I/O;
4. call the S3-compatible PUT outside any database transaction;
5. after PUT success, create the normal `knowledge_sources` row and transition the cleanup to `referenced` in one PostgreSQL transaction;
6. return HTTP 201 only after that transaction commits.

If PUT fails or the source transaction fails, the request does not report success and does not create a tenant-visible failed source. The service best-effort arms cleanup as `pending`, performs one immediate idempotent delete, and best-effort marks cleanup `succeeded` if deletion confirms success/absence.

The immediate delete does not consume the background retry budget. If PostgreSQL is unavailable during recovery, the already committed `prepared` row remains durable. If deletion also fails, `prepared` or `pending` remains discoverable for replay.

## Reconciliation replay

The trusted replay entry point is `reconcile_file_upload_cleanup(...)`. No tenant-facing cleanup route exists.

Replay rules:

- lookup requires both `tenant_id` and cleanup ID;
- foreign-tenant lookup returns no work and never reveals or uses the foreign object key;
- `referenced` and `succeeded` are no-ops;
- `exhausted` does not retry automatically;
- only due `prepared`/`pending` work can be claimed;
- claim happens under `SELECT ... FOR UPDATE` in a short DB transaction;
- claim increments `attempt_count` and advances `next_attempt_at` before storage I/O;
- object deletion happens only after that DB transaction closes;
- S3-compatible delete is idempotent, so an already-absent object counts as success.

Background retries are bounded to exactly three deletion attempts:

```text
request failure -> first retry due in 30 seconds
attempt 1 failure -> next due in 5 minutes
attempt 2 failure -> next due in 30 minutes
attempt 3 failure -> exhausted
```

A stale `prepared` row first becomes eligible at its stored 15-minute grace deadline. If a worker crashes after claiming an attempt, the advanced `next_attempt_at` makes the obligation eligible again. A row already at three attempts transitions to `exhausted` rather than starting an unbounded fourth delete.

## Investigation

For an unresolved cleanup ID:

1. Confirm the row's tenant and status through trusted internal tooling.
2. If status is `prepared`/`pending` and due, prefer the normal reconciliation replay rather than manual object deletion.
3. If object storage is unavailable, leave the durable state unchanged and retry through the approved replay path later.
4. If status is `exhausted`, record the incident and resolve the storage/platform fault before any operator-approved requeue or manual recovery.
5. Never infer object absence from a timeout or generic storage error.

A metadata-only HEAD may be used by trusted incident tooling for diagnosis, but it is not required for normal idempotent cleanup replay.

## Failure-injection QA

Use only local/test infrastructure and synthetic content.

1. **Cleanup-intent DB failure before PUT**
   - Inject failure while creating `knowledge_upload_cleanups`.
   - Expected: request fails and object-storage PUT is never called.
2. **Normal success**
   - Expected: one source row, one raw object, and cleanup status `referenced` with attempt count `0`.
3. **PUT failure + immediate delete success**
   - Expected: existing storage error response, no source row, cleanup reaches `succeeded`.
4. **Ambiguous PUT + immediate delete failure**
   - Make test storage persist the object and then raise `ObjectStorageError`; make delete fail too.
   - Expected: request fails, no source row is created, raw object remains, and a durable `pending`/`prepared` cleanup row contains its generated key.
5. **PUT success + source transaction failure + delete failure**
   - Expected: source insert and `referenced` transition roll back together; the raw object remains discoverable by the durable cleanup intent.
6. **Replay success**
   - Restore storage, make cleanup due, replay once.
   - Expected: object is deleted once/idempotently and cleanup becomes `succeeded`.
7. **Foreign-tenant replay**
   - Replay a known cleanup ID using another tenant ID.
   - Expected: no storage call and no object-key disclosure.
8. **Retry exhaustion**
   - Fail three due reconciliation deletes.
   - Expected: attempt count `3`, status `exhausted`, no further automatic retry.
9. **Authorization**
   - Use a member without `knowledge.sources.manage` and a foreign tenant context.
   - Expected: rejection occurs before cleanup-intent creation or storage I/O.

## Rollback

Migration `20260824_0010` is additive, but its downgrade has a safety gate.

Before rollback:

1. stop new V1.3.04A upload traffic or deploy code that no longer creates cleanup intents;
2. inspect cleanup counts;
3. resolve every `prepared`, `pending`, and `exhausted` row;
4. confirm the unresolved count is zero;
5. only then downgrade `20260824_0010`.

The migration refuses to drop the table while unresolved obligations exist. Rolling application code back to OPE-303 store-first behavior reintroduces the audited double-failure orphan risk and requires an explicit operational decision.

## Evidence to retain

For acceptance or incident review, retain only:

- commit/PR and CI run identifiers;
- synthetic tenant/source/cleanup IDs;
- failure phase, status, attempt count, and safe error code;
- replay outcome and timing.

Never retain raw uploaded content, unrestricted object keys, credentials, tokens, bucket names, or endpoints in runbook evidence.
