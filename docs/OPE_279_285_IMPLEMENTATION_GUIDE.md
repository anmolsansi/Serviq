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


---

# OPE-280 — Implement workforce OIDC token validation

## What problem this ticket solves

A JWT is only a signed container of claims. Serviq must not treat the text inside a workforce token as trusted simply because the token looks structurally correct. Before identity data is allowed into later user/membership code, Serviq must prove that the configured identity provider signed the token, that the token was meant for Serviq, that it has not expired, and that it identifies a real subject.

OPE-280 creates that cryptographic trust boundary.

## Architecture decision made before coding

The ticket contained an explicit stop condition because the API scaffold did not have an approved JOSE/JWT library. Instead of writing token cryptography by hand or quietly adding a framework, OPE-280 records ADR-003.

ADR-003 freezes these V1 choices:

- `joserfc` performs JWT/JWK verification;
- the already-used `httpx` client becomes a runtime dependency for OIDC discovery/JWKS retrieval;
- only `RS256` workforce signatures are accepted;
- issuer discovery and JWKS are cached for at most five minutes;
- staging/production metadata must use HTTPS;
- local/test HTTP is allowed only for loopback development hosts.

The dependency lockfile was regenerated after the architecture decision, so CI installs the exact resolved dependency graph instead of resolving a different set on every machine.

## Stable authentication failure

`services/api/app/core/errors.py` now includes `AuthenticationError` with stable code `UNAUTHENTICATED` and the generic message `Authentication failed.`

The reason for a generic boundary error is security. A caller should not receive raw JOSE messages that reveal whether a key ID was found, how a signature failed, or which internal metadata request errored. Detailed provider/library text can also accidentally contain untrusted token fragments.

## Verified identity DTO

`VerifiedWorkforceIdentity` is deliberately small. It contains only:

- exact configured issuer;
- verified subject;
- normalized email when present;
- strict email-verification boolean;
- optional display name derived from `name` or `preferred_username`.

It does **not** contain arbitrary token claims. In particular, token-supplied tenant IDs and permissions are ignored even if present in a correctly signed token. Serviq's tenant membership and capabilities must come from its own database in OPE-282.

## Discovery and JWKS cache

`OidcMetadataCache` starts from the configured issuer. It builds the standard discovery URL itself instead of reading an issuer URL from the token.

On a cold cache it:

1. fetches discovery metadata;
2. verifies discovery repeats the exact configured issuer;
3. extracts `jwks_uri`;
4. validates the metadata URL policy;
5. fetches the public key set;
6. imports the JWKS into a typed `KeySet`;
7. stores it for a bounded five-minute lifetime.

An async lock makes this single-flight. If many requests arrive at the same moment while the cache is empty, one refresh runs and the others reuse the result.

The HTTP fetch path uses a five-second timeout, does not follow redirects, and rejects OIDC JSON responses larger than one megabyte.

## Token validation sequence

`WorkforceOidcValidator.validate()` performs the following sequence:

1. reject blank input;
2. obtain the trusted issuer key set from the bounded cache;
3. cryptographically decode/verify using only `RS256`;
4. require exact configured `iss`;
5. require exact configured `aud`;
6. require and validate `exp`;
7. require `sub`;
8. separately reject a blank subject;
9. normalize only the approved identity profile fields;
10. return the frozen verified identity DTO.

Any metadata, network, JOSE, signature, claims, or malformed-token failure becomes `AuthenticationError` without returning the raw dependency exception.

## Email handling

Email is profile data, not the primary identity key. If a string email claim exists, it is trimmed and case-folded. `email_verified` is true only when the claim is literally boolean `true`.

An unverified email can therefore be carried as profile information while remaining explicitly unverified. Later invitation acceptance code must not treat an unverified email as proof that the user owns an invitation address.

## Tests added

`services/api/tests/test_workforce_oidc.py` uses locally generated deterministic-purpose RSA/JWK fixtures and a fake discovery/JWKS fetcher. No external identity provider is needed for automated tests.

Coverage includes:

- valid token success;
- exact normalized identity output;
- proof that token tenant/permission claims are discarded;
- wrong issuer;
- wrong audience;
- expired token;
- missing subject;
- blank subject;
- invalid signature;
- malformed token;
- discovery issuer mismatch;
- two validations within cache lifetime producing only one discovery + one JWKS fetch;
- unverified email behavior;
- raw token absent from error text and captured logs.

## Security review

`docs/security-reviews/OPE-280-workforce-oidc-validation.md` records the explicit security review for this trust boundary. It covers signature bypass, algorithm confusion, issuer/audience confusion, token claim injection, metadata SSRF/redirect behavior, oversized metadata, dependency amplification, token leakage, and residual key-rotation risk.

The final PR must still pass the permanent OPE-272 security workflow before merge. The review document is not a substitute for CodeQL, Gitleaks, Trivy, and dependency auditing.

## What this improves

After OPE-280, downstream code can ask one component to validate a workforce JWT and receive either a small verified identity or one safe authentication failure. No later service needs to parse JWT claims independently, choose its own algorithm policy, fetch JWKS on every request, or risk copying tenant/permission claims from the identity provider into Serviq authorization.

## What remains

OPE-280 does not create browser sessions, persist users, resolve memberships, construct RequestContext, or expose login routes. OPE-281 consumes the verified identity DTO to create/reuse Serviq's internal user identity. OPE-282 then resolves tenant membership and capabilities from PostgreSQL.


---

# OPE-281 — Upsert internal user from verified OIDC identity

## What problem this ticket solves

OIDC gives Serviq a verified external identity such as `(issuer, subject)`, but the rest of Serviq should not use that external pair as a foreign key everywhere. Memberships, role assignments, audit records, ownership, and future workflows need one stable internal `users.id`.

OPE-281 creates the bridge between those two identity systems.

The primary identity key remains the exact `(oidc_issuer, oidc_subject)` pair. Email is deliberately **not** used as the identity key because email can change and the same email string is not a cryptographic identity guarantee.

## Existing database contract reused

This ticket does not add a migration. OPE-277 already created the `users` table with:

- UUID primary key;
- `oidc_issuer`;
- `oidc_subject`;
- non-null email;
- non-null display name;
- `active|disabled` status;
- unique `(oidc_issuer, oidc_subject)` constraint.

`services/api/app/modules/workforce/models.py` maps that existing table into SQLAlchemy. The mapping exists so repository/service code can use the frozen schema without creating a second database representation.

## Layering added

The new workforce module follows the repository architecture:

```text
models.py      -> existing database table mapping
repository.py  -> exact persistence queries
service.py     -> business rules and transaction ownership
schemas.py     -> stable internal result DTO
errors.py      -> typed fail-closed domain errors
```

No routes or memberships are introduced in this ticket.

## Internal user DTO

`InternalWorkforceUser` contains only the stable internal fields downstream services need: user UUID, OIDC issuer/subject, email, display name, and status. It is frozen to prevent a caller from rewriting resolved identity after the service returns it.

## Exact identity lookup

`find_user_by_oidc_identity()` performs one tenant-independent lookup using both issuer and subject. It never searches by email and never picks the first matching-looking user.

This also means the same subject string under a different issuer is treated as a different external identity, matching the database unique constraint.

## First-login transaction

`upsert_verified_workforce_user()` accepts only the `VerifiedWorkforceIdentity` DTO produced by OPE-280. A raw JWT cannot enter the persistence service.

The service owns one transaction. It first checks whether the exact identity already exists.

If it does not, it stages an active user and flushes it inside a database savepoint. The savepoint matters because two servers can receive the first login for the same person at nearly the same time.

The PostgreSQL unique constraint is the final concurrency authority. If both requests try to insert:

1. one transaction wins and creates the row;
2. the losing insert raises a uniqueness error inside the savepoint;
3. only the savepoint is rolled back, not the entire service transaction;
4. the loser re-reads the winning `(issuer, subject)` row;
5. both callers receive the same stable internal user UUID.

If the integrity error did not produce a matching winner, the service re-raises it instead of hiding an unrelated database problem.

## Repeated login and safe profile synchronization

When the identity already exists and is active, the same UUID is returned.

The verified identity may update safe profile fields:

- a changed normalized email replaces the stored profile email;
- a supplied changed display name replaces the stored display name;
- if a later token omits display name, the existing display name is preserved.

New users require email because the frozen `users.email` database column is non-null. If the verified identity has no email, the service fails with `WORKFORCE_IDENTITY_PROFILE_INVALID` rather than inventing an address or writing invalid data. For a new user whose verified DTO has email but no display name, the email becomes the initial display label.

## Disabled users fail closed

A verified OIDC token does not override Serviq's internal account state.

If the matching Serviq user has status `disabled`, the service raises `WORKFORCE_USER_DISABLED`. It never silently changes the row back to active. This keeps Serviq's administrative disable control authoritative even when the upstream identity provider still considers the identity valid.

## PostgreSQL integration tests

`tests/integration/test_workforce_user_upsert.py` runs against the real PostgreSQL migration head and verifies:

- first login creates a user;
- repeat login returns the same UUID;
- safe email/display-name synchronization;
- same subject under a second issuer creates a separate identity;
- disabled users fail closed and remain disabled;
- two concurrent first-login calls result in exactly one row and the same returned UUID;
- missing verified email fails before a database write.

The tests use unique OPE-281 issuer prefixes and clean their rows after each scenario so they do not pollute later integration tests.

## What this improves

After OPE-281, downstream Serviq code has one dependable internal workforce identifier. The user identity is stable across repeated logins, concurrent login races cannot create duplicate users, and a valid OIDC token cannot silently re-enable an internally disabled account.

## What remains

This ticket does not choose a tenant, create a membership, resolve permissions, create a session, or expose an API route. OPE-282 takes the stable internal `users.id` plus a trusted tenant ID and resolves the active membership/capability set.
