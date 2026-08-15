# OPE-287 — Member management security review

## Scope

This review covers:

- `GET /api/v1/organizations/{organizationId}/members`
- `PATCH /api/v1/organizations/{organizationId}/members/{membershipId}`

It does not change invitation acceptance, OIDC verification, platform-operator access, or the membership schema.

## Security invariants

### Tenant identity comes from the route and every resource query repeats it

The target membership query always includes both `membership_id` and `tenant_id`. A known membership UUID from tenant B therefore cannot be used through a tenant-A route. Member-list queries also include the requested tenant ID directly.

The caller must have an active membership in the same tenant before the management capability is considered. A caller from another tenant gets the same non-disclosing membership/organization not-found response.

### Safe member responses do not expose OIDC identity keys

The list/detail serializer returns only:

- membership ID;
- internal user ID;
- email;
- display name;
- membership status;
- assigned role ID/key/display name.

It intentionally omits `oidc_issuer` and `oidc_subject`. Those fields remain internal identity-linking data and are not needed by Team & Access UI.

### Tenant roles cannot grant platform-operator privileges

Requested role IDs are resolved with an explicit allow rule:

- tenant-owned roles for the target tenant; or
- frozen global workforce system roles `owner` and `admin`.

A global system role with any other key is rejected. A role belonging to another tenant is rejected. The service compares the full requested ID set with the full resolved allowlisted set before replacing mappings.

### Role replacement and status mutation are atomic

PATCH runs inside one SQLAlchemy transaction. Role mappings and status changes are flushed but committed only when the whole operation succeeds. Validation/authorization/last-owner failures leave the previous membership state intact.

### Last active owner protection is serialized on the tenant row

The main race to prevent is:

1. tenant has owners A and B;
2. request X removes A's owner role;
3. request Y simultaneously removes B's owner role;
4. both count two owners before either commits;
5. tenant ends with zero active owners.

OPE-287 avoids that race by locking the tenant's `tenants` row with PostgreSQL `FOR UPDATE` before authorization, target lookup, owner counting, or mutation. Every member PATCH for the tenant takes that same lock. Two competing mutations therefore cannot make the owner decision concurrently.

After the lock is acquired, the service computes whether the target is currently an active owner and whether the requested state would stop that membership from being an active owner. If so, it counts active owner memberships inside the same transaction. Count `<= 1` produces `LAST_ACTIVE_OWNER` and no mutation.

This is deliberately conservative: serializing member PATCH operations per tenant is simpler to reason about than trying to lock a changing join between memberships, roles, and membership-role rows. The expected Team & Access write rate is low enough that the correctness benefit is more important than parallel PATCH throughput.

### Authorization uses existing frozen capability resolution

The routes do not implement a second role-name authorization system. They call the existing effective capability resolver and require `organization.members.manage`, which is already granted to the frozen Owner/Admin workforce roles. An active member with an ordinary tenant role is denied even if they know target UUIDs.

### Input is strict

PATCH accepts only `roleIds` and `status`.

- Unknown fields are rejected.
- Status accepts only `active|suspended`.
- Duplicate role IDs are rejected before persistence.
- An empty PATCH is rejected.
- Role-list size is bounded.

This prevents accidental client-controlled tenant IDs, platform flags, user IDs, or other mass-assignment fields from reaching service logic.

## PostgreSQL attack coverage

The integration test creates two tenants with deliberately overlapping organization names, user display names, member email values, and role display names. It then proves:

- tenant-A list pages never contain tenant-B membership IDs;
- tenant-A owner cannot list tenant B;
- tenant-A owner cannot mutate a known tenant-B membership UUID through tenant A;
- ordinary tenant-A member cannot list or PATCH;
- tenant-B role ID is rejected on tenant-A target;
- synthetic global platform-operator system role is rejected;
- valid tenant role replacement succeeds without duplicate rows;
- duplicate role input and unknown PATCH fields fail validation;
- non-owner suspension succeeds;
- removing one of two owners succeeds;
- suspending or removing the owner role from the remaining active owner returns conflict and leaves the row active.

## Residual considerations

The list route uses bounded `limit`/`offset` pagination and the repository orders by `(created_at, id)` for deterministic pages. Offset pagination can shift if rows are inserted concurrently; that affects navigation consistency, not tenant isolation. A cursor contract can replace it later if/when Serviq freezes a shared cursor envelope.

## Conclusion

OPE-287 preserves tenant isolation, keeps identity-linking fields private, blocks platform-role escalation, uses the existing capability system, and serializes last-owner decisions strongly enough that concurrent tenant member mutations cannot remove all active owners.