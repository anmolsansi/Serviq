# OPE-284 Security Review — Organization Detail and Update APIs

## Review status

Approved for merge only after the final pull-request head passes CI, real PostgreSQL integration, and the permanent Security workflow.

## Trust boundary

The routes receive an organization UUID from the URL, but that UUID is only a lookup hint. It is not proof that the current workforce user belongs to the organization or may edit it.

## Threats and controls

### Cross-tenant existence disclosure

Control: both GET and PATCH begin with a repository query joining the organization to an `active` membership for the current internal user. A foreign user receives the same `ORGANIZATION_NOT_FOUND` response whether the UUID is real or nonexistent.

### Unauthorized settings mutation

Control: after active membership is proven, PATCH resolves the caller's effective tenant capabilities through OPE-282 and requires the exact CCR-005 capability `organization.settings.write`. Members without that capability receive 403.

### Client-controlled tenant identity

Control: the organization ID is never copied into trusted auth context merely because it appears in the route. Membership and RBAC are resolved from PostgreSQL using the server-owned workforce user ID.

### Mutating restricted fields

Control: the PATCH schema contains only `displayName` and `defaultLocale` and rejects unknown fields. `slug` and `status` therefore cannot reach the mutation service.

### Locale scope expansion

Control: V1 accepts only literal `en`. Other locale strings fail validation before persistence.

### Empty update ambiguity

Control: an empty object or a body where both recognized fields are absent/null fails validation. Every successful PATCH therefore contains at least one recognized setting change.

### Transaction consistency

Control: membership lookup, capability resolution, field mutation, and flush run inside one SQLAlchemy transaction.

## Required adversarial coverage

- active support/member role can GET safe organization metadata;
- Owner can PATCH;
- Admin can PATCH;
- active member without settings capability receives 403;
- foreign-tenant user receives non-disclosing 404 for GET and PATCH;
- empty/blank/oversized display name fails;
- unsupported locale fails;
- `slug` and `status` fail as unknown fields;
- missing server-owned principal returns 401.

## Deliberate non-goals

This review does not approve organization suspension, slug changes, role management, invitation operations, or platform-operator organization access.
