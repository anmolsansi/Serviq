# Knowledge Upload Consistency Runbook

## Purpose

This runbook covers file-backed knowledge sources that remain in the durable V1.3.04A incomplete state after a failed or interrupted upload request.

The authoritative architecture decision is `docs/architecture-decisions/ADR-018-durable-knowledge-upload-consistency.md`.

## Durable signal

A source requires operator investigation when all of these are true:

- it is a file-backed source (`pdf`, `markdown`, or `text`);
- `status = 'failed'`;
- `last_error_code = 'KNOWLEDGE_UPLOAD_INCOMPLETE'`.

This state is intentionally durable. The generated `object_key` may point to an object that does not exist, or to an object that storage accepted even though the request later failed. Either case is safe because any object that may exist is already referenced by the source row.

## Security boundary

Only trusted platform/worker operations may inspect or act on the stored object key.

Do not:

- return `object_key` through a tenant-facing API;
- paste object keys, filenames, document content, credentials, tokens, or request bodies into logs or tickets;
- use production customer data for failure injection;
- delete an object only because a client request failed.

Safe operational evidence is limited to bounded tenant/source IDs, status, error code, timestamps, outcome, attempt count when a future reconciliation worker exists, and correlation IDs.

## Detection

Use a trusted database session and count incomplete rows without selecting document content:

```sql
SELECT tenant_id, id AS source_id, status, last_error_code, created_at, updated_at
FROM knowledge_sources
WHERE source_type IN ('pdf', 'markdown', 'text')
  AND status = 'failed'
  AND last_error_code = 'KNOWLEDGE_UPLOAD_INCOMPLETE'
ORDER BY created_at, id;
```

The count of these rows is the V1.3.04A operator-visible backlog. Alerting thresholds are not frozen by this ticket.

## Investigation

For one source, use trusted internal tooling to read its server-owned `object_key` and perform a metadata-only object-storage HEAD request.

Classify the result as one of:

1. **Object exists.** The upload may have succeeded but the request or final DB transition failed. Keep the object. Do not compensate-delete it.
2. **Object is absent.** The PUT failed before object creation, or the request stopped before PUT. The failed row remains safe durable evidence.
3. **Storage is unavailable or outcome is unknown.** Make no destructive change. Retry the metadata-only check later through approved operational tooling.

Do not infer object absence from a timeout or generic storage error.

## Recovery

V1.3.04A deliberately does not create a new worker, cleanup queue, DLQ, or object-list sweeper. V1.3.06 owns the first general durable knowledge outbox contract.

Until a later trusted reconciliation command is frozen:

- do not manually set a failed source to `pending` unless an approved incident procedure has independently proved the object exists and the change is reviewed;
- do not manually delete the source row when the object outcome is unknown;
- do not manually delete a raw object whose durable source row still exists;
- if the user needs the content immediately, have them submit a new upload through the normal API. Treat the old failed row as operational evidence until an approved reconciliation path retires it.

A future recovery command may safely use the failed source row as its source of truth. It must verify tenant ownership, use the stored generated key, be idempotent, and avoid exposing the key to tenant users.

## Failure-injection QA

Use only local/test infrastructure and synthetic content.

1. **Initial DB failure**
   - Inject failure while inserting the file source.
   - Expected: request fails, storage PUT is never called, and no object exists from the attempt.
2. **Storage failure before acceptance**
   - Commit the failed/incomplete source row, then make PUT fail.
   - Expected: request returns the existing storage-unavailable error and the durable row remains failed.
3. **Ambiguous storage outcome**
   - Make test storage persist the object and then raise `ObjectStorageError`.
   - Expected: request fails, the object remains present, and its exact generated key equals the failed source row's `object_key`.
4. **Final DB transition failure**
   - Let PUT succeed, then fail the `failed -> pending` transition.
   - Expected: request fails, object remains present, and the failed source row still references it.
5. **Success**
   - Expected: one raw object, one matching source row, `status = 'pending'`, and `last_error_code IS NULL`.
6. **Authorization**
   - Use a tenant member without `knowledge.sources.manage` and a foreign-tenant context.
   - Expected: request is rejected before the durable source row or storage object is created.

## Rollback

No schema rollback is required because V1.3.04A reuses existing `knowledge_sources` columns.

Do not roll application code back to ADR-017's store-first compensation behavior as a routine recovery step. That ordering reintroduces the audited double-failure orphan risk. If a rollback is unavoidable, record the risk explicitly and run a separate storage/database reconciliation before declaring the incident closed.

## Evidence to retain

For acceptance or incident review, retain only:

- commit/PR and CI run identifiers;
- synthetic tenant/source IDs;
- failure phase and safe error code;
- whether the object metadata check returned exists/absent/unknown;
- test outcome and timing.

Never retain raw uploaded content, unrestricted object keys, credentials, or tokens in the runbook evidence.
