# OPE-283 Security Review — Organization List and Create APIs

## Review status

Approved for merge only after final CI, real PostgreSQL integration, migration reversibility, and the permanent Security workflow pass.

## Trust boundaries reviewed

The routes accept no client-supplied workforce user ID. The current internal user is read only from the server-owned principal handoff frozen by ADR-005. Organization listing and creation then rely on PostgreSQL membership/RBAC state.

## Threats and controls

### User identity spoofing

Control: `require_workforce_user_id()` reads only `request.state.serviq_user_id` and requires an actual UUID. Organization JSON has no `userId` field and unknown fields are rejected. Missing server-owned principal returns 401.

### Cross-user tenant disclosure

Control: GET begins from active memberships for the current internal user and joins to tenants. There is no fallback to the first or only tenant.

### Partial organization creation

Control: tenant, creator membership, and Owner mapping are in one SQLAlchemy transaction. A forced mapping failure is integration-tested and leaves neither tenant nor membership committed.

### Dynamic privilege creation

Control: the request service never creates roles. CCR-005 seeds the global Owner/Admin workforce system roles in a migration. Organization creation resolves the existing `owner` role by exact key and system-role attributes.

### Duplicate organization slug

Control: exact request validation runs before persistence, and PostgreSQL's unique constraint remains the concurrency authority. A unique conflict during tenant flush maps to stable HTTP 409.

### Platform-role crossover

Control: CCR-005 roles are tenant workforce system roles. The routes have no platform-operator principal path and do not bypass active tenant membership.

### Error-shape drift

Control: authentication, validation, duplicate-slug, and bootstrap failures use Serviq's `{error:{...}}` envelope. Success responses use `{data:...}`.

## Adversarial coverage

- unauthenticated request receives 401;
- request body cannot inject `userId`;
- another user cannot see a tenant created by the first user;
- invalid/uppercase/leading/trailing slug values fail validation;
- blank/oversized display names fail validation;
- duplicate slug maps to 409;
- forced owner mapping failure rolls back tenant and membership;
- successful create maps the creator to the pre-seeded Owner role.

## Deliberate non-goals

This review does not approve organization update behavior, invitation handling, browser-session population of request state, role-management APIs, or platform-operator organization access.
