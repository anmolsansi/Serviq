# Knowledge Upload Consistency Runbook

## Purpose

This runbook covers V1.3.04A durable cleanup obligations created by failed or interrupted file-backed knowledge uploads.

Authoritative contracts:

- `docs/architecture-decisions/ADR-018-durable-knowledge-upload-consistency.md`
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

## Reconciliation behavior

### Confirmed PUT succeeded, source DB transaction failed

The request tries to arm the row `pending`, due in 30 seconds, then performs one immediate idempotent DELETE outside the DB transaction.

If that delete succeeds, the row is best-effort marked `succeeded`. If the DB update fails, later replay can safely delete an already-absent object again.

If DELETE fails, the durable row remains `pending` or, if PostgreSQL was unavailable during the arm, remains `prepared` and becomes due at its original preparation deadline.

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

The implementation claims work in a short row-locked PostgreSQL transaction, increments the attempt counter, and advances `next_attempt_at` before storage I/O. HEAD and DELETE are performed only after the transaction is closed.

## Manual replay

V1.3.04A provides the internal reconciliation function but deliberately does not add a new public route, broker topic, or always-on worker deployment. V1.3.06 may schedule this durable state through the general outbox/worker design.

For local/test or an approved operator tool, invoke the internal cleanup service with:

- trusted tenant ID;
- cleanup ID;
- architecture-owned `ObjectStorage` adapter;
- normal database session.

Never accept a raw object key from an operator/client as the replay input. The service retrieves the key through the tenant-scoped cleanup row and regenerates the typed key before deletion.

## Exhausted cleanup

`exhausted` is the V1.3.04A DLQ-equivalent state.

When an item reaches `exhausted`:

1. do not silently requeue it;
2. record the cleanup ID, tenant ID, bounded error code, attempt count, and timing only;
3. verify storage health and database health;
4. use reviewed trusted tooling to determine whether the raw object exists;
5. do not modify/delete a `knowledge_sources` row as part of cleanup unless a separate approved recovery contract requires it;
6. keep the exhausted record until an operator-reviewed recovery path resolves it.

V1.10.09 may consume the status/count contract for DLQ operations. This ticket does not create that UI.

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
7. **Replay idempotency**
   - Delete once, replay again.
   - Expected: terminal success is a no-op and does not leak the key.
8. **Foreign tenant**
   - Replay a cleanup ID using another tenant.
   - Expected: safe unavailable/denial result and no storage action.
9. **Retry exhaustion**
   - Force storage failure for all three reconciliation attempts.
   - Expected: attempt count reaches 3, status becomes `exhausted`, `next_attempt_at` clears, and operator counts include the row.
10. **Safe logs**
   - Capture cleanup logs.
   - Expected: full generated object key, document body, filename, and credentials are absent.

## Migration and rollback

Migration `20260824_0010` is additive.

Before downgrade:

1. stop new V1.3.04A upload traffic or otherwise prevent new cleanup-intent creation;
2. count `prepared`, `pending`, and `exhausted` rows;
3. resolve all unresolved obligations through approved trusted recovery;
4. verify the unresolved count is zero;
5. only then run the Alembic downgrade.

The migration refuses to drop `knowledge_upload_cleanups` while any `prepared`, `pending`, or `exhausted` row exists.

Rolling application code back to OPE-303's store-first compensation behavior reintroduces the audited orphan risk and is not a routine recovery step.

## Retention

- `prepared`/`pending`: retain until terminal.
- `exhausted`: retain until operator-reviewed recovery resolves it.
- `referenced`/`succeeded`: eligible for a later purge after 14 days.

V1.3.04A does not implement the purge job.

## Evidence to retain

For acceptance or incident review retain only:

- commit/PR and CI run identifiers;
- synthetic cleanup/tenant IDs;
- failure phase and bounded error code;
- status, attempt count, and timing;
- test outcome;
- aggregate status counts.

Never retain raw uploaded content, unrestricted object keys, credentials, tokens, bucket names, or storage endpoints in runbook evidence.
