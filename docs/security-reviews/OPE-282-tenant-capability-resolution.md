# OPE-282 Security Review — Tenant Capability Resolution

## Review status

Approved for merge only after the final pull-request head passes the permanent CI and Security workflows.

## Trust boundary

The resolver accepts an internal `user_id` and `tenant_id` that must already come from trusted server state. It converts that pair into one active membership and a deduplicated set of tenant-effective permissions.

## Threats and controls

### Cross-tenant membership lookup

Control: membership lookup always requires the exact `(tenant_id, user_id)` pair. There is no first-membership, only-membership, or default-tenant fallback.

### Suspended membership retaining access

Control: any membership whose status is not exactly `active` fails with the same closed membership-access category as a missing membership.

### Foreign tenant role leakage

Control: a mapped role contributes permissions only when its `tenant_id` equals the trusted tenant. Integration tests deliberately create a structurally valid mapping from a Tenant A membership to a Tenant B role and prove the Tenant B permission is excluded.

### Unsafe global role reuse

Control: a global role contributes only when `tenant_id IS NULL` **and** `is_system = true`. A global non-system role is excluded.

### Platform privilege escalation

Control: global system roles remain workforce RBAC roles. The resolver does not construct platform-operator identity or platform permissions. Platform authorization remains a separate trust boundary.

### Duplicate/ambiguous permissions

Control: permission keys from all approved roles are deduplicated and returned in deterministic sorted order. Duplicate grants do not change authorization meaning.

### Information disclosure

Control: failures do not return another membership, tenant, role, or permission details. The typed failure says only that active tenant membership is required.

## Required adversarial tests

- active tenant membership resolves expected permissions;
- overlapping role permissions deduplicate;
- suspended membership fails closed;
- missing membership fails closed;
- foreign tenant role mapping contributes nothing;
- approved global system role contributes;
- global non-system role contributes nothing;
- no unrelated tenant permission appears in the result.

## Deliberate non-goals

This review does not approve HTTP route guards, organization APIs, role seeding, invitation role assignment, or platform-operator authorization. Those are separate boundaries.
