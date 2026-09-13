# ADR-030 — Workforce session and server-owned tenant context

## Status

Accepted for V1.1.16 backend completion. Tracked by GitHub issue #230 and PR #231.

## Context

Serviq already validates workforce OIDC tokens, maps verified identities to internal users, resolves active tenant memberships, and exposes protected routes through trusted request-state readers. PR #229 added Authorization Code + PKCE and an opaque Valkey session, but normal protected requests still did not restore those request-state values. Its tenant helper also accepted `X-Serviq-Tenant-ID`, which conflicts with ADR-009: a browser-controlled header cannot be the source of tenant authority.

The client console needs an authenticated session and a tenant switcher, but V1.9.02 owns the UI. V1.1.16 therefore completes only the backend trust boundary.

## Decision

1. Workforce browser authentication uses Authorization Code + PKCE S256 with one-time Valkey auth state. Provider access tokens are validated server-side and are not stored in browser-visible state.
2. The browser receives only an opaque `serviq_session` cookie. The server-side Valkey record owns the internal user ID, verified OIDC identity fields, optional active tenant ID, and a random CSRF token.
3. HTTP middleware restores `serviq_user_id`, `serviq_workforce_identity`, and, when present, `serviq_tenant_id` from that server-side record before protected route dependencies run.
4. Tenant identity is never accepted from a request header, query parameter, or arbitrary business payload. In particular, `X-Serviq-Tenant-ID` is not an authorization contract.
5. On login, Serviq automatically selects a tenant only when the user has exactly one active membership. Zero or multiple active memberships leave `active_tenant_id` unset.
6. `POST /auth/tenant` is the only V1 browser tenant-switch operation. It revalidates the requested user/tenant pair through the authoritative membership service before updating the session record. Session replacement uses the existing key and preserves its remaining TTL.
7. Existing tenant services remain the authorization source of truth. A session-selected tenant is routing context, not cached permission authority. Provider and knowledge services continue to recheck active membership/capabilities in PostgreSQL.
8. `GET /auth/session` returns browser-safe session state needed by the console: internal user ID, email/display name, active tenant ID, and CSRF token. It never returns the opaque session ID or OIDC token.
9. Cookie-authenticated state-changing auth operations require the session-bound CSRF token in `X-Serviq-CSRF-Token`. Tenant switching always requires it. Logout requires it for a valid live session; an absent or already-expired session remains idempotently clearable.
10. Post-login redirects must use the exact scheme, hostname, and effective port of `SERVIQ_PUBLIC_BASE_URL`. Host-prefix lookalikes, credentials, fragments, non-HTTP schemes, and different ports fail closed.
11. A session-store outage fails closed with stable `503 SESSION_STORE_UNAVAILABLE` and `Retry-After: 5`. Requests with no session cookie, such as health checks and login initiation, do not require a session lookup.
12. Existing sessions created before this contract lack the required CSRF field and are treated as invalid. Users reauthenticate. No database migration or durable-data conversion is required.

## Security consequences

- The browser cannot forge tenant authority by supplying another tenant UUID.
- A stolen cross-site form submission cannot silently mutate tenant selection or revoke a live session without the session-bound CSRF proof.
- Session IDs, CSRF values, OIDC tokens, and provider/knowledge secrets must not be logged.
- Membership suspension or removal is still enforced by tenant-scoped service authorization even if a stale session names that tenant.

## Failure and operational behavior

- Missing, expired, or malformed session records behave as unauthenticated requests.
- Valkey unavailability is distinguishable from an invalid session and returns 503 rather than 401 or 500.
- Tenant-switch failure does not mutate the existing active tenant.
- A successful tenant switch does not extend the 24-hour session lifetime.
- Rollback is code-only. Reverting this change may discard incompatible session records; users can safely authenticate again.

## Alternatives rejected

### Client `X-Serviq-Tenant-ID` header

Rejected because the browser would choose authorization context directly. Validating membership on every request reduces but does not remove the contract violation and creates two competing tenant-selection mechanisms.

### Put tenant and permissions in a signed browser token

Rejected for V1. Permissions and membership state change independently and must remain authoritative in PostgreSQL. Opaque server sessions make revocation and context changes simpler.

### Add a new auth/session service

Rejected. FastAPI, Valkey, the existing OIDC validator, workforce mapper, and tenancy service already provide the required boundaries. Another service would add operational cost without improving the trust model.

## Verification

V1.1.16 requires HTTP-level tests without principal dependency overrides for missing/expired sessions, real request-state restoration, forged tenant-header resistance, authorized tenant switching, rejected foreign/suspended memberships, CSRF, redirect validation, and session-store outage behavior. Repository lint, strict mypy, tests, CI, Security, and required integration gates must pass on the exact final PR head.
