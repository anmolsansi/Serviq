# ADR-018 — Durable knowledge upload consistency

## Status

Accepted for V1.3.04A.

## Date

2026-08-24

## Context

OPE-303 stores a generated raw knowledge object before committing its `knowledge_sources` row. If that database write fails, the service attempts to delete the object, but object-storage deletion can fail independently. The result can be a raw object that is neither referenced by PostgreSQL nor discoverable through a durable cleanup record.

The V1.3.04A requirement is stronger than best-effort compensation: every raw object that may have been accepted by object storage must already have a durable server-owned reference before the storage call occurs.

The existing V1 knowledge schema already provides the necessary durable fields without adding a new table:

- `knowledge_sources.id` identifies the generated source;
- `knowledge_sources.tenant_id` fixes tenant ownership server-side;
- `knowledge_sources.object_key` stores the generated OPE-301 raw key;
- `knowledge_sources.status` already permits `failed` and `pending`;
- `knowledge_sources.last_error_code` can carry a bounded, browser-safe recovery classification.

The public knowledge-source response does not expose `object_key` or storage credentials.

## Options considered

### Option A — Store first, then compensate on database failure

This is the OPE-303 behavior. It minimizes database writes on the success path, but two independent failures can leave an untracked object. Retrying deletion after the fact requires a durable cleanup record or an object-list reconciliation contract that the current repository does not have.

Rejected because it does not meet the V1.3.04A durability requirement.

### Option B — Add a cleanup-intent table and sweeper

A separate durable cleanup record could make failed compensation replayable and later expose DLQ state. This is viable, but it introduces a new persistence contract, retry lifecycle, worker ownership, retention policy, and operational surface immediately before V1.3.06, which owns the general durable outbox design.

Rejected for this ticket because the existing source row can provide the required durable reference with less new infrastructure.

### Option C — Persist the source reference before object storage

Create the file-backed source first in a durable failed/incomplete state, then perform the object PUT outside the transaction, then promote the source to normal `pending` only after the PUT succeeds.

Selected.

## Decision

For file-backed knowledge-source creation, Serviq uses this exact state transition:

1. Resolve tenant membership and require `knowledge.sources.manage`.
2. Validate the uploaded file completely.
3. Generate `source_id`, `object_id`, and the existing OPE-301 raw object key.
4. In a database transaction, create the file-backed `knowledge_sources` row with:
   - `status = 'failed'`;
   - `last_error_code = 'KNOWLEDGE_UPLOAD_INCOMPLETE'`;
   - the generated `object_key`;
   - `sync_version = 0`;
   - the existing tenant, creator, source type, name, and access scope values.
5. Commit that row before calling object storage.
6. Perform the S3-compatible PUT outside any database transaction.
7. If the PUT raises or its outcome is ambiguous, return the existing storage failure response. Do not delete the durable source reference and do not report success.
8. After PUT success, open a second database transaction and change only:
   - `status: 'failed' -> 'pending'`;
   - `last_error_code: 'KNOWLEDGE_UPLOAD_INCOMPLETE' -> NULL`;
   - `updated_at` to the transition time.
9. Return the existing successful upload response only after the second transaction commits.

The service no longer performs best-effort object deletion when the final database transition fails. The object is already referenced by the durable failed source row, so deleting it in that path would weaken the recovery evidence and reintroduce an unnecessary cross-store race.

## Failure semantics

### Initial database write fails

No object-storage PUT has occurred. The request fails and no raw object can exist from this attempt.

### Object-storage PUT fails before accepting the object

The request returns the existing storage error. The durable source remains `failed` with `KNOWLEDGE_UPLOAD_INCOMPLETE`. It references the generated key even if no object exists.

### Object-storage PUT succeeds but the response is lost

The request still fails safely. If the object exists, it is already referenced by the durable failed source row.

### Final database transition fails

The request fails. The raw object remains referenced by the already committed failed source row. A later trusted recovery process can inspect that durable state without relying on request logs.

## Tenant and security boundary

- Tenant ID, source ID, object ID, creator ID, and object key remain server-owned.
- The object-key layout remains `tenants/{tenantId}/knowledge/{sourceId}/raw/{objectId}`.
- `object_key`, bucket names, endpoints, credentials, tokens, raw documents, and upload bodies are never added to tenant-facing responses or logs.
- Recovery operations must use trusted platform/worker context and must verify the row's tenant before acting on its generated key.

## Observability

Safe telemetry may include source ID, tenant ID, phase (`prepared`, `storage_failed`, `committed`), outcome, duration, and the bounded error code. Raw filenames, object keys, credentials, document content, and request bodies must not be logged.

The durable operator-visible state for this ticket is the failed `knowledge_sources` row with `last_error_code = 'KNOWLEDGE_UPLOAD_INCOMPLETE'`.

## Compatibility

This decision does not change:

- `POST /api/v1/knowledge-sources` request formats;
- successful response fields or status codes;
- error response shapes;
- supported file types or size limits;
- the generated object-key layout;
- tenant/RBAC behavior;
- knowledge parsing, indexing, or retrieval behavior.

It changes only the internal ordering and durable failure state of file upload persistence.

## Relationship to ADR-017 and V1.3.06

This ADR supersedes only the **Storage and transaction boundary** section of ADR-017. ADR-017's multipart dependency, validation, upload limits, and object-key rules remain accepted.

V1.3.06 may introduce a general transactional outbox/DLQ framework for asynchronous work. That future design may consume failed upload state, but it must not reintroduce store-first creation or make raw-object discoverability depend on best-effort request-time deletion.

## Rollback

Code can be rolled back without a database migration because this ADR adds no schema. Failed rows created under this decision are valid under the existing knowledge schema. Before rolling code back to store-first behavior, operators must understand that the old double-failure orphan risk would return.
