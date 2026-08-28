# ADR-019 — Knowledge upload quota and abuse controls

## Status

Accepted for V1.3.04B / OPE-309.

## Date

2026-08-28

## Context

V1.3.04 and V1.3.04A make individual file uploads bounded and cross-store cleanup durable, but an authorized or compromised user can still send repeated uploads, keep many uploads in flight, create unbounded knowledge-source rows, or consume unbounded tenant object storage over time.

The staged V1.3.04B ticket also referenced `services/api/app/modules/providers/rate_limits.py`. That path does not exist on current `main`. The repository's architecture and implemented provider connectivity path already own shared Valkey-backed request limits at `services/api/app/core/rate_limits.py`. V1.3.04B therefore extends the existing core boundary rather than creating a provider-owned parallel abstraction.

This decision must preserve the V1.3.04A invariant that PostgreSQL knows every possible raw object before object storage PUT is attempted.

## Frozen V1 limits

- Multipart knowledge upload attempts: **6 per 60 seconds per tenant + workforce user**.
- Concurrent file-upload leases: **3 per tenant**.
- Stored raw file bytes: **1 GiB (1,073,741,824 bytes) per tenant**.
- Knowledge sources: **100 total `knowledge_sources` rows per tenant**, including URL, sitemap, PDF, Markdown, and text.
- File-upload reservation lease: **10 minutes**.

These are V1 platform hard limits, not billing-plan entitlements. V1.10.05 may later expose general platform rate-policy configuration, but widening these knowledge limits requires explicit contract change control.

## Options considered

### Option A — Keep only per-file limits

This preserves the current code but does not address repeated requests, concurrency, total objects, or cumulative stored bytes.

Rejected because it does not solve the abuse case.

### Option B — Keep all counters only in Valkey

Valkey can atomically enforce short-window counters and concurrency cheaply.

Rejected for source-count and stored-byte quota because cache loss, eviction, failover, or counter drift could admit durable PostgreSQL/S3 state that exceeds the real quota. Reconstructing authoritative byte usage from Valkey is also not reliable.

### Option C — Query S3 object listings for every quota decision

Object storage could be treated as the byte source of truth.

Rejected because the approved storage contract intentionally has no list operation, listing adds pagination/eventual-consistency/cost concerns, and it would weaken the existing PostgreSQL-owned consistency boundary.

### Option D — PostgreSQL authoritative reservations plus Valkey request rate

Use Valkey only for the short-window per-user request rate. Use PostgreSQL for source count, committed byte accounting, and short-lived upload reservations. Serialize quota decisions by briefly locking the tenant row. Reconcile legacy file sizes through the typed object-storage `HEAD` boundary outside a database transaction before reserving new capacity.

Selected.

## Decision

### Request-rate boundary

Multipart upload attempts consume one Valkey counter keyed by trusted tenant ID and workforce user ID before multipart parsing. The frozen window is six attempts per 60 seconds.

If Valkey is unavailable or returns an invalid result, Serviq fails closed with `503 KNOWLEDGE_UPLOAD_LIMITER_UNAVAILABLE`. The request does not parse the multipart body and performs no object PUT.

JSON URL/sitemap source creation does not consume this upload-rate counter. General API rate policy remains V1.10.05 scope.

### Authoritative quota boundary

PostgreSQL owns:

- total knowledge-source count;
- committed raw file bytes;
- in-flight upload reservations;
- durable association between an upload reservation and a V1.3.04A cleanup obligation.

Before a quota calculation, the service briefly locks the trusted tenant row with `FOR UPDATE`. While that lock is held it removes expired reservations that were never linked to a cleanup intent, calculates committed + held usage, and creates the new reservation if all limits pass. No object-storage operation occurs while the database transaction is open.

This serializes reservations across API processes without introducing a new coordinator service.

### Reservation semantics

`knowledge_upload_reservations` represents capacity reserved before raw-object PUT.

A new validated file reserves:

- one source slot;
- its exact validated byte count;
- one active-concurrency slot until `lease_expires_at`, initially 10 minutes after reservation.

Before PUT, the reservation is linked to the durable `knowledge_upload_cleanups` row in the same PostgreSQL transaction that creates the cleanup intent.

On successful source persistence, the source row stores the exact byte count, cleanup becomes `referenced`, and the reservation is deleted in the same transaction.

On confirmed cleanup success, request-time or background reconciliation deletes the linked reservation in the same transaction that records cleanup success.

A reservation linked to a `prepared`, `pending`, or `exhausted` cleanup continues to count against byte and source quota even after its 10-minute concurrency lease expires. This intentionally fails closed: a possible orphan object cannot become free quota merely because the request or cleanup lease expired. An expired linked reservation no longer counts as active concurrency, preventing a permanently exhausted cleanup from consuming one of the three in-flight slots forever.

An expired **unlinked** reservation can be deleted on the next quota operation because no cleanup intent was committed and V1.3.04A forbids object PUT before that intent exists.

### Source-count behavior

The 100-source limit applies to all knowledge-source types. URL/sitemap creation locks the tenant row and checks the committed source count plus held file reservations before inserting the metadata row. File upload reservations check the same combined source usage before reserving one slot.

This prevents JSON registration from bypassing the source-count limit while keeping file-specific byte/concurrency behavior scoped to multipart uploads.

### Committed byte accounting

V1.3.04B adds nullable `knowledge_sources.object_size_bytes`.

- New PDF/Markdown/text sources always persist the byte count produced by existing bounded validation.
- URL/sitemap sources keep the value null.
- Existing file rows may initially be null after migration.

Before a tenant can reserve a new file upload, any legacy file rows with unknown size are reconciled using the existing generated raw-key shape and typed `ObjectStorage.head()` metadata call. Storage calls happen outside database transactions. The service then writes the measured sizes back with tenant-scoped updates.

If a legacy key is malformed, belongs to a different tenant/source identity, or storage metadata cannot be obtained, authoritative usage is unknown. The upload fails closed with `503 KNOWLEDGE_QUOTA_UNAVAILABLE` before any new raw-object PUT.

## Stable public errors

- `429 KNOWLEDGE_UPLOAD_RATE_LIMITED`, with `Retry-After`.
- `429 KNOWLEDGE_UPLOAD_CONCURRENCY_LIMITED`, with bounded `Retry-After`.
- `413 KNOWLEDGE_STORAGE_QUOTA_EXCEEDED`.
- `409 KNOWLEDGE_SOURCE_QUOTA_EXCEEDED`.
- `503 KNOWLEDGE_UPLOAD_LIMITER_UNAVAILABLE`.
- `503 KNOWLEDGE_QUOTA_UNAVAILABLE`.

Errors expose only stable codes/messages and retry timing where applicable. They never expose object keys, bucket names, storage endpoints, credentials, raw filenames, file bodies, foreign-tenant usage, tokens, or provider internals.

## Race and failure behavior

The tenant-row lock gives exact source/byte/concurrency admission across cooperating API processes. There is no allowed quota overshoot from concurrent reservations.

A process can crash after reservation but before cleanup-intent commit. That unlinked reservation can over-count usage for at most the 10-minute lease and is reclaimed on later quota activity. This is an availability-only tolerance, not a quota overshoot.

A process can crash after the reservation is linked to a cleanup intent. The linked reservation remains charged until source ownership commits or cleanup is confirmed. This matches the durable cleanup obligation and cannot silently free capacity while a raw object may exist.

## Tenant and authorization boundary

- Tenant and workforce user IDs remain server-owned trusted context.
- Existing `knowledge.sources.manage` remains required.
- Reservation, source, and cleanup repository operations are tenant-scoped.
- A foreign tenant cannot query usage, reserve capacity, release a reservation, or trigger storage I/O for another tenant.
- Platform overrides are not introduced by this ticket.

## Observability

The API currently has no production Python metrics exporter. V1.3.04B therefore uses durable PostgreSQL count/usage queries as the authoritative metric source and bounded structured log events for admission/rejection/reconciliation outcomes.

Safe operational evidence may include tenant ID, reservation ID, cleanup ID, counts, bytes, limit code, retry seconds, and timings. It must not include object keys or user content.

## Rollback

The migration is additive. Application rollback below V1.3.04B removes enforcement and therefore reopens the abuse risk.

Before downgrading the schema:

1. stop new V1.3.04B upload traffic;
2. resolve or explicitly clear all upload reservations after verifying their cleanup/source outcome;
3. confirm `knowledge_upload_reservations` is empty;
4. downgrade the migration;
5. understand that committed `object_size_bytes` accounting will be removed and must be reconciled again if V1.3.04B is later re-enabled.

The migration refuses downgrade while any reservation exists.

## Compatibility

The successful `POST /api/v1/knowledge-sources` request/response shapes, file-type limits, generated object-key layout, permissions, and source lifecycle values remain unchanged. This ticket adds only quota-specific failure responses and internal/additive persistence required to enforce them.