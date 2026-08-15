from pathlib import Path

focused = Path("docs/OPE_279_285_IMPLEMENTATION_GUIDE.md")
focused_marker = "# OPE-284 — Implement organization detail and update APIs"
focused_section = r'''

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
'''
if focused_marker not in focused.read_text():
    focused.write_text(focused.read_text() + focused_section)

build = Path("docs/SERVIQ_BUILD_GUIDE.md")
build_marker = "# OPE-284 — organization detail and update APIs"
build_section = r'''

---

# OPE-284 — organization detail and update APIs

OPE-284 adds GET and PATCH `/api/v1/organizations/{organizationId}` while preserving tenant non-disclosure. Both routes first prove that the current server-owned workforce user has an active membership before returning organization metadata. A foreign user receives 404 rather than learning whether another tenant's UUID exists.

PATCH then reuses OPE-282 capability resolution and requires the exact CCR-005 permission `organization.settings.write`. Owner/Admin can update, while same-tenant roles without that capability receive 403.

The PATCH schema exposes only trimmed `displayName` and V1 `defaultLocale=en`, rejects unknown fields, and rejects an empty change set. `slug` and `status` are therefore immutable through this API. The membership check, capability check, mutation, and flush run inside one transaction.

Real PostgreSQL/API tests cover member read, Owner/Admin updates, support-role denial, cross-tenant 404 behavior, unsupported locale, invalid display names, immutable `slug`/`status`, empty PATCH, and unauthenticated access.

A focused review is recorded at `docs/security-reviews/OPE-284-organization-detail-update.md`; the detailed narrative is in `docs/OPE_279_285_IMPLEMENTATION_GUIDE.md`.
'''
if build_marker not in build.read_text():
    build.write_text(build.read_text() + build_section)
