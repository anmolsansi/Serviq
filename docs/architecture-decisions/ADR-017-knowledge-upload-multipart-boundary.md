# ADR-017 — Knowledge upload multipart boundary

## Status

Accepted, with the **Storage and transaction boundary** superseded by ADR-018 for V1.3.04A. The multipart dependency, validation, upload limits, and object-key rules below remain accepted.

## Date

2026-08-19

## Context

OPE-303 adds file-backed knowledge-source creation to the architecture-owned `POST /api/v1/knowledge-sources` path. The existing FastAPI service has no approved multipart parser dependency, while normal FastAPI `File`/`Form`/`UploadFile` handling requires `python-multipart`.

The ticket requires bounded upload handling and explicitly says not to invent an unapproved upload dependency. This ADR resolves that implementation-level dependency without changing the frozen product contract.

## Decision

Serviq approves `python-multipart >=0.0.20,<1` for the API service. The exact resolved patch version is frozen by `services/api/uv.lock`.

The existing route keeps one path with content-type dispatch:

- `application/json` continues the OPE-302 URL/sitemap metadata-registration flow.
- `multipart/form-data` handles OPE-303 file-backed knowledge-source creation.

The multipart request contains exactly these logical fields:

- `sourceType`: `pdf`, `markdown`, or `text`;
- `name`: trimmed, length 1–160;
- `accessScope`: `customer` or `internal`;
- `file`: exactly one uploaded file.

Unknown fields and duplicate logical fields are rejected.

## Upload boundary

FastAPI/Starlette may spool an uploaded part to a temporary file, but application code must still count file bytes with bounded chunk reads and stop as soon as the V1 type-specific limit is exceeded. The application must not call an unbounded file read.

The V1 limits remain unchanged:

- PDF `.pdf`, `application/pdf`, maximum 25 MiB;
- Markdown `.md`/`.markdown`, `text/markdown` or `text/plain`, maximum 5 MiB;
- text `.txt`, `text/plain`, maximum 5 MiB.

Extension, MIME, declared source type, and content sanity must agree. PDF content must begin with the PDF signature. Markdown/text must be valid UTF-8 data and must not contain NUL bytes. Uploaded content is never executed.

## Storage and transaction boundary

**Superseded by ADR-018.** The original OPE-303 implementation authorized first, validated the upload, stored the generated raw object, then created the pending database row in a separate transaction with best-effort deletion on database failure.

V1.3.04A now commits an internal `knowledge_upload_cleanups` intent before the object PUT. A successful source insert and cleanup `referenced` transition commit together after the PUT. Failed uploads still create no tenant-visible source row, while the internal cleanup state can drive bounded idempotent deletion. See ADR-018 and CCR-006 for the frozen failure, retry, tenant, retention, and rollback semantics.

## Explicit non-decisions

This ADR does not add presigned uploads, S3 multipart-upload APIs, customer attachments, parsers, chunking, embedding/index workers, filename-based keys, arbitrary filesystem destinations, or synchronous URL crawling.
