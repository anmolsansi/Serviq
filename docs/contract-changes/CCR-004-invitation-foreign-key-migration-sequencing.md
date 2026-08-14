# Contract Change Record: CCR-004

## Contract

Architecture database contract for `memberships.created_by_invitation_id` and the migration split between OPE-277 (`tenants`, `users`, `memberships`, `roles`, `role_permissions`, `membership_roles`) and OPE-278 (`organization_invitations`, `organization_invitation_roles`).

## Current shape

The frozen final schema says:

- `memberships.created_by_invitation_id uuid NULL FK organization_invitations SET NULL`.
- OPE-277 must create `memberships` but must not create invitation tables.
- OPE-278 creates `organization_invitations` later.

Those requirements cannot all be applied as a PostgreSQL foreign-key constraint inside the OPE-277 migration because PostgreSQL requires the referenced table to exist when the constraint is created.

## New shape

The **final database schema does not change**.

Migration sequencing is clarified as follows:

1. OPE-277 creates the nullable `memberships.created_by_invitation_id uuid` column with no foreign-key constraint yet.
2. OPE-278 creates `organization_invitations` and `organization_invitation_roles`.
3. In that same OPE-278 migration, after `organization_invitations` exists, add the named foreign key from `memberships.created_by_invitation_id` to `organization_invitations.id` with `ON DELETE SET NULL`.
4. OPE-278 downgrade drops that foreign key before dropping invitation tables.

After OPE-278 upgrades, the resulting schema exactly matches the frozen Architecture contract.

## Reason

This resolves a migration dependency cycle without creating invitation tables early, changing table names, changing column names, weakening the final foreign-key behavior, or combining two tickets into one migration. It preserves the explicit product ownership split while making both migrations executable on real PostgreSQL.

## Breaking?

No. There is no released production schema to migrate, and the final Architecture schema remains unchanged. Between migration revisions `20260814_0002` and `20260814_0003`, the invitation-origin column exists before its referential constraint; application/runtime invitation logic is not introduced during that intermediate revision.

## Compatibility plan

- No application code may rely on `created_by_invitation_id` until OPE-278 has created the invitation tables and final foreign key.
- OPE-277 adds no API/business logic that can write invitation IDs.
- OPE-278 adds the missing final FK before any later invitation runtime/API ticket can depend on it.

## Migration plan

- OPE-277 migration revision: create the six tenant/workforce/RBAC tables, including nullable `memberships.created_by_invitation_id`, but explicitly defer the invitation FK.
- OPE-278 migration revision: create invitation tables, then use Alembic to create the named `memberships.created_by_invitation_id` foreign key with `ON DELETE SET NULL`.
- OPE-278 downgrade: drop the deferred FK first, then drop invitation-role and invitation tables in dependency-safe order.
- Real PostgreSQL tests validate OPE-277's six-table intermediate schema and OPE-278's complete final referential behavior.

## Downstream impact

- OPE-277 implementation/tests must treat the missing invitation FK as an approved temporary migration state, not an omission.
- OPE-278 implementation/tests must add and verify the deferred FK.
- `docs/ARCHITECTURE.md` receives a migration-sequencing note next to the frozen schema so future builders do not attempt to create an impossible FK before its referenced table.
- `docs/repo_context.md` and `docs/SERVIQ_BUILD_GUIDE.md` must explain the sequencing once the migrations are implemented.
- GitHub issues #74 and #75 / Linear OPE-277 and OPE-278 completion records should reference CCR-004.

## Updated artifacts

- `docs/contract-changes/CCR-004-invitation-foreign-key-migration-sequencing.md`
- `docs/ARCHITECTURE.md`
- OPE-277 migration/tests/documentation
- OPE-278 migration/tests/documentation
- `docs/repo_context.md`
- `docs/SERVIQ_BUILD_GUIDE.md`
