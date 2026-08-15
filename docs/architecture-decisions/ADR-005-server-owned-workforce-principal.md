# ADR-005 — Server-owned workforce principal boundary for API routes

## Status

Accepted for OPE-283 until the later browser-session middleware ticket owns principal population.

## Context

OPE-280 verifies workforce OIDC identity and OPE-281 resolves it to a stable internal `users.id`, but the current API scaffold does not yet include the browser session/PKCE middleware that places that internal user on every protected request. OPE-283 must not work around this gap by accepting a user ID from a request header, query string, or JSON body.

## Decision

Protected workforce routes may consume the current internal user only from server-owned Starlette request state:

```text
request.state.serviq_user_id
```

Rules:

1. The value must be a UUID already produced by trusted authentication/session code.
2. Route dependency code only **reads** this value. It does not parse OIDC tokens or create sessions.
3. If the value is absent or not a UUID, the route fails with HTTP 401 using Serviq's frozen error envelope.
4. No `X-User-ID`, request-body `userId`, query parameter, or cookie value is directly interpreted by organization routes.
5. Tests may install a test-only middleware/dependency override that populates request state to exercise route behavior. That test hook is not a production authentication mechanism.
6. A later session middleware ticket will become the sole production writer of `serviq_user_id` after OIDC/session verification. This reader contract can remain unchanged.

## Why

Request state is server-owned within the ASGI application. Using one reserved state field lets protected routes be implemented and tested now without inventing browser-session behavior or creating a client-spoofable identity header.

## Consequences

- Real requests remain unauthenticated until trusted auth/session middleware populates the state field.
- Organization code stays independent from OIDC token parsing.
- The later session implementation has one explicit principal handoff contract.
- Platform-operator identity remains separate and cannot enter this workforce principal dependency.
