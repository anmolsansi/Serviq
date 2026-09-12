# Knowledge Upload Consistency Runbook

## Purpose

This runbook covers the durable cleanup obligations created by failed or interrupted file-backed knowledge uploads and the V1.3.04D worker scheduler that now reconciles them automatically.

Authoritative contracts:

- `docs/architecture-decisions/ADR-018-durable-knowledge-upload-consistency.md`
- `docs/architecture-decisions/ADR-028-worker-owned-knowledge-upload-cleanup-scheduler.md`
- `docs/contract-changes/CCR-006-durable-knowledge-upload-cleanup-intent.md`

The tenant-facing knowledge-source API does not expose this cleanup state or raw object keys.

## Durable signal

The source of truth is the internal table:

```text
knowledge_upload_cleanups
```

Statuses are:

- `prepared` — cleanup intent existed before PUT. An unresolved row becomes reconciliation-eligible at its stored deadline, normally 15 minutes after preparation.
- `pending` — cleanup is known to be required and has a bounded next retry time.
- `referenced` — the normal `knowledge_sources` row committed and owns the raw object. Never delete from this cleanup row.
- `succeeded` — cleanup was safely confirmed.
- `exhausted` — the three-attempt reconciliation budget was consumed without safe cleanup confirmation. Operator attention is required.

A failed upload still creates no tenant-visible knowledge-source row unless the normal source transaction committed successfully.

## Security boundary

Cleanup is a trusted worker/platform operation.

Do not:

- return cleanup rows or `object_key` through tenant-facing APIs;
- paste raw object keys, filenames, document content, credentials, tokens, bucket names, endpoints, or request bodies into logs or incident tickets;
- reconstruct a key from user-supplied text;
- replay cleanup for a tenant other than the cleanup row's tenant;
- run failure injection against production customer content.

Safe operational evidence is limited to bounded cleanup/tenant IDs, status, attempt count, bounded error code, timestamps, outcome, correlation IDs, and counts.

## Detection

Use the internal status-count repository contract when available. For a trusted database-only diagnostic, query counts without selecting keys:

```sql
SELECT status, count(*)
FROM knowledge_upload_cleanups
GROUP BY status
ORDER BY status;
```

Unresolved operator backlog is:

```sql
SELECT status, count(*)
FROM knowledge_upload_cleanups
WHERE status IN ('prepared', 'pending', 'exhausted')
GROUP BY status
ORDER BY status;
```

Do not expose these rows through the customer knowledge-source API.

## Investigating one cleanup

Use only trusted internal tooling.

1. Resolve the cleanup by both `tenant_id` and cleanup `id`.
2. Verify its `source_id` and `object_id` regenerate the exact typed key:

```text
tenants/{tenantId}/knowledge/{sourceId}/raw/{objectId}
```

3. If the regenerated key does not equal the persisted key, stop destructive work. The implementation moves the obligation to `exhausted` with a bounded key-mismatch code.
4. Inspect status and retry timing before any storage call.
5. Never delete an object for a `referenced` cleanup.

## Automatic worker reconciliation

`services/worker/app/jobs/knowledge_upload_cleanup.py` is the production caller for due cleanup work. It runs inside the normal durable worker `TaskGroup` alongside outbox publication and knowledge-sync consumption.

Every poll processes a bounded batch. Due `prepared` and `pending` rows are selected with `FOR UPDATE SKIP LOCKED`, so multiple worker processes can share the same table without intentionally claiming the same due row in one claim window.

The claim transaction is short. It validates the durable identifiers and exact generated key, increments the attempt counter, changes the row to `pending`, and advances `next_attempt_at` before object-storage I/O. The transaction then closes. HEAD/exists and DELETE happen only after that commit, so a slow storage dependency does not hold a PostgreSQL row lock.

If the worker crashes after a claim, no in-memory recovery record is required. The advanced `next_attempt_at` remains in PostgreSQL and a later worker can recover the obligation once that deadline becomes due.

A key mismatch is exhausted without any storage call. `referenced`, `succeeded`, and `exhausted` rows are not selected as due work.

## Reconciliation behavior

### Confirmed PUT succeeded, source DB transaction failed

The request tries to arm the row `pending`, due in 30 seconds, then performs one immediate idempotent DELETE outside the DB transaction.

If that delete succeeds, the row is best-effort marked `succeeded`. If the DB update fails, later worker replay can safely delete an already-absent object again.

If DELETE fails, the durable row remains `pending` or, if PostgreSQL was unavailable during the arm, remains `prepared` and becomes due at its original preparation deadline.

When the row becomes due, the worker claims it, performs the idempotent delete outside the claim transaction, and records the terminal result in a new short transaction.

### Generic PUT error or ambiguous result

A generic object-storage error does not prove whether the server accepted the PUT. The row therefore stays `prepared` even if the request performs an immediate DELETE.

At the 15-minute preparation deadline, reconciliation uses a metadata-only `exists`/HEAD check first:

- object visible: issue the idempotent DELETE and record success when confirmed;
- object absent: keep the obligation unresolved and consume one bounded observation attempt rather than declaring success immediately;
- HEAD unavailable: keep the obligation unresolved and consume one bounded attempt;
- three unresolved attempts: transition to `exhausted`.

The 15-minute delay is deliberately longer than the S3 adapter's 5-second connect and 30-second read timeouts.

## Retry schedule

The immediate request-time DELETE does not consume the reconciliation budget.

For a known cleanup failure:

```text
first retry due: 30 seconds
after attempt 1 failure: 5 minutes
after attempt 2 failure: 30 minutes
after attempt 3 failure: exhausted
```

A stale `prepared` row first becomes due at its stored 15-minute deadline and then uses the same three-attempt bounded budget.

The worker advances the retry lease before storage I/O. This is also the crash-recovery boundary: a claimed item is not immediately available to another worker while the first worker may still be performing the storage operation.

## Reservation and quota behavior

A cleanup-linked `knowledge_upload_reservations` row remains charged while raw-object ownership is unresolved.

The worker releases that reservation only after a safe terminal cleanup success. Existing request/source persistence logic also releases the reservation when the uploaded object becomes a normal referenced source.

A cleanup that becomes `exhausted` keeps its reservation. This is deliberate. An unresolved possible raw object must not disappear from source/byte accounting merely because automated cleanup ran out of attempts.

## Manual replay and operator intervention

Routine due cleanup no longer requires manual invocation. The durable worker scheduler is the normal production path.

Manual intervention is still appropriate for an `exhausted` obligation or controlled local/test diagnosis. Use only reviewed trusted tooling and resolve the cleanup by trusted tenant ID plus cleanup ID. Never accept an operator-supplied raw object key as the destructive input.

Do not manually reset attempt counters or requeue an exhausted record without an approved recovery decision. The current scheduler deliberately does not auto-requeue or purge exhausted rows.

## Exhausted cleanup

`exhausted` is the V1 cleanup DLQ-equivalent state.

When an item reaches `exhausted`:

1. do not silently requeue it;
2. record the cleanup ID, tenant ID, bounded error code, attempt count, and timing only;
3. verify storage health and database health;
4. use reviewed trusted tooling to determine whether the raw object exists;
5. do not modify/delete a `knowledge_sources` row as part of cleanup unless a separate approved recovery contract requires it;
6. keep the exhausted record and its unresolved quota reservation until an operator-reviewed recovery path resolves it.

V1.10.09 may consume the status/count contract for DLQ operations. V1.3.04D does not create that UI.

## Failure-injection QA

Use only local/test infrastructure and synthetic content.

1. **Cleanup-intent DB failure**
   - Inject failure before the cleanup-intent transaction commits.
   - Expected: request fails and object-storage PUT is never called.
2. **Happy upload**
   - Expected: one raw object, one `knowledge_sources` row in `pending`, and one cleanup row in `referenced`.
3. **Storage failure before/around acceptance**
   - Raise a generic storage error.
   - Expected: request keeps the existing storage error contract, no source row is created, and cleanup remains durably `prepared` for conservative reconciliation.
4. **Confirmed PUT + source DB failure + DELETE success**
   - Expected: request fails, no source row commits, object is absent, cleanup becomes `succeeded` when the final DB update succeeds.
5. **Confirmed PUT + source DB failure + DELETE failure**
   - Expected: request fails, no source row commits, object may remain, cleanup is durably `pending` with bounded retry.
6. **Source DB failure + retry-arm DB failure + DELETE failure**
   - Expected: request fails and the original `prepared` cleanup still exists with its stale-preparation deadline.
7. **Worker success replay**
   - Seed a due `pending` cleanup plus synthetic object and reservation.
   - Expected: worker deletes the object, marks cleanup `succeeded`, and releases the reservation.
8. **Restart recovery**
   - Let a due ambiguous `prepared` row consume one failed observation, stop that work unit, make the object visible, and invoke a fresh database session after the persisted deadline.
   - Expected: the fresh work unit uses only durable state, deletes the object, and completes cleanup.
9. **Retry exhaustion**
   - Keep an ambiguous object absent for all three reconciliation attempts.
   - Expected: attempt count reaches 3, status becomes `exhausted`, `next_attempt_at` clears, and the reservation remains charged.
10. **Key mismatch**
    - Persist an object key that does not match the generated tenant/source/object identity.
    - Expected: worker exhausts the obligation without making a storage call.
11. **Replay idempotency**
    - Delete once, replay again through a terminal state.
    - Expected: terminal state is not selected as new due work and no key is exposed.
12. **Foreign tenant**
    - Attempt to resolve a cleanup under another tenant through trusted test/operator boundaries.
    - Expected: safe unavailable/denial result and no storage action.
13. **Safe logs**
    - Capture cleanup logs around synthetic failures.
    - Expected: full generated object key, document body, filename, credentials, endpoints, and raw infrastructure exception text are absent.

The permanent `Knowledge Quota Integration` workflow now runs the worker cleanup integration suite against real PostgreSQL and the repository's S3-compatible storage service with synthetic fixture data.

## Migration and rollback

Migration `20260824_0010` is additive.

Before a database downgrade:

1. stop new upload traffic and the cleanup worker or otherwise prevent new cleanup-intent/claim activity;
2. count `prepared`, `pending`, and `exhausted` rows;
3. resolve all unresolved obligations through approved trusted recovery;
4. verify the unresolved count is zero;
5. only then run the Alembic downgrade.

The migration refuses to drop `knowledge_upload_cleanups` while any `prepared`, `pending`, or `exhausted` row exists.

Rolling only the V1.3.04D scheduler code back requires no migration, but it stops automatic recovery and recreates the original unscheduled-cleanup operational gap. Existing durable rows remain in PostgreSQL for later replay. Rolling application code all the way back to OPE-303's store-first compensation behavior reintroduces the audited orphan risk and is not a routine recovery step.

## Retention

- `prepared`/`pending`: retain until terminal.
- `exhausted`: retain until operator-reviewed recovery resolves it.
- `referenced`/`succeeded`: eligible for a later purge after 14 days.

V1.3.04D does not implement the purge job.

## Evidence to retain

For acceptance or incident review retain only:

- commit/PR and CI run identifiers;
- synthetic cleanup/tenant IDs;
- failure phase and bounded error code;
- status, attempt count, and timing;
- test outcome;
- aggregate status counts.

Never retain raw uploaded content, unrestricted object keys, credentials, tokens, bucket names, or storage endpoints in runbook evidence.
