from pathlib import Path

build_guide = Path("docs/SERVIQ_BUILD_GUIDE.md")
architecture = Path("docs/ARCHITECTURE.md")
repo_context = Path("docs/repo_context.md")

build_marker = "## V1.3.04A — Durable knowledge-upload consistency"
build_section = r'''

---

## V1.3.04A — Durable knowledge-upload consistency

V1.3.04A closes the cross-system failure gap in file-backed knowledge uploads tracked by GitHub #178 and Linear OPE-308. The implementation merged through PR #180.

### Problem and invariant

A raw knowledge upload crosses S3-compatible object storage and PostgreSQL. Before this ticket, a raw object could upload successfully, the `knowledge_sources` transaction could fail, and the compensating delete could fail too. That left an object with neither a normal source reference nor durable cleanup work.

The implemented invariant is:

> Before Serviq attempts a raw-object PUT, PostgreSQL already contains enough tenant-scoped information to reconcile that exact generated object later.

Every attempted raw upload is therefore either referenced by normal product state or represented by durable cleanup state until it is resolved or explicitly exhausted for operator action.

### Architecture selected

ADR-018 and CCR-006 freeze a pre-upload PostgreSQL cleanup-intent design. Serviq does not create a tenant-visible failed source before storage succeeds, does not depend on bucket-wide object listing, and does not add a new broker/outbox dependency before the planned asynchronous platform work.

The internal `knowledge_upload_cleanups` table stores the cleanup ID, tenant ID, intended source/object IDs, exact generated raw key, status, bounded attempt count, next retry time, safe error code, resolution time, and audit timestamps.

The states are `prepared`, `pending`, `referenced`, `succeeded`, and `exhausted`.

- `prepared`: PostgreSQL knows the upload identity before the PUT.
- `pending`: cleanup/reconciliation work remains.
- `referenced`: normal source creation and cleanup reference transition committed together.
- `succeeded`: cleanup completed.
- `exhausted`: the bounded DLQ-equivalent state requiring operator recovery.

### Successful upload flow

For an authorized valid file upload, Serviq:

1. enforces the existing `knowledge.sources.manage` permission;
2. validates the existing upload type/size contract;
3. generates source ID, object ID, cleanup ID, and typed raw-object key server-side;
4. commits a `prepared` cleanup intent before object-storage I/O;
5. performs the PUT outside a database transaction;
6. after confirmed PUT success, row-locks the cleanup and creates the normal `knowledge_sources` row while transitioning cleanup to `referenced` in the same PostgreSQL transaction;
7. returns the existing success response.

The public request/response envelope, generated key layout, supported types/size limits, permission rule, and tenant-visible source-list behavior remain unchanged.

### Confirmed source-persistence failure

If storage confirms the PUT but the source transaction fails, the source transaction rolls back while the pre-existing cleanup row survives. Serviq then performs fast recovery outside the database transaction: it arms cleanup for reconciliation, attempts one immediate idempotent delete, and records success when possible. If delete or the follow-up state write also fails, the already-durable cleanup row remains available to reconciliation.

The failed request is never converted into upload success merely because cleanup work was scheduled.

### Double-failure guarantee

For the adversarial sequence:

```text
object PUT succeeds
        +
source PostgreSQL transaction fails
        +
compensating DELETE fails
```

Serviq retains a `prepared` or `pending` cleanup obligation for the exact tenant/source/object identity. The object therefore remains discoverable through durable cleanup state even when both request-time recovery operations fail.

### Ambiguous PUT outcome

A client-side object-storage error does not always prove the remote PUT failed. A timeout can occur after the server accepted the object. Generic PUT errors are therefore treated as outcome-ambiguous.

The durable cleanup remains `prepared` with a 15-minute stale deadline. An immediate delete may still run as an optimization, but that delete alone does not terminalize the obligation. When the stale intent is due, reconciliation uses the existing typed `exists`/HEAD operation first. If the object is visible, it deletes it idempotently. If the object is absent or the presence check fails, the bounded ambiguous-outcome retry path remains active instead of silently declaring success.

The 15-minute grace is intentionally much longer than the bounded object-storage adapter request timeouts.

### Retry and exhaustion contract

The request-time immediate delete does not consume the background retry budget.

For confirmed source-persistence failure, the first replay is due after 30 seconds. Background failures then follow:

- attempt 1 failure -> retry in 5 minutes;
- attempt 2 failure -> retry in 30 minutes;
- attempt 3 failure -> `exhausted`.

A stale ambiguous `prepared` intent uses the same three-attempt reconciliation budget after its grace period.

The due row is claimed in a short row-locked PostgreSQL transaction. Object-storage HEAD/DELETE operations happen after that transaction ends, so slow storage calls do not hold database locks.

### Tenant, key, and logging safety

Replay is scoped by both tenant ID and cleanup ID. Foreign-tenant access is rejected before storage I/O. The replay path regenerates the typed raw key from stored tenant/source/object identity and compares it with the persisted key; a mismatch fails closed into an exhausted key-mismatch state rather than deleting an unexpected object.

No tenant-facing cleanup endpoint was added.

Structured logs contain only bounded operational fields such as cleanup ID, tenant ID, status, attempt count, and safe error code. They omit raw object keys, file contents, credentials, tokens, and secrets. An internal status-count query provides operator-visible counts without exposing document/key data; this ticket does not add a new metrics SDK.

### Retention and rollback safety

Unresolved `prepared` and `pending` work remains until reconciled. `exhausted` work remains for operator recovery. Resolved `referenced` and `succeeded` rows are eligible for a later purge after 14 days; V1.3.04A intentionally does not implement that purge job.

Alembic revision `20260824_0010_knowledge_upload_cleanups.py` adds the cleanup table and constraints. Its downgrade refuses to drop the table while unresolved `prepared`, `pending`, or `exhausted` obligations remain, preventing rollback from deleting the only durable evidence needed to reconcile an uploaded object.

The operational procedure is documented in `docs/KNOWLEDGE_UPLOAD_CONSISTENCY_RUNBOOK.md`.

### Validation evidence

The merged implementation covers:

- happy upload and durable `referenced` state;
- cleanup-intent DB failure proving PUT is never attempted;
- confirmed source DB failure plus delete success;
- source DB failure plus delete failure leaving durable work;
- an additional DB failure while arming retry, proving the pre-upload intent survives;
- ambiguous PUT behavior;
- due cleanup replay and repeated-replay idempotency;
- foreign-tenant replay denial before storage access;
- 30-second / 5-minute / 30-minute scheduling and bounded exhaustion;
- status counts and safe log non-disclosure;
- real PostgreSQL migration/schema integration;
- S3-compatible object-storage integration.

The exact implementation head `22ad508fc148f68759b4b0466323e9ce6e452c1c` passed both CI and Security. PR #180 merged it into `main` as `ae9c2d67b8e09b3db62e824b7868fa3e163324b0` on 2026-08-26.

### Primary implementation and evidence files

```text
docs/KNOWLEDGE_UPLOAD_CONSISTENCY_RUNBOOK.md
docs/V1.3.04A_SECURITY_RELIABILITY_REVIEW.md
docs/architecture-decisions/ADR-017-knowledge-upload-multipart-boundary.md
docs/architecture-decisions/ADR-018-durable-knowledge-upload-consistency.md
docs/contract-changes/CCR-006-durable-knowledge-upload-cleanup-intent.md
services/api/alembic/versions/20260824_0010_knowledge_upload_cleanups.py
services/api/app/modules/knowledge/cleanup.py
services/api/app/modules/knowledge/models.py
services/api/app/modules/knowledge/repository.py
services/api/app/modules/knowledge/service.py
services/api/tests/integration/test_database_integration.py
services/api/tests/integration/test_knowledge_file_upload_api.py
services/api/tests/integration/test_knowledge_upload_cleanup.py
```

### Intentionally out of scope

V1.3.04A does not implement knowledge parsing/indexing, customer attachments, bucket lifecycle policies, a new storage service, a general transactional outbox, new broker consumers/topics, a cleanup UI, or changes to generated object-key/file rules.
'''

text = build_guide.read_text()
if build_marker not in text:
    build_guide.write_text(text.rstrip() + build_section + "\n")

arch_text = architecture.read_text()
cleanup_schema = r'''knowledge_upload_cleanups
  id uuid PK DEFAULT uuidv7()
  tenant_id uuid NOT NULL FK tenants RESTRICT
  source_id uuid NOT NULL
  object_id uuid NOT NULL
  object_key text NOT NULL
  status text NOT NULL CHECK prepared|pending|referenced|succeeded|exhausted
  attempt_count integer NOT NULL DEFAULT 0 CHECK 0..3
  next_attempt_at timestamptz NULL
  last_error_code text NULL
  resolved_at timestamptz NULL
  created_at timestamptz NOT NULL DEFAULT now()
  updated_at timestamptz NOT NULL DEFAULT now()
Constraints: UNIQUE(tenant_id, source_id), UNIQUE(object_key); unresolved states require next_attempt_at and no resolved_at; terminal states require resolved_at and no next_attempt_at
Indexes: (tenant_id, status, next_attempt_at), (status, next_attempt_at)

'''
if "knowledge_upload_cleanups\n" not in arch_text:
    needle = "knowledge_documents\n  id uuid PK\n"
    if needle not in arch_text:
        raise SystemExit("Architecture knowledge_documents insertion point not found")
    arch_text = arch_text.replace(needle, cleanup_schema + needle, 1)

arch_marker = "## V1.3.04A durable knowledge-upload consistency contract"
arch_section = r'''

## V1.3.04A durable knowledge-upload consistency contract

ADR-018 and CCR-006 freeze the cross-store raw-upload boundary. Before any raw object PUT, the API commits a tenant-scoped `knowledge_upload_cleanups` row containing generated source/object identity and the typed raw key. A confirmed successful PUT is followed by one PostgreSQL transaction that creates the normal `knowledge_sources` row and changes cleanup to `referenced` atomically.

Storage I/O is never performed while the cleanup/source transaction is open. Confirmed source-persistence failure keeps the durable intent, schedules first replay after 30 seconds, and may perform one immediate idempotent delete as a fast path. Background failures retry after 5 minutes and 30 minutes; the third failed replay becomes `exhausted`.

A generic PUT error is outcome-ambiguous. Its `prepared` intent remains durable for a 15-minute grace period and due reconciliation uses the typed `exists`/HEAD operation before deciding whether deletion is required. The same bounded observation/retry budget applies when presence cannot be safely resolved.

Replay is tenant-scoped and regenerates the expected typed key from tenant/source/object identity. A key mismatch fails closed. Structured state logs and internal status counts omit object keys, file contents, credentials, and tokens. No public cleanup API is added.

Resolved `referenced`/`succeeded` rows are eligible for a future purge after 14 days; unresolved and `exhausted` work is retained for reconciliation/operator recovery. Alembic downgrade refuses to drop the table while unresolved `prepared`, `pending`, or `exhausted` obligations exist.

This preserves the existing knowledge-upload HTTP envelope, supported file rules, RBAC behavior, tenant-visible source listing, and raw object-key layout. General outbox/broker integration remains future work.
'''
if arch_marker not in arch_text:
    arch_text = arch_text.rstrip() + arch_section + "\n"
architecture.write_text(arch_text)

context_text = repo_context.read_text()
old_header = '''> Current-state engineering map, audited on 2026-08-22 at `main` commit
> `258d189` (`Merge OPE-304 release system reconciliation`). This describes
> code that exists. Future contracts remain in `PRD.md`, `ARCHITECTURE.md`, and
> the staged roadmap. The workforce OIDC integration-evidence notes below were
> refreshed on 2026-08-23 for V1.1.15 against `main` base `1422834`.
'''
new_header = '''> Current-state engineering map. The knowledge-upload consistency state was
> refreshed on 2026-08-26 after V1.3.04A merged to `main` as `ae9c2d6`.
> This describes code that exists. Future contracts remain in `PRD.md`,
> `ARCHITECTURE.md`, and the staged roadmap. Earlier subsystem evidence notes
> retain their ticket-specific dates and commit references below.
'''
if old_header in context_text:
    context_text = context_text.replace(old_header, new_header, 1)
context_text = context_text.replace(
    "| `migrations` | Alembic schema history | Nine revisions through knowledge permissions |",
    "| `migrations` | Alembic schema history | Ten revisions through durable knowledge-upload cleanup intents |",
    1,
)

context_marker = "## V1.3.04A current state — durable knowledge uploads"
context_section = r'''

## V1.3.04A current state — durable knowledge uploads

File-backed knowledge-source registration now has an implemented cross-store consistency boundary. Before the API attempts the generated raw-object PUT, it commits an internal tenant-owned `knowledge_upload_cleanups` row containing the source/object identity, generated key, retry state, bounded error code, and timestamps required for reconciliation.

On confirmed PUT success, the normal `knowledge_sources` insert and cleanup transition to `referenced` occur in the same PostgreSQL transaction. If source persistence fails, the pre-upload intent survives rollback. Request-time cleanup performs a best-effort immediate delete outside the database transaction while durable reconciliation remains available if deletion or the follow-up state write fails.

Generic storage PUT failures are treated as outcome-ambiguous rather than assumed absent. `prepared` work has a 15-minute stale deadline; due reconciliation uses the typed presence check before deletion. Confirmed cleanup replay starts at 30 seconds, then retries after 5 minutes and 30 minutes, with the third failed replay becoming `exhausted`.

Replay is internal, tenant-scoped, idempotent, and key-validated. Foreign-tenant access is rejected before storage I/O. Object keys, file data, credentials, and tokens are excluded from cleanup logs and status-count visibility. There is no public cleanup endpoint.

Alembic revision `20260824_0010` adds the schema and refuses downgrade while unresolved cleanup obligations exist. The worker remains a scaffold: this ticket implements the durable reconciliation service contract but does not claim a general transactional outbox, broker consumer, scheduler, cleanup UI, or resolved-row purge job is deployed.

Primary evidence is ADR-018, CCR-006, `KNOWLEDGE_UPLOAD_CONSISTENCY_RUNBOOK.md`, `V1.3.04A_SECURITY_RELIABILITY_REVIEW.md`, migration 0010, the knowledge cleanup/service/repository modules, and PostgreSQL/S3-compatible integration tests.

The exact implementation head `22ad508fc148f68759b4b0466323e9ce6e452c1c` passed CI and Security before PR #180 merged it into `main` as `ae9c2d67b8e09b3db62e824b7868fa3e163324b0` on 2026-08-26.
'''
if context_marker not in context_text:
    context_text = context_text.rstrip() + context_section + "\n"
repo_context.write_text(context_text)
