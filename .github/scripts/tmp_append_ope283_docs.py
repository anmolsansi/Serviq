from pathlib import Path

focused = Path("docs/OPE_279_285_IMPLEMENTATION_GUIDE.md")
focused_marker = "# OPE-283 — Implement organization list and create APIs"
focused_section = r'''

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
'''
if focused_marker not in focused.read_text():
    focused.write_text(focused.read_text() + focused_section)

build = Path("docs/SERVIQ_BUILD_GUIDE.md")
build_marker = "# OPE-283 — organization list and create APIs"
build_section = r'''

---

# OPE-283 — organization list and create APIs

OPE-283 exposes the first tenant-management workforce endpoints: GET and POST `/api/v1/organizations`.

Two explicit stop conditions were resolved before route code. CCR-005 freezes and seeds global workforce system roles `owner` and `admin`, each with `organization.settings.write` and `organization.members.manage`. ADR-005 freezes the protected-route principal handoff as server-owned `request.state.serviq_user_id`; organization routes never accept a client-supplied user ID.

The API now mirrors Serviq's frozen `{data:...}` and `{error:{...}}` envelopes in Python and maps authentication/request-validation failures into those shapes. Organization creation validates the exact slug/display-name contract and rejects unknown fields.

GET lists only tenants reached through the current user's active memberships. POST performs one transaction that creates the tenant, the creator's active membership, and the mapping to the pre-seeded Owner role. Duplicate slug maps to 409. Any later mapping failure rolls the whole transaction back.

Real PostgreSQL/API tests cover empty/two-organization lists, cross-user isolation, Owner mappings, duplicate slug, all specified validation failures, unauthenticated access, and a forced mapping failure proving atomic rollback.

A focused security review is recorded at `docs/security-reviews/OPE-283-organization-list-create.md`, and the detailed implementation narrative is in `docs/OPE_279_285_IMPLEMENTATION_GUIDE.md`.
'''
if build_marker not in build.read_text():
    build.write_text(build.read_text() + build_section)
