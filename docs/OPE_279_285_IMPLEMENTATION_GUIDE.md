# Serviq OPE-279 through OPE-285 Implementation Guide

## Purpose

This document records the engineering work for Linear tickets OPE-279 through OPE-285 in plain language. It is intentionally detailed enough for a non-technical reader, a new intern, or a student to understand what changed, why the change was needed, how the code works, what safety rules were followed, and what the change enables next.

The cumulative `docs/SERVIQ_BUILD_GUIDE.md` remains the overall story of the Serviq product. This file is the focused implementation record for this seven-ticket MAS-1 workforce/organization batch.

---

# OPE-279 — Implement trusted RequestContext

## What problem this ticket solves

Every authenticated request eventually needs a trusted answer to questions such as:

- Which organization is this request operating inside?
- Who is acting?
- Is the actor a workforce user, customer, internal service, or platform operator?
- Which internal user or customer record has already been verified?
- Which permissions were resolved for this request?
- How strong is the identity proof for this actor?

Without one canonical object, different parts of Serviq could invent their own versions of this information. One service might trust a tenant ID from a header, another might use a request-body field, and another might use a database result. That creates an authorization risk because the same request could be interpreted differently by different services.

Architecture Contract C-1 therefore defines one trusted request context. OPE-279 turns that architecture contract into real Python code.

## Files changed

### `services/api/app/core/errors.py`

The file previously contained only a placeholder comment. OPE-279 adds two small typed internal exceptions:

- `AuthorizationContextError`, the common category for trusted auth/context failures;
- `MissingTenantContextError`, the specific fail-closed error used when tenant-scoped code is asked to proceed without trusted tenant context.

This does **not** add HTTP error handling. A later global exception-mapping ticket can decide how typed domain errors become HTTP responses. The important improvement now is that lower-level code can raise a stable error category instead of a generic `RuntimeError`, silently using a default tenant, or leaking implementation details.

### `services/api/app/core/auth.py`

This reserved authentication boundary now owns the canonical Contract C-1 model.

The implementation adds:

- `ActorType`, with only `tenant_user`, `customer`, `service`, and `platform_operator`;
- `AssuranceLevel`, with only `anonymous`, `verified`, `workforce`, and `platform`;
- `RequestActor`, the nested trusted actor identity;
- `RequestContext`, the immutable request-context model;
- `has_permission()`, a simple capability lookup helper;
- `require_tenant_id()`, a fail-closed tenant requirement helper.

The Python field names use normal snake_case, such as `request_id` and `tenant_id`. Pydantic aliases preserve the frozen camelCase Contract C-1 field names such as `requestId`, `tenantId`, `userId`, `customerId`, and `assuranceLevel` when serialized as the shared contract.

## Why the model is frozen

Once authentication and tenant resolution have produced trusted context, later application code should not be able to quietly rewrite it halfway through a request.

For example, this would be dangerous conceptually:

```text
Request starts in Tenant A
→ authorization succeeds
→ some helper mutates tenantId to Tenant B
→ repository query runs with Tenant B
```

The Pydantic models are therefore configured as frozen. The nested actor object is frozen too. Permissions are held as a tuple rather than a mutable list inside Python.

When serialized to JSON, the permission collection is still represented as the Contract C-1 array. The implementation deliberately preserves permission order and duplicates rather than inventing deduplication rules at this boundary.

## Why `require_tenant_id()` accepts a missing context

Contract C-1 itself always contains a tenant UUID. We did not weaken that contract by changing `tenantId` to nullable.

The helper accepts either a valid `RequestContext` or no resolved context at all. Tenant-scoped service code can therefore write one explicit guard:

```text
trusted context exists → return its tenant UUID
trusted context missing → raise MissingTenantContextError
```

There is no fallback to a default tenant, the first tenant in the database, `X-Tenant-ID`, or a request-body value.

## Tests added

`services/api/tests/test_request_context.py` verifies:

1. a valid workforce context with a tenant, internal user, and permissions;
2. exact camelCase Contract C-1 serialization;
3. a valid verified-customer context;
4. an anonymous customer context without an invented workforce user ID;
5. rejection of an unknown actor type;
6. rejection of an unknown assurance level;
7. fail-closed behavior when trusted tenant context is unavailable;
8. successful tenant extraction only from an actual trusted context;
9. immutability of the context after construction;
10. immutability of the nested actor identity.

## Security boundary

OPE-279 intentionally does **not** decide whether a token, cookie, header, or database row is trustworthy. It only defines the object that later verified resolution code is allowed to construct.

This ticket adds no:

- OIDC token validation;
- browser session behavior;
- membership database lookup;
- route guard;
- arbitrary tenant-header parsing;
- provider credential or secret field.

That narrow scope matters. A trusted context type is useful only when later code cannot bypass the trust-resolution process by filling it directly from unverified client input.

## What this improves

After OPE-279, later Serviq services no longer need to invent identity/tenant/permission parameter bundles. They can depend on one immutable, validated, architecture-owned model. This reduces contract drift, makes authorization code easier to test, and creates a clear place for tenant-scoped code to fail closed when trusted context is unavailable.

## What remains

The object is not yet constructed from a real login. Workforce OIDC validation, internal user mapping, membership/capability resolution, organization APIs, and invitation APIs are the next tickets in this batch. OPE-279 provides the trusted shape those later steps will eventually populate.
