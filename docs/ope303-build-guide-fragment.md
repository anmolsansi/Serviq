

## OPE-303 — Knowledge file uploads

**Implemented on branch:** `ope303`  
**Linear ticket:** `OPE-303`

OPE-303 extends the existing knowledge-source API so authorized business users can register approved PDF, Markdown, and plain-text files in addition to the URL and sitemap sources added by OPE-302. The same `POST /api/v1/knowledge-sources` path keeps JSON registration for URL-backed sources and accepts `multipart/form-data` for file-backed sources.

PDF accepts only `.pdf` with `application/pdf` up to 25 MiB. Markdown accepts `.md` or `.markdown` with `text/markdown` or `text/plain` up to 5 MiB. Plain text accepts `.txt` with `text/plain` up to 5 MiB. The server checks source type, extension, MIME type, actual byte count, and content sanity together. PDFs must begin with the PDF signature, while Markdown/text must be valid UTF-8 without NUL bytes. Uploaded content is untrusted data and is never executed.

File size is counted with bounded chunk reads. User filenames never become storage paths. Serviq generates source and object UUIDs and reuses the OPE-301 key format `tenants/{tenantId}/knowledge/{sourceId}/raw/{objectId}`. A sanitized basename can exist only as object metadata.

Serviq checks `knowledge.sources.manage`, validates the file, uploads the generated object outside a database transaction, and then creates a pending `knowledge_sources` row with `source_uri = NULL`, the generated `object_key`, and `sync_version = 0`. Storage failure creates no source row. A database failure after storage succeeds triggers deletion of the just-uploaded object so it cannot become an orphan.

Responses remain browser-safe and omit `objectKey`, bucket names, internal endpoints, credentials, and `createdBy`. Tests cover accepted file formats, size boundaries, MIME/extension mismatch, fake PDFs, invalid UTF-8, malicious filenames, authorization, tenant scoping, storage failure, and database-failure compensation.

OPE-303 does not parse documents, chunk or embed content, run synchronization workers, crawl URLs, add customer attachments, introduce presigned uploads, or change the frozen object-key layout.
