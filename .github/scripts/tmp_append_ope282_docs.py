from pathlib import Path

focused = Path("docs/OPE_279_285_IMPLEMENTATION_GUIDE.md")
focused_marker = "# OPE-282 — Resolve tenant membership and effective capabilities"
focused_section = r'''

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
'''
if focused_marker not in focused.read_text():
    focused.write_text(focused.read_text() + focused_section)

build = Path("docs/SERVIQ_BUILD_GUIDE.md")
build_marker = "# OPE-282 — tenant membership and effective capability resolution"
build_section = r'''

---

# OPE-282 — tenant membership and effective capability resolution

OPE-282 adds the tenant-scoped authorization resolver that sits between a stable internal workforce user and later protected organization APIs. The resolver requires the exact trusted `(user_id, tenant_id)` pair and accepts only an `active` membership. Missing and suspended memberships fail closed.

ADR-004 resolves the previously unstated system-role rule before coding: a tenant-owned role contributes only to its own tenant, while a global role is reusable only when `tenant_id IS NULL` and `is_system = true`. A role owned by another tenant is filtered out even if a malformed mapping row points to it. Global system roles remain workforce RBAC and cannot create platform-operator access.

The new tenancy module maps the existing membership/RBAC tables without changing the schema, performs tenant-safe joins, deduplicates permission keys, and returns one immutable `ResolvedTenantMembership` DTO.

Real PostgreSQL tests deliberately map a Tenant A membership to a Tenant B role and prove the foreign permission is excluded. They also cover overlapping permission deduplication, approved global system roles, global non-system exclusion, suspended membership, and missing membership.

A dedicated security review is recorded at `docs/security-reviews/OPE-282-tenant-capability-resolution.md`. No HTTP route or middleware behavior is added in this ticket.

The detailed implementation narrative is in `docs/OPE_279_285_IMPLEMENTATION_GUIDE.md`.
'''
if build_marker not in build.read_text():
    build.write_text(build.read_text() + build_section)
