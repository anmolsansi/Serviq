# ADR-004 — Tenant and system role resolution semantics

## Status

Accepted for OPE-282.

## Context

The frozen RBAC schema permits two role ownership shapes:

- a role owned by one tenant through `roles.tenant_id`;
- a role with no tenant owner and `is_system = true`.

OPE-282 must prevent a membership in Tenant A from inheriting a role owned by Tenant B. The existing architecture does not explicitly state how a global system role participates in tenant capability resolution, and the Linear ticket requires an architect decision rather than an implicit SQL assumption.

## Decision

For workforce tenant-capability resolution:

1. Start from the exact membership identified by trusted `(tenant_id, user_id)`.
2. The membership must have status `active`.
3. A role mapping may contribute permissions only when either:
   - `roles.tenant_id` equals the trusted target tenant, or
   - `roles.tenant_id IS NULL` and `roles.is_system = true`.
4. A role owned by any other tenant never contributes permissions, even if a malformed or historically bad `membership_roles` row points to it.
5. A global row with `tenant_id IS NULL` but `is_system = false` is not an approved reusable role and contributes nothing.
6. Permission keys from all approved mapped roles are deduplicated before being returned.
7. These system roles remain **tenant workforce roles**. They do not grant Serviq platform-operator access. Platform-operator authorization remains a separate trust boundary.

## Why

The schema intentionally allows global system roles, so rejecting every `tenant_id IS NULL` role would make that shape unusable. At the same time, allowing every mapped role would create a cross-tenant privilege-escalation path because `membership_roles` itself does not encode tenant ownership.

The resolver therefore applies tenant ownership at read time as a defense-in-depth rule. This means authorization remains safe even if an invalid cross-tenant mapping row somehow exists.

## Consequences

- Tenant-owned custom roles work only inside their owning tenant.
- Approved global system roles can be reused by memberships in multiple tenants.
- Cross-tenant mapping corruption cannot leak another tenant's permissions through the resolver.
- This ADR does not define role names, seed roles, or permission catalogs. Those remain separate product/bootstrap decisions.
- No schema change is required.

## Rejected alternatives

### Trust every `membership_roles` row

Rejected because the mapping table alone does not prove that the referenced role belongs to the membership tenant.

### Permit every role with `tenant_id IS NULL`

Rejected because a null owner alone does not prove that the row is an architecture-approved reusable system role. `is_system` must also be true.

### Treat system roles as platform roles

Rejected because Serviq's platform operator is explicitly a separate trust boundary and cannot be granted by tenant RBAC.
