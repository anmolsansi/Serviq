# Knowledge Upload Quota and Abuse-Control Runbook

## Purpose

This runbook covers the V1.3.04B controls that prevent one tenant or workforce user from exhausting knowledge-upload request capacity, source rows, or raw object storage.

Architecture details live in `docs/architecture-decisions/ADR-019-knowledge-upload-quota-and-abuse-controls.md`. The additive persistence and API contract lives in `docs/contract-changes/CCR-007-knowledge-upload-quota-accounting.md`.

## Frozen V1 limits

| Control | Limit | Authority |
|---|---:|---|
| Multipart upload attempts | 6 per 60 seconds per tenant + workforce user | Valkey |
| Active file uploads | 3 per tenant | PostgreSQL reservation lease |
| Stored raw file bytes | 1 GiB per tenant | PostgreSQL committed bytes + held reservations |
| Total knowledge sources | 100 per tenant | PostgreSQL committed rows + held file reservations |
| Crash-safety upload lease | 10 minutes | PostgreSQL |

These are V1 hard platform limits, not billing entitlements.

## Public failures

| HTTP | Code | Meaning | Operator action |
|---:|---|---|---|
| 429 | `KNOWLEDGE_UPLOAD_RATE_LIMITED` | User exceeded 6 upload attempts in 60 seconds | Usually none. Confirm abusive/retry patterns if sustained. |
| 429 | `KNOWLEDGE_UPLOAD_CONCURRENCY_LIMITED` | Tenant already has 3 active upload leases | Check active leases and stalled requests. |
| 413 | `KNOWLEDGE_STORAGE_QUOTA_EXCEEDED` | Committed + held bytes would exceed 1 GiB | Inspect committed bytes and unresolved cleanup reservations. |
| 409 | `KNOWLEDGE_SOURCE_QUOTA_EXCEEDED` | Committed + held sources reached 100 | Inspect source count and unresolved cleanup reservations. |
| 503 | `KNOWLEDGE_UPLOAD_LIMITER_UNAVAILABLE` | Valkey could not enforce upload request rate | Restore Valkey. Uploads intentionally fail closed. |
| 503 | `KNOWLEDGE_QUOTA_UNAVAILABLE` | Authoritative byte accounting/reconciliation is unavailable | Inspect legacy file metadata and object-storage health. |

Responses never expose object keys, bucket credentials, filenames, content, or foreign-tenant usage.

## How admission works

For a multipart upload:

1. Trusted tenant and workforce-user context is resolved by the existing API boundary.
2. Valkey atomically consumes the per-user upload-attempt counter before multipart parsing.
3. Existing V1 file validation checks extension, MIME/signature, and bounded size.
4. Legacy file rows with unknown `object_size_bytes` are reconciled with typed object-storage `HEAD` calls outside a database transaction.
5. PostgreSQL locks the tenant row briefly, removes expired unlinked reservations, calculates committed + held usage, and either rejects or inserts one reservation.
6. The V1.3.04A cleanup intent is created and the reservation is bound to it in one transaction.
7. Only after that transaction commits may the raw object PUT occur.
8. Successful source persistence stores the exact byte count and releases the reservation in the same transaction that marks cleanup `referenced`.
9. Confirmed object cleanup releases the reservation in the same transaction that marks cleanup `succeeded`.

A handled failed request ends its active concurrency lease immediately, but its linked source/byte hold remains until cleanup is confirmed. A crashed request can occupy an active slot for at most 10 minutes.

## Safe PostgreSQL diagnostics

Use tenant IDs and aggregate counts only. Do not copy object keys or source content into tickets, chat, or logs.

### Tenant committed usage

```sql
SELECT
  count(*) AS committed_sources,
  coalesce(sum(object_size_bytes), 0) AS committed_file_bytes
FROM knowledge_sources
WHERE tenant_id = '<tenant-uuid>';
```

### Tenant held reservation usage

```sql
SELECT
  count(*) AS held_sources,
  coalesce(sum(reserved_bytes), 0) AS held_bytes
FROM knowledge_upload_reservations
WHERE tenant_id = '<tenant-uuid>'
  AND (cleanup_id IS NOT NULL OR lease_expires_at > now());
```

### Tenant active concurrency

```sql
SELECT
  count(*) AS active_uploads,
  min(lease_expires_at) AS earliest_lease_expiry
FROM knowledge_upload_reservations
WHERE tenant_id = '<tenant-uuid>'
  AND lease_expires_at > now();
```

### Platform reservation count

```sql
SELECT count(*) AS reservation_count
FROM knowledge_upload_reservations;
```

### Cleanup status counts

```sql
SELECT status, count(*)
FROM knowledge_upload_cleanups
GROUP BY status
ORDER BY status;
```

An `exhausted` cleanup with a linked reservation intentionally continues charging source/byte quota. Do not delete that reservation just to unblock a tenant. First establish whether the raw object exists and follow the approved cleanup/recovery contract.

## Rate-limit diagnosis

The Valkey key format is:

```text
serviq:rate:knowledge-upload:user:{tenant_id}:{user_id}
```

The value is a short-lived request count with a 60-second TTL. Do not return it through a public API. Avoid manual deletion during normal operation because it weakens abuse controls.

If Valkey is unavailable, the upload endpoint returns `503 KNOWLEDGE_UPLOAD_LIMITER_UNAVAILABLE` before multipart parsing or object PUT. Restore Valkey connectivity rather than bypassing the limiter.

## Legacy size reconciliation failure

`KNOWLEDGE_QUOTA_UNAVAILABLE` can indicate that an existing file-backed source has a null `object_size_bytes` and Serviq could not establish the size safely.

Check:

1. the source row has a generated V1 raw object key, not an arbitrary path;
2. the key's tenant/source UUIDs match the row;
3. S3-compatible storage is reachable;
4. the object exists;
5. `HEAD` returns a non-negative size no larger than the V1 25 MiB single-file maximum.

Do not manually enter a guessed byte count. Either restore storage metadata access or resolve the inconsistent source/object state through an explicit data-repair decision.

## Reservation recovery rules

### Expired and unlinked

An expired reservation with `cleanup_id IS NULL` is safe for automatic reclamation. V1.3.04A forbids raw-object PUT before cleanup intent commit, so no durable object can validly exist for an unlinked pre-PUT reservation.

### Linked and unresolved

A linked reservation attached to `prepared`, `pending`, or `exhausted` cleanup remains charged for source/byte quota. Its active concurrency lease may already be expired. This is intentional.

### Referenced or succeeded cleanup with stale reservation

The reconciler self-heals a stale reservation when it observes cleanup already `referenced` or `succeeded`. If one persists after replay, investigate transaction/DB failures before manual mutation.

## Verification commands

### Fast API quality checks

```bash
cd services/api
uv sync --frozen
uv run ruff check app tests
uv run mypy app tests
uv run pytest
```

### Real PostgreSQL integration

```bash
export SERVIQ_DATABASE_INTEGRATION=1
uv run alembic upgrade head
uv run pytest tests/integration/test_knowledge_quota_postgres.py \
  tests/integration/test_knowledge_quota_api.py
```

### Real Valkey

Start the repository Valkey service, then:

```bash
export SERVIQ_VALKEY_INTEGRATION=1
uv run pytest tests/integration/test_knowledge_upload_rate_limit_valkey.py
```

### Real S3-compatible storage and reconciliation

Start `object-storage` from `infra/docker/compose.yml`, use the repository local storage settings, then:

```bash
export SERVIQ_KNOWLEDGE_QUOTA_REAL_STACK=1
uv run pytest tests/integration/test_knowledge_quota_real_stack.py
```

CI automates the real PostgreSQL + Valkey + S3-compatible stack in `.github/workflows/knowledge-quota-integration.yml`.

## Migration and rollback

Migration `20260828_0011` is additive.

Before downgrading below it:

1. stop new V1.3.04B upload traffic;
2. resolve every reservation against its source/cleanup outcome;
3. verify `SELECT count(*) FROM knowledge_upload_reservations` returns zero;
4. run the downgrade;
5. understand that `object_size_bytes` is removed and legacy sizes must be reconciled again if V1.3.04B is later re-enabled.

The migration refuses to downgrade while any reservation exists.

Rolling application code back while leaving the additive schema in place is structurally safe, but quota enforcement disappears and the original abuse risk returns.

## Escalation conditions

Escalate rather than improvising when:

- a linked reservation has no matching cleanup/source explanation;
- an object key does not match the generated tenant/source identity;
- a cleanup is `exhausted` and object presence cannot be established;
- storage metadata conflicts with committed `object_size_bytes`;
- a tenant appears above a frozen hard limit without a reservation/legacy explanation;
- a request bypassed tenant scoping, permission checks, or pre-PUT reservation ordering;
- operators want to raise limits, add overrides, or introduce paid overages.

Limit changes, override policy, billing, and lifecycle automation require a new architecture/contract decision.