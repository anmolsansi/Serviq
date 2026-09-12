# ADR-029 — Pre-parser knowledge upload admission

## Status

Accepted for V1.3.04C.

This ADR tightens the upload-boundary section of ADR-017. ADR-017's public multipart contract, file types, type-specific byte limits, content checks, generated object-key rules, and ADR-018 cleanup durability remain unchanged.

## Date

2026-09-12

## Context

`POST /api/v1/knowledge-sources` accepts URL/sitemap JSON or one multipart file upload. Before V1.3.04C, the multipart path called Starlette `request.form(...)` first and only afterward entered `create_file_source(...)`, where Serviq validated file bytes and created the PostgreSQL upload reservation.

That ordering left two resource-control gaps:

1. source/concurrency quota was not authoritative until after multipart parsing could create a spooled temporary file;
2. Starlette's multipart `max_part_size` protects normal field data, but file payload bytes are written through `UploadFile` and require an explicit file/body boundary for Serviq's contract.

A `Content-Length` check alone is not an acceptable control because clients may omit it or stream/chunk a request. Reserving the maximum 25 MiB before parsing is also not acceptable because a valid small text upload could be rejected when the tenant has enough capacity for the actual upload but less than 25 MiB remaining.

## Decision

### 1. Reserve source/concurrency capacity before parsing

After the existing Valkey request-rate check, Serviq resolves workforce permission and reconciles any legacy unknown file sizes. It then creates an ordinary `knowledge_upload_reservations` row with:

- the real tenant ID;
- a generated source ID;
- `reserved_bytes = 0`;
- the existing ten-minute active-upload lease.

The row therefore consumes one held source slot and one active concurrency slot before multipart parsing starts, without prematurely charging byte quota.

The existing tenant-row lock remains the serialization boundary. No second limiter, table, queue, service, or cache-owned concurrency counter is introduced.

### 2. Bound streamed multipart input without trusting headers

The knowledge upload parser consumes `Request.stream()` through a counting generator. The complete raw multipart request is capped at:

`25 MiB + 1 MiB multipart overhead`

The parser also tracks file-part bytes while python-multipart is streaming callbacks and stops the request once the absolute V1 file ceiling of 25 MiB is crossed.

The extra raw-request allowance is only for multipart boundary/headers and the three small text fields. It does not increase the approved file maximum.

Starlette 1.6.0 is frozen in the API lockfile. V1.3.04C subclasses its `MultiPartParser` only to add the missing file-byte counter before the parser queues more file data for `UploadFile.write`. This is intentionally knowledge-local and covered by focused tests because the hook touches Starlette parser internals. A future Starlette upgrade must run those tests before merge.

### 3. Keep exact type-specific validation

After bounded parsing, existing validation still enforces:

- PDF: maximum 25 MiB;
- Markdown: maximum 5 MiB;
- text: maximum 5 MiB;
- extension and declared MIME agreement;
- PDF `%PDF-` signature;
- UTF-8/NUL checks for text formats;
- safe normalized filename handling.

The parser-level 25 MiB ceiling is an absolute resource guard. It does not replace the stricter 5 MiB Markdown/text rule.

### 4. Finalize exact byte quota under the tenant lock

Once `validate_upload(...)` has counted the exact file bytes, Serviq re-locks the tenant and the specific admission reservation.

Finalization requires that the reservation:

- belongs to the current tenant;
- matches the generated source ID;
- is still unlinked to cleanup;
- still has `reserved_bytes = 0`;
- has an unexpired active-upload lease.

The exact validated byte count then replaces zero under the same quota lock. The existing committed/held-byte calculation decides whether the upload still fits below the 1 GiB tenant storage ceiling.

This does not re-add a source or concurrency hold. The original admission row already represents both.

### 5. Preserve the durable object-write boundary

Only after exact-byte reservation succeeds may the existing ADR-018 flow continue:

1. create durable cleanup intent;
2. bind the reservation to cleanup;
3. commit that transaction;
4. PUT the raw object;
5. commit tenant-visible source state and cleanup `referenced` transition;
6. release the reservation.

No object-store PUT is allowed before the cleanup-binding transaction commits.

### 6. Release pre-cleanup failures

If multipart parsing, field validation, permission re-check, file validation, or exact-byte finalization fails, the still-unlinked admission reservation is released best-effort.

If the process or database becomes unavailable during that release, the existing ten-minute unlinked lease is the crash-safety fallback.

Once the service begins the cleanup-bound flow, the route must not delete the reservation directly. ADR-018/V1.3.04D owns failures from that point onward.

### 7. Close multipart resources on every path

The parser is exposed through an async context manager. Successfully parsed `FormData` is always closed on exit, which closes `UploadFile` temporary resources. Parser errors are also required to close any temporary files already created before re-raising a safe validation/size error.

## Error contract

Public error shapes remain unchanged:

- `413 UPLOAD_TOO_LARGE` for the absolute/type-specific upload size boundary;
- `413 KNOWLEDGE_STORAGE_QUOTA_EXCEEDED` for tenant byte capacity;
- `429 KNOWLEDGE_UPLOAD_CONCURRENCY_LIMITED` for the active upload cap;
- `409 KNOWLEDGE_SOURCE_QUOTA_EXCEEDED` for source capacity;
- `422 VALIDATION_ERROR` for malformed multipart fields/content;
- `503 KNOWLEDGE_QUOTA_UNAVAILABLE` when authoritative quota state cannot be proven;
- `503 OBJECT_STORAGE_UNAVAILABLE` for object-storage failures after admission.

No parser exception text, object key, credential, endpoint, filename contents, or request body is reflected to the caller.

## Alternatives rejected

### Header-only size admission

Rejected. `Content-Length` is optional/untrusted and does not protect streamed requests.

### Reserve 25 MiB before parsing

Rejected. It preserves concurrency but creates false byte-quota rejection for smaller valid uploads.

### Separate Valkey concurrency semaphore

Rejected. PostgreSQL is already the authoritative reservation/cleanup boundary. A second counter would require reconciliation and could disagree after crashes.

### New upload service or presigned multipart workflow

Rejected for V1.3.04C. It changes the external contract and architecture far beyond the audit finding.

## Operational notes

- A client that takes longer than the ten-minute admission lease to finish parsing is rejected during exact-byte finalization rather than silently proceeding without active admission.
- The absolute raw request limit is intentionally slightly larger than the maximum file so valid multipart framing can fit.
- Parser internals are version-sensitive. The focused multipart tests are upgrade gates for Starlette.
- Existing V1.3.04D worker cleanup remains unchanged because pre-parser failures have no object and therefore no cleanup obligation.

## Rollback

Revert V1.3.04C code and this ADR together. No database migration rollback is required because the implementation reuses the existing reservation schema. Rolling back reopens the audit finding, so it should only be used to recover from a production regression while a corrected admission boundary is prepared.
