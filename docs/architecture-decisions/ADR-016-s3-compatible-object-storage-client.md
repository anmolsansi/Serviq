# ADR-016 — S3-compatible object-storage client and retry boundary for OPE-301

## Status

Accepted.

## Date

2026-08-19

## Context

OPE-301 implements Serviq's already-frozen S3-compatible object-storage boundary. The architecture and Docker Compose configuration already establish SeaweedFS as the local S3-compatible service, the object bucket convention, and the tenant-scoped object-key layouts. The repository did not yet name the Python S3 client library that the API should use.

That missing client choice is an implementation-level architecture decision because OPE-301 explicitly requires bounded retries, explicit network timeouts, local S3 compatibility, future AWS S3 compatibility, and stable application-owned errors. Picking a client ad hoc inside feature code would make those behaviors accidental and could couple Serviq to SeaweedFS-specific APIs.

## Decision

The Python API will use the AWS-maintained low-level `botocore` S3 client behind Serviq's own object-storage interface.

The Production V1 dependency range is:

```text
botocore >=1.42.89,<1.43
```

The exact patch release remains frozen by `services/api/uv.lock`.

Serviq will not add `boto3` for OPE-301. The ticket requires primitive S3 operations only, so boto3's higher-level resource and transfer layers do not add value to this boundary.

The adapter owns the following client configuration:

- S3 Signature Version 4;
- path-style S3 addressing so the same implementation works with the local SeaweedFS endpoint;
- 5-second connection timeout;
- 30-second read timeout;
- one total SDK attempt, which disables automatic retry amplification at this boundary;
- endpoint, bucket, access key, and secret key loaded only from `PlatformSettings`;
- `us-east-1` as the Production V1 signing region for the local S3-compatible endpoint.

The OPE-301 storage contract exposes:

```text
put_object
get_object
head
delete_object
```

`put_object` accepts bytes or a binary stream, content type, and string metadata. Metadata is copied at the boundary, metadata keys are normalized to lowercase, blank keys are rejected, and carriage-return/newline/NUL control characters are rejected from metadata keys and values.

`head` returns content type, content length, ETag when present, and user metadata without downloading the object body.

The adapter also exposes `exists` as a small convenience implemented on top of `head`; it is not a second storage discovery/listing mechanism.

The adapter does not expose the underlying botocore client to feature modules.

## Object-key ownership

Feature code must not supply arbitrary object-key strings.

OPE-301 provides typed key value objects and helper functions that accept trusted UUID identifiers and generate exactly these architecture-owned layouts:

```text
tenants/{tenantId}/knowledge/{sourceId}/raw/{objectId}
tenants/{tenantId}/knowledge/{sourceId}/normalized/{documentId}/{version}
tenants/{tenantId}/exports/{exportId}
tenants/{tenantId}/evaluation/{evaluationRunId}
```

The OPE-301 acceptance contract specifically consumes the raw knowledge helper. The additional architecture-owned normalized/export/evaluation helpers use the same typed UUID boundary so future callers do not need to invent full-key strings.

User-controlled filenames are not parameters to these helpers. A filename may be carried only as object/database metadata when a caller's architecture permits it, but it cannot influence the storage key.

All tenant-owned keys therefore begin with the tenant UUID chosen by trusted application code.

## Error boundary

Raw SDK exceptions, endpoint URLs, bucket internals, credentials, and upstream error messages are not application errors.

The adapter normalizes failures into stable Serviq errors:

```text
OBJECT_STORAGE_UNAVAILABLE
OBJECT_NOT_FOUND
```

`get_object` and `head` map a missing object to `OBJECT_NOT_FOUND`.

`exists` maps that normalized missing-object result to `False`.

`delete_object` is idempotent. Deleting an already-missing object succeeds.

A missing bucket is not treated as a missing object when the SDK provides the `NoSuchBucket` code; it remains an infrastructure/configuration failure and becomes `OBJECT_STORAGE_UNAVAILABLE`.

Other SDK/network failures become `OBJECT_STORAGE_UNAVAILABLE` without carrying the botocore exception text into the public exception message.

## Bucket convention

This ADR does not change the bucket convention already owned by Architecture:

```text
local:  serviq-local-objects
cloud:  serviq-{environment}-objects
```

OPE-301 aligns `.env.example` with the local Compose default so local application configuration and local infrastructure point at the same bucket.

## Production AWS S3

The Serviq application interface remains S3-compatible rather than SeaweedFS-specific. A production AWS S3 deployment can provide its production endpoint/credentials/bucket behind the same adapter.

Production-region discovery, workload identity, bucket policy, server-side encryption policy, retention, replication, and lifecycle policy are deployment/security concerns that are not invented by OPE-301. If a later production infrastructure ticket requires a configurable AWS signing region, that can extend settings without changing the application-facing object-storage interface or the key layouts frozen here.

## Explicit non-decisions

OPE-301 does not introduce or define:

- `ListObjects` or bucket browsing;
- presigned upload/download URLs;
- multipart-upload policy;
- ACLs;
- public object access;
- server-side encryption policy;
- retention/lifecycle policy;
- customer attachment storage;
- knowledge ingestion workers;
- export generation;
- filename-based keys;
- vendor-specific SeaweedFS calls.

These remain separate architecture/security/product decisions.

## Validation requirements

The implementation must prove:

- every implemented key helper matches its architecture-owned layout exactly;
- runtime rejection of non-UUID identifiers at the key boundary;
- tenant prefixes differ when the tenant UUID differs;
- malicious filenames including traversal text, slashes, Unicode separators, and very long names cannot alter the generated raw key;
- a filename can remain isolated in metadata without changing the key;
- bucket and endpoint come from configuration;
- explicit timeout and retry settings are present;
- put/get/head/delete behavior works through the adapter;
- head returns expected content length/content type/metadata;
- repeated delete is safe;
- missing reads/heads are normalized;
- error text does not reveal credentials or internal endpoint details;
- a real round trip succeeds against the local S3-compatible service in CI.

## Result

The client-library stop condition in OPE-301 is resolved without changing the product contract. Feature code depends on a small Serviq-owned interface, local development uses the existing S3-compatible service, and a later AWS S3 deployment can keep the same storage boundary and object-key rules.
