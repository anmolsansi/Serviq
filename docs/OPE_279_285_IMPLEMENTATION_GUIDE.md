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


---

# OPE-282 — Resolve tenant membership and effective capabilities

## What problem this ticket solves

A workforce user can belong to more than one Serviq organization. A stable internal `users.id` therefore does not tell Serviq what that user may do inside a particular tenant. OPE-282 resolves one trusted `(user_id, tenant_id)` pair into one active membership and the exact effective permission keys that membership receives.

The critical requirement is isolation. A role from Tenant B must never contribute permissions while resolving a Tenant A membership, even if a bad mapping row exists.

## Architecture decision before the query

The RBAC schema allows roles whose `tenant_id` is null and also has an `is_system` flag, but the previous repository documentation did not explicitly define how those fields interact during tenant capability resolution. The Linear ticket requires stopping rather than guessing.

ADR-004 freezes the rule:

- tenant-owned roles contribute only inside their owning tenant;
- global roles contribute only when `tenant_id IS NULL` and `is_system = true`;
- global non-system roles contribute nothing;
- a role owned by another tenant contributes nothing;
- these global system roles remain workforce roles and never become platform-operator access.

This decision changes no schema and does not define role names or permission catalogs.

## ORM mappings and layers

`services/api/app/modules/tenancy/models.py` maps the already-existing `memberships`, `roles`, `role_permissions`, and `membership_roles` tables. No migration is added.

The rest of the module separates concerns:

- `repository.py` owns exact tenant-scoped reads;
- `service.py` owns fail-closed membership rules;
- `schemas.py` owns the immutable resolved result;
- `errors.py` owns the stable membership-access failure.

## Exact membership lookup

The repository begins with exact `tenant_id` and `user_id`. It never selects the first organization a user belongs to and never falls back to the only membership in the database.

The service requires status `active`. A missing membership and a suspended membership both fail closed with `TENANT_MEMBERSHIP_REQUIRED`. This prevents a suspended account from retaining authorization because the external identity is still valid.

## Tenant-safe role filtering

The permission query begins from the already-resolved membership ID and joins through `membership_roles`, `roles`, and `role_permissions`.

A role contributes only when:

```text
role.tenant_id == trusted tenant
OR
(role.tenant_id is NULL AND role.is_system == true)
```

That filter is important because the database mapping table has foreign keys but does not itself store a tenant ID. Defense in depth at read time prevents a malformed cross-tenant role mapping from becoming a privilege-escalation path.

## Permission deduplication

A person may hold multiple roles with overlapping capabilities. The repository removes duplicate permission keys and returns them in deterministic sorted order. Permission duplication therefore does not alter authorization meaning or produce unstable context output.

## Real PostgreSQL adversarial tests

The integration fixture creates three tenants, one user, an active Tenant A membership, a suspended Tenant B membership, two Tenant A roles with an overlapping permission, a Tenant B role, a valid global system role, and an invalid global non-system role.

It then deliberately maps the Tenant A membership to the Tenant B role. This mapping is structurally possible through the foreign keys, so it is a useful adversarial test. The resolver proves that the Tenant B secret permission still does not appear.

The tests also prove:

- active membership resolution;
- overlapping permission deduplication;
- valid global system-role contribution;
- global non-system role exclusion;
- suspended membership rejection;
- missing Tenant C membership rejection.

All fixtures are removed in foreign-key-safe order after each scenario.

## Security review

`docs/security-reviews/OPE-282-tenant-capability-resolution.md` records the explicit review of cross-tenant role leakage, suspended membership behavior, unsafe global roles, platform privilege separation, and information disclosure.

## What this improves

After OPE-282, Serviq can safely convert a verified internal workforce user and trusted tenant into the capability set later used by RequestContext and organization APIs. Authorization no longer has to assemble RBAC joins independently in each route.

## What remains

This ticket does not add HTTP route guards, role seeds, role-management APIs, organization APIs, invitations, or platform-operator access. OPE-283 uses this resolver when building organization list/create behavior.


---

# OPE-283 — Implement organization list and create APIs

## What problem this ticket solves

OPE-283 is the first ticket in this batch that turns the identity/RBAC foundation into a user-facing workforce API. An authenticated workforce user must be able to see only organizations where they have an active membership and create their first organization without manually inserting database rows.

Creating an organization is more than inserting one tenant row. The creator must immediately receive an active membership and the approved Owner role. Those three changes must behave as one unit.

## Stop conditions resolved before API code

The Linear ticket correctly identified two missing contracts.

### Owner role bootstrap

The PRD says the organization creator becomes Owner, but the repository had no concrete Owner role key or clean-database seed. CCR-005 freezes the minimum V1 workforce bootstrap:

- global system role `owner`;
- global system role `admin`;
- `organization.settings.write` for both;
- `organization.members.manage` for both.

These are tenant workforce roles, not platform roles. Alembic revision `20260815_0004` seeds them once. Request code looks them up and never dynamically creates another Owner role.

### Server-owned current user

OIDC validation and internal user upsert exist, but browser session middleware has not been implemented yet. ADR-005 therefore freezes the route handoff boundary: protected workforce routes may read only `request.state.serviq_user_id` as the already-verified internal user. They do not accept `X-User-ID`, JSON `userId`, or a query parameter.

If trusted session middleware has not populated that state, the endpoint returns 401. Tests use dependency overrides to populate the server-owned value, which is test infrastructure rather than a production authentication shortcut.

## Frozen API envelopes in Python

`app/core/api.py` mirrors the existing shared contracts package shapes:

```text
success -> { data: ... }
error   -> { error: { code, message, fields? } }
```

`app/core/http_errors.py` maps missing authentication and FastAPI request-validation failures into that envelope, so these first product APIs do not fall back to FastAPI's unrelated default `detail` shape.

## Request validation

`OrganizationCreateRequest` rejects unknown fields and enforces exactly the Linear contract:

- slug length 3–63;
- lowercase `a-z`, digits, and hyphens only;
- no leading/trailing hyphen;
- display name is trimmed;
- final display name length 1–120.

The API never accepts a user ID in this body.

## Membership-scoped listing

GET `/api/v1/organizations` starts from the current internal user and active memberships, then joins to organizations. Suspended memberships are excluded. There is no "only tenant" shortcut and no unscoped organization query.

## Atomic organization creation

POST `/api/v1/organizations` runs one transaction:

1. resolve the pre-seeded global system Owner role;
2. insert the active tenant;
3. flush so PostgreSQL validates slug constraints/uniqueness;
4. insert an active membership for the current user;
5. insert the membership-to-Owner mapping;
6. commit only after all steps succeed.

A duplicate slug is detected at the tenant flush and maps to HTTP 409. A later failure rolls the transaction back rather than leaving an ownerless tenant or membership without its role.

## Tests

Real PostgreSQL/API tests cover:

- authenticated user with no memberships receives an empty list;
- creating two organizations returns 201 and both appear in GET;
- the creator has two active memberships and two Owner mappings;
- another user sees neither organization;
- duplicate slug returns 409;
- uppercase, short, leading/trailing-hyphen slugs return 422;
- blank/oversized display names return 422;
- unknown `userId` input returns 422;
- missing server-owned principal returns 401;
- a deliberately forced membership-role mapping failure rolls back both tenant and membership.

The successful-create test also proves the migration-created Owner role exists at migration head.

## What this improves

After OPE-283, Serviq has a safe organization-onboarding primitive rather than requiring manual database setup. The API contract is strict, current-user identity is server-owned, organization visibility is membership-scoped, and the creator cannot end up with a partially-created authorization state.

## What remains

This ticket does not allow organization editing or invitations. OPE-284 adds safe detail/update behavior using the exact settings capability frozen by CCR-005. OPE-285 adds member invitation workflows using the member-management capability.


---

# OPE-284 — Implement organization detail and update APIs

## What problem this ticket solves

OPE-283 created organizations and listed memberships, but there was still no safe API for viewing one organization's metadata or editing its allowed settings. OPE-284 adds those routes without turning a route UUID into authorization.

## Authorization order

Both GET and PATCH begin with a membership-scoped organization query. The repository joins the requested organization to an active membership for the current server-owned internal user. If that join finds nothing, the API returns `ORGANIZATION_NOT_FOUND`.

This means a user in another tenant receives the same 404 whether the requested UUID belongs to somebody else or does not exist. Serviq does not reveal organization existence before access is proven.

PATCH performs a second authorization step after membership is established. It reuses OPE-282's tenant-capability resolver and requires the CCR-005 capability `organization.settings.write`. Owner/Admin receive that capability through the seeded system roles; a support-only member does not.

## Safe PATCH contract

`OrganizationUpdateRequest` contains only:

- optional `displayName`;
- optional `defaultLocale`.

The request rejects unknown fields, so `slug` and `status` cannot reach service code. Display names are trimmed and must be 1–120 characters. V1 locale is the literal `en` only. An empty request is rejected because every successful PATCH must contain at least one recognized change.

## Transaction behavior

PATCH starts one database transaction before membership lookup. Inside that transaction it:

1. proves active membership;
2. resolves effective permissions;
3. checks `organization.settings.write`;
4. changes only the supplied safe fields;
5. updates the modification timestamp;
6. flushes and commits together.

## HTTP behavior

- active member GET -> 200 `{data: ...}`;
- Owner/Admin PATCH -> 200 `{data: ...}`;
- same-tenant member without settings capability -> 403 `FORBIDDEN`;
- foreign/non-member GET or PATCH -> non-disclosing 404;
- invalid/unknown PATCH input -> 422 `VALIDATION_ERROR`;
- missing trusted workforce principal -> 401.

## Real PostgreSQL authorization matrix

The integration test creates two tenants and four users: Owner, Admin, support-only active member, and a user in the second tenant. It verifies:

- support member can read safe metadata;
- support member cannot update;
- Owner can update display name/locale;
- Admin can update display name;
- slug/status remain unchanged;
- foreign user receives 404 for both read and update;
- empty body, invalid display names, unsupported locale, `slug`, and `status` are rejected;
- unauthenticated access receives 401.

## Security review

`docs/security-reviews/OPE-284-organization-detail-update.md` records the non-disclosure, capability, field-immutability, locale, and transaction review.

## What this improves

Serviq now has a reusable pattern for tenant resource APIs: prove membership before disclosing resource metadata, then apply capability checks for mutations. Organization settings can be changed without making slug/status writable or allowing another tenant to probe organization IDs.

## What remains

This ticket does not add invitation operations, member removal, organization suspension, slug mutation, or platform-operator access. OPE-285 builds invitation create/list/revoke on the same membership and capability foundations.


---

# OPE-285 — Implement invitation create, list, and revoke APIs

## What problem this ticket solves

An organization administrator needs a safe way to invite another workforce user before that person has a Serviq membership. This sounds like a normal CRUD feature, but invitations are security-sensitive because an invitation carries two forms of authority:

1. a bearer secret that will later prove possession of the invitation; and
2. requested roles that determine what the new member may eventually do.

OPE-285 therefore treats invitation management as an authorization and secret-handling workflow, not just a database form.

## Stop conditions resolved before implementation

The database schema already existed from OPE-278, but the ticket correctly identified four missing implementation contracts. ADR-006 freezes all four before API code:

- deterministic invitation-email normalization;
- secure token generation and one-way hashing;
- the one-time public invitation URL format;
- exactly which role IDs may be assigned through an invitation.

The same ADR also freezes the member-management capability and revoke-conflict semantics so create/list/revoke cannot drift apart.

## Email normalization

Serviq stores and compares the normalized email rather than whichever capitalization or surrounding spaces the administrator typed.

The helper performs this sequence:

1. trim leading/trailing Unicode whitespace;
2. Unicode `casefold()` the complete address;
3. require normalized length 3–320, matching the database constraint;
4. reject whitespace inside the address;
5. require exactly one `@`;
6. require non-empty local and domain parts;
7. reject a domain beginning/ending with a dot or containing an empty dot-separated label.

For example:

```text
" Invitee@Example.COM "
        ↓
"invitee@example.com"
```

This is intentionally one deterministic Serviq matching rule. It is not an attempt to accept every historical RFC mailbox syntax. The future acceptance flow must reuse this helper so create and accept never disagree about who an invitation belongs to.

## Token generation

`generate_invitation_token()` uses:

```text
secrets.token_urlsafe(32)
```

The `32` requests 32 bytes, or 256 bits, of cryptographically secure random material before URL-safe encoding.

The token is not based on:

- UUIDs;
- timestamps;
- email addresses;
- tenant IDs;
- Python's normal pseudo-random generator.

That matters because the future acceptance URL is a bearer credential. Anyone who possesses a valid unexpired token may later present it to the acceptance endpoint.

## Why SHA-256 is used here

The plaintext token is immediately hashed with SHA-256 and only the lowercase hexadecimal digest is given to the ORM/database layer.

A slow password hash is designed to compensate for weak, human-chosen passwords. This invitation secret is different. It begins with 256 bits of random entropy. The security requirement is therefore to avoid storing a usable bearer credential, while retaining a deterministic verifier for the next ticket.

The schema contains `token_hash` and no plaintext-token column. OPE-285 does not add one.

Both the plaintext token and its hash are considered sensitive for logs. Knowing the hash should not be necessary for normal operational logging, so it is not logged either.

## Plaintext lifetime

The service deliberately does **not** generate a token as soon as the request arrives.

It first:

1. proves the caller has an active membership in the organization;
2. proves the caller has `organization.members.manage`;
3. resolves and validates all requested role IDs.

Only then does it generate the plaintext token, hash it immediately, and create the invitation row.

This minimizes how long sensitive plaintext exists in process memory. Python strings cannot be reliably zeroized after use, so the implementation does not claim memory zeroization. It reduces lifetime and prevents the token from crossing unnecessary code boundaries.

## One-time invite URL

After the database transaction succeeds, the create service builds:

```text
{SERVIQ_PUBLIC_BASE_URL}/invite?token={URL-encoded-token}
```

The origin comes from typed platform configuration, not from client input.

Only the successful POST response uses `InvitationCreateView`, which contains `inviteUrl`. The normal `InvitationView` used by GET and DELETE has no invite URL, plaintext token, or token hash.

Because the database stores only the digest, Serviq cannot reconstruct the invite URL later. This is intentional. The administrator receives the bearer URL once and future resend/email-delivery behavior must be designed separately.

## Role assignability

A role ID is invitation-assignable only when:

```text
role belongs to target tenant
OR
role is approved global workforce system role "owner" or "admin"
```

The query rejects:

- another tenant's role;
- missing roles;
- global non-system roles;
- any other global system role, even if `is_system=true`.

The final rule is important defense in depth. A future internal or platform-related role cannot suddenly become assignable through invitations merely because it happens to live in the same `roles` table. Global assignability is an explicit allowlist, not a side effect of `is_system`.

## Authorization

All three endpoints require the exact CCR-005 capability:

```text
organization.members.manage
```

The service reuses OPE-282's active-membership/capability resolver.

Authorization behavior is:

- no active membership in target tenant -> non-disclosing 404;
- active membership without member-management capability -> 403;
- Owner/Admin -> permitted because CCR-005 grants that capability;
- platform-operator access is not introduced here.

## Invitation creation transaction

POST creation runs one SQLAlchemy transaction:

1. resolve active membership/capability;
2. validate all requested roles;
3. generate secure plaintext token;
4. hash token immediately;
5. calculate `expires_at = now + 7 days`;
6. insert pending invitation with only `token_hash`;
7. flush so PostgreSQL enforces pending-email and hash uniqueness;
8. insert all invitation-role mappings;
9. flush mappings;
10. leave transaction successfully;
11. construct the one-time `inviteUrl` for the response.

If any role mapping or database constraint fails, the transaction cannot leave a partially-created invitation behind.

The PostgreSQL partial unique index remains the concurrency authority for "one pending invitation per tenant and normalized email." A duplicate maps to HTTP 409.

## Safe list behavior

GET is tenant-scoped and returns only safe metadata:

- invitation ID;
- normalized email;
- status;
- expiry;
- requested role IDs/keys/display names;
- inviter user ID;
- accepted user/timestamps when present;
- created/updated timestamps.

The serializer has no place for token, token hash, or invite URL. This is stronger than remembering to delete a secret field from a generic database serialization.

## Revoke behavior

DELETE looks up the invitation using both target tenant ID and invitation ID.

Only an invitation that is:

```text
status == pending
AND
expires_at > current time
```

may become revoked.

A successful revoke sets:

- `status = revoked`;
- `revoked_at = now`;
- `updated_at = now`.

Already revoked, accepted, or time-expired invitations return the same 409 lifecycle conflict. Re-revoke is intentionally not reported as a successful idempotent operation because the repository had no frozen idempotent-delete contract.

A user from another tenant receives non-disclosing 404 even if they know a valid invitation UUID.

## API routes

OPE-285 adds exactly:

```text
GET    /api/v1/organizations/{organizationId}/invitations
POST   /api/v1/organizations/{organizationId}/invitations
DELETE /api/v1/organizations/{organizationId}/invitations/{invitationId}
```

They reuse Serviq's `{data: ...}` and `{error: {...}}` envelopes.

Important public failures are:

- unauthenticated -> 401;
- inaccessible tenant/invitation -> 404;
- active member without capability -> 403;
- unassignable role -> 422;
- duplicate pending normalized email -> 409;
- invalid revoke lifecycle -> 409;
- malformed email/body/duplicate role IDs/client-supplied token field -> 422.

## Real PostgreSQL and API security tests

The integration suite creates two tenants plus Owner, Admin, support-only, and foreign-tenant users. It also creates:

- one tenant-owned role in Tenant A;
- one foreign Tenant B role;
- one support-only role;
- one deliberately unapproved global `is_system=true` role representing internal/platform-like scope.

The suite verifies:

### Create and secret handling

- Owner can create an invitation;
- input email is normalized;
- requested tenant role plus approved global Admin role are returned;
- create response contains one token-bearing `inviteUrl`;
- the query token can be extracted exactly once from that URL;
- database `token_hash` equals SHA-256 of the returned token;
- stored hash is not the plaintext token;
- expiry is seven days within a tiny execution-time tolerance;
- neither plaintext token nor hash appears in captured logs.

### Authorization and roles

- Admin can create;
- support-only member receives 403;
- foreign user cannot list/revoke Tenant A invitations;
- Tenant B role is rejected for a Tenant A invitation;
- unapproved global system/platform-like role is rejected.

### Conflict and serialization

- duplicate normalized pending email returns 409;
- list response includes neither token, hash, nor `inviteUrl`;
- revoke response includes neither token, hash, nor `inviteUrl`.

### Lifecycle

- pending invitation can be revoked;
- revoke timestamp is returned;
- repeated revoke returns lifecycle conflict;
- an accepted invitation inserted as a fixture cannot be revoked as pending.

### Input safety

- malformed email fails validation;
- empty role list fails;
- duplicate role IDs fail;
- a client attempt to supply a `token` field fails because unknown fields are forbidden;
- unauthenticated list fails with 401.

## Premium security review

`docs/security-reviews/OPE-285-invitation-management.md` records the explicit review of tenant access, privilege assignment, global-role allowlisting, entropy, hashing, secret lifetime, serializers, log redaction, duplicate-pending behavior, transaction atomicity, lifecycle enforcement, cross-tenant probing, and public URL origin.

The permanent OPE-272 Security workflow still has to pass on the final PR head. The written review is additional design evidence, not a replacement for automated scanning.

## What this improves

After OPE-285, an authorized Serviq organization administrator can safely create, inspect, and revoke workforce invitation records without storing a usable invitation secret or exposing another tenant's invitations. Role assignment is validated before persistence, and the database plus application layer jointly enforce one live invite per normalized email.

## What remains

OPE-285 deliberately does not accept invitations, create memberships from invitations, send invitation email, resend links, or implement browser session population. The next acceptance ticket must reuse the exact normalization and token-hash helpers frozen here so create and acceptance form one consistent security protocol.
