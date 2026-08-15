# CCR-005 — V1 workforce system role bootstrap

## Status

Approved for OPE-283 and the immediately dependent OPE-284/OPE-285 organization workflows.

## Problem

Architecture freezes the RBAC schema and the PRD freezes the Owner/Admin authorization intent, but the repository did not contain the concrete system-role keys or a database bootstrap. OPE-283 cannot atomically make a new organization creator its owner if a clean database has no owner role to map.

OPE-284 and OPE-285 also require exact capability keys for organization settings and member/invitation management. Leaving those strings to individual routes would create authorization drift.

## Frozen V1 bootstrap

Create exactly two global workforce system roles:

| Role key | Display name | tenant_id | is_system |
|---|---|---|---|
| `owner` | `Owner` | `NULL` | `true` |
| `admin` | `Admin` | `NULL` | `true` |

Grant both roles exactly these capabilities for the current organization-management scope:

- `organization.settings.write`
- `organization.members.manage`

These capability keys mean:

- `organization.settings.write`: edit the safe organization settings exposed by OPE-284;
- `organization.members.manage`: create/list/revoke workforce invitations and manage tenant membership workflows covered by OPE-285 and later membership-management tickets.

## Security boundary

These are **tenant workforce system roles**, not platform roles. They can contribute permissions only through an active tenant membership under ADR-004. They do not grant platform-operator access and cannot bypass tenant resolution.

## Bootstrap mechanism

The roles and role-permission rows are seeded by an Alembic data migration. Application services resolve the pre-existing system role by key. They must never dynamically create a second Owner/Admin role during an API request.

## Compatibility

This change does not alter table structure or the RequestContext contract. It fills previously missing seed data and freezes the minimum capability vocabulary required by the already-approved PRD action matrix.

Additional system roles or capabilities require a later explicit contract change rather than being inferred from UI labels.
