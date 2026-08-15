# OPE-288 — Reusable tenant-isolation harness security review

## Scope

This review covers test-only code under `services/api/tests/support` and the real-PostgreSQL integration test that applies it to organization and membership APIs. OPE-288 changes no production authorization, database schema, API status code, or platform-operator behavior.

## Security objective

The harness must make a false-positive tenant-isolation test difficult. It therefore creates tenant A and tenant B with overlapping human-facing values and gives tests the exact foreign UUIDs needed to attack the boundary directly.

## Controls

### Known foreign UUID attacks

The fixture exposes tenant-B organization, membership, user, and role identifiers. Tests do not depend on the UI hiding those identifiers. A privileged tenant-A owner receives a real tenant-B UUID and attempts direct GET/PATCH operations.

### Overlapping visible data

Both tenants intentionally use the same organization display name, user display name, user email, and role display name. A missing tenant predicate therefore cannot be masked by a coincidental unique label.

Role database keys remain tenant-specific only because the current schema requires global uniqueness. The visible role name remains identical so user-facing equality cannot substitute for ownership checks.

### Real PostgreSQL, no mocked repository filters

The harness inserts rows into the actual migration-defined tables and exercises FastAPI routes backed by the real repositories. It does not mock the tenant predicate being verified.

### Read and mutation assertions

Reusable helpers cover three different failure modes:

- list leakage: the known foreign resource ID must be absent;
- get/update/delete access: a foreign resource remains hidden under the existing 404 semantics;
- mutation integrity: the foreign persisted value before and after a rejected mutation must be identical.

### Privileged callers

The integration test attacks tenant B as tenant A's Owner, not merely an unprivileged member. This proves `organization.members.manage` and organization-management capabilities remain bounded by tenant membership.

### Bidirectional fixture use

The same test reverses A/B roles and repeats isolation from tenant B toward tenant A. This catches accidental fixture assumptions that make one side globally special.

### Cleanup isolation

Cleanup targets only UUIDs created by that typed fixture. Shared bootstrap Owner/Admin roles are never deleted. The integration test performs cleanup in `finally`, reducing state leakage into later tests even when assertions fail.

## What this harness does not prove

A reusable fixture is not a replacement for domain-specific isolation assertions. Every future tenant-owned domain must still create tenant-A and tenant-B resources and use the harness identifiers/assertions around that domain's repository or API behavior.

It also does not claim PostgreSQL Row Level Security exists; current isolation is enforced through application/repository tenant predicates according to the implemented architecture.

## Conclusion

OPE-288 creates a reusable, adversarial tenant-isolation control without weakening production behavior. It directly exercises known foreign identifiers, privileged callers, persisted-state integrity, and overlapping visible data against real PostgreSQL.