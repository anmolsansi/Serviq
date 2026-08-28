# CCR-007 — Knowledge upload quota accounting

## Status

Approved for V1.3.04B / OPE-309.

## Date

2026-08-28

## Change type

Additive internal database contract plus new stable quota-specific HTTP failures. Successful knowledge-source request/response contracts remain unchanged.

## Trigger

V1.3.04/V1.3.04A bound individual files and make raw-object cleanup durable but do not bound cumulative tenant bytes, source count, concurrent uploads, or per-user upload request rate.

ADR-019 selects PostgreSQL-authoritative source/byte/reservation accounting and the existing core Valkey boundary for the short-window user rate limit.

## Frozen limits

```text
knowledge upload attempts / tenant + workforce user: 6 / 60 seconds
active file upload reservations / tenant:           3
stored raw file bytes / tenant:                     1,073,741,824 (1 GiB)
total knowledge_sources rows / tenant:              100
reservation concurrency lease:                      10 minutes
```

## Existing contracts preserved

- `POST /api/v1/knowledge-sources` JSON and multipart successful shapes;
- V1.3.04 PDF/Markdown/text extension, MIME, signature, and size limits;
- V1.3.04A pre-PUT durable cleanup intent ordering;
- generated raw object-key layout;
- `knowledge.sources.manage` permission and server-owned tenant/actor context;
- source lifecycle values and parser/indexing scope;
- object-storage credentials/key secrecy.

## `knowledge_sources` additive column

Add:

```text
object_size_bytes bigint null
```

Rules:

- null for URL/sitemap sources;
- exact validated byte count for every newly created PDF/Markdown/text source;
- existing file rows may remain null immediately after migration and are reconciled through typed object-storage `HEAD` before a new file reservation for that tenant can be admitted;
- values are non-negative and no larger than the existing maximum single-file limit of 25 MiB.

## New table

Add:

```text
knowledge_upload_reservations
  id               uuid PK default uuidv7()
  tenant_id        uuid NOT NULL FK tenants(id) ON DELETE RESTRICT
  source_id        uuid NOT NULL
  reserved_bytes   bigint NOT NULL
  cleanup_id       uuid NULL
  lease_expires_at timestamptz NOT NULL
  created_at       timestamptz NOT NULL default now()
  updated_at       timestamptz NOT NULL default now()
```

Constraints:

- `(tenant_id, source_id)` unique;
- `cleanup_id` unique when non-null;
- `reserved_bytes BETWEEN 0 AND 26214400`;
- `lease_expires_at > created_at` on newly written rows through the service contract.

Indexes:

```text
(tenant_id, lease_expires_at)
(tenant_id, cleanup_id)
```

`source_id` is deliberately not a foreign key. The reservation is created before the user-visible source row exists. `cleanup_id` is deliberately not a database foreign key so migration ordering and V1.3.04A cleanup retention remain independent, but service/repository code binds only server-generated cleanup IDs in the same transaction that creates the cleanup intent.

## Authoritative quota calculation

Under a short lock on the trusted `tenants` row:

1. remove expired reservations where `cleanup_id IS NULL`;
2. count committed `knowledge_sources` rows;
3. sum committed `object_size_bytes` for file sources;
4. count/sum held reservations where `cleanup_id IS NOT NULL OR lease_expires_at > now()`;
5. count active concurrency where `lease_expires_at > now()`;
6. reject or insert one reservation atomically.

Source quota uses:

```text
committed source count + held reservation count
```

Byte quota uses:

```text
committed file bytes + held reserved bytes
```

Concurrency uses only non-expired leases. A linked reservation can therefore continue to charge byte/source quota after its concurrency lease expires.

## URL/sitemap source contract

Metadata-only source creation does not create an upload reservation. In its existing insertion transaction, it locks the tenant row and rejects when:

```text
committed source count + held file reservations >= 100
```

This prevents JSON registrations from bypassing the tenant source cap.

## Legacy byte reconciliation

A tenant with a file-backed `knowledge_sources` row whose `object_size_bytes` is null cannot receive a new file reservation until the missing size is established.

For each such row:

1. validate that `object_key` exactly matches the generated raw-key format for the trusted tenant and source IDs;
2. construct the typed raw object key;
3. call `ObjectStorage.head()` outside a database transaction;
4. persist only the non-negative returned `content_length` using tenant + source identity;
5. re-run authoritative quota calculation.

Malformed key, tenant/source mismatch, missing object, or storage failure returns `503 KNOWLEDGE_QUOTA_UNAVAILABLE`. No new PUT occurs.

## Reservation lifecycle

### Validated file, before PUT

Create the reservation after existing bounded validation and legacy-size reconciliation, but before the V1.3.04A cleanup intent and object PUT.

### Cleanup-intent transaction

Create `knowledge_upload_cleanups(status='prepared')` and bind the reservation's `cleanup_id` in the same transaction. If that transaction fails, no object PUT is permitted. The unlinked reservation may be explicitly released by the request path or expires after 10 minutes.

### Successful source transaction

In one transaction:

- insert file-backed `knowledge_sources` with `object_size_bytes`;
- mark cleanup `referenced`;
- delete the matching reservation.

### Confirmed cleanup success

Request-time or background cleanup deletes the reservation by trusted tenant + cleanup ID in the same transaction that marks cleanup `succeeded`.

### Unresolved cleanup

`prepared`, `pending`, and `exhausted` cleanup obligations retain their linked reservation for byte/source accounting. They do not consume concurrency once `lease_expires_at` passes.

## Request-rate contract

Use `services/api/app/core/rate_limits.py` and the configured platform Valkey URL. The staged ticket's `services/api/app/modules/providers/rate_limits.py` path is obsolete and must not be created.

For multipart upload requests, before `request.form()`:

```text
key = serviq:rate:knowledge-upload:user:{tenant_id}:{user_id}
limit = 6
window = 60 seconds
```

The Lua decision reads, rejects, or increments/sets TTL atomically. Valkey transport failure or malformed response fails closed.

## Public error contract

```text
429 KNOWLEDGE_UPLOAD_RATE_LIMITED
429 KNOWLEDGE_UPLOAD_CONCURRENCY_LIMITED
413 KNOWLEDGE_STORAGE_QUOTA_EXCEEDED
409 KNOWLEDGE_SOURCE_QUOTA_EXCEEDED
503 KNOWLEDGE_UPLOAD_LIMITER_UNAVAILABLE
503 KNOWLEDGE_QUOTA_UNAVAILABLE
```

429 responses include a bounded integer `Retry-After` header. No usage endpoint is added by this ticket.

## Security/privacy contract

- All quota keys use trusted server-owned tenant/user IDs.
- All database reads/writes are tenant-scoped.
- No quota failure exposes another tenant's usage.
- Logs/responses never include object keys, raw filenames, bodies, bucket names, storage endpoints, credentials, tokens, or secrets.
- Rejected quota/rate requests perform no object PUT and create no source row.

## Migration

Create Alembic revision `20260828_0011` after `20260824_0010`.

Upgrade:

1. add nullable `knowledge_sources.object_size_bytes` and its value check;
2. create `knowledge_upload_reservations`, constraints, and indexes.

Existing file rows are intentionally not backfilled in migration because object-storage network I/O is not permitted inside schema migration execution. Runtime reconciliation safely fills their sizes before future file admission.

Downgrade refuses while any reservation row exists, then drops the reservation table and `object_size_bytes` column/check.

## Rollback

Stop new upload traffic, resolve all reservations against source/cleanup state, verify the reservation table is empty, then downgrade. Rolling application code back while keeping the additive schema is safe but removes quota enforcement. Rolling back both code and schema reopens the abuse risk and loses committed byte accounting.