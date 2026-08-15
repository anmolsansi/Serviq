# OPE-285 Security Review — Invitation Create, List, and Revoke APIs

## Review status

Approved for merge only after the final pull-request head passes the permanent CI, real PostgreSQL integration, migration reversibility, CodeQL, Gitleaks, Trivy, and dependency-audit workflows.

## Trust boundaries reviewed

OPE-285 crosses three sensitive boundaries at once:

1. tenant authorization, because one organization's administrators must never manage another organization's invitations;
2. privilege assignment, because invitations carry requested role IDs;
3. bearer-secret handling, because possession of the invitation token will later authorize invitation acceptance.

The implementation keeps these boundaries separate and fail-closed.

## Threats and controls

### Client or foreign user managing another tenant's invitations

Control: every create/list/revoke operation starts with OPE-282's exact `(user_id, tenant_id)` active-membership resolution and then requires `organization.members.manage`. A missing membership becomes non-disclosing 404. A same-tenant member without the capability receives 403.

### Foreign-tenant role injection

Control: requested role IDs are loaded through one tenant-safe query. A role is accepted only when it belongs to the target tenant or is one of the explicitly approved global workforce system roles `owner` or `admin`. A role owned by another tenant is rejected before any invitation is inserted.

### Future platform/internal role injection

Control: global system-role status alone is not enough. The global role key must be explicitly allowlisted as `owner` or `admin`. Tests create an unapproved global system role representing platform/internal scope and prove it is rejected.

### Weak or predictable bearer token

Control: invitation tokens come from `secrets.token_urlsafe(32)`, which uses 32 bytes of cryptographically secure random material. UUIDs, timestamps, email addresses, tenant IDs, and pseudo-random generators are not used as bearer secrets.

### Plaintext token persistence

Control: token generation occurs only after authorization and role validation. The token is immediately SHA-256 hashed and only the hexadecimal digest is assigned to the ORM model. The schema has no plaintext token column.

### Offline guessing of stored token hash

Control: the token has 256 bits of random entropy, unlike a human password. SHA-256 is used as a one-way verifier for that high-entropy random bearer value. A slow password KDF is not needed to compensate for weak human-chosen entropy.

### Token leakage through list/revoke serializers

Control: `InvitationView` has no token, token-hash, or invite-URL field. `InvitationCreateView` adds `inviteUrl` only for the successful POST response. GET and DELETE use the safe base view.

### Token/hash leakage through logs or errors

Control: neither the token nor its digest is passed to logging calls, exception messages, metrics, audit metadata, or route errors. Integration tests derive both values and assert neither appears in captured logs or later API responses.

### Duplicate live invitations

Control: normalized email is deterministic and PostgreSQL's partial unique index remains the concurrency authority for one pending invitation per `(tenant_id, email_normalized)`. The insert flush maps the conflict to stable HTTP 409.

### Inconsistent email matching

Control: ADR-006 freezes one normalization helper used before persistence: trim, Unicode casefold, length check, exactly one `@`, no whitespace, non-empty local/domain parts, and basic domain-dot validation. The next invitation-acceptance ticket must reuse this exact helper.

### Partial role mapping

Control: invitation row and all requested role mappings share one SQLAlchemy transaction. The successful response is built only after the transaction scope completes.

### Revoke of accepted or expired invitation

Control: only a currently `pending` invitation whose stored expiry is still in the future may transition to `revoked`. Accepted, revoked, and time-expired rows return the same lifecycle-conflict category.

### Cross-tenant invitation-ID probing

Control: revoke lookup includes both `tenant_id` and `invitation_id`. A caller from another tenant receives non-disclosing 404 rather than learning the invitation's status.

### Invite URL origin injection

Control: the URL base is taken only from typed platform configuration `SERVIQ_PUBLIC_BASE_URL`. The client cannot supply or override the response origin.

## Required automated security evidence

The real PostgreSQL/API suite must prove:

- Owner can create;
- Admin can create;
- same-tenant unauthorized role receives 403;
- foreign tenant cannot list or revoke;
- foreign-tenant requested role is rejected;
- unapproved global system/platform-like role is rejected;
- duplicate normalized pending email returns 409;
- create response contains exactly one token-bearing `inviteUrl`;
- stored value equals SHA-256 of the returned token and is not plaintext;
- expiry is seven days within the small execution-time tolerance;
- logs contain neither plaintext token nor digest;
- list response contains no token, hash, or invite URL;
- pending invitation revokes successfully;
- repeated revoke conflicts;
- accepted invitation cannot be revoked;
- malformed email, empty/duplicate role IDs, and client-supplied token fields fail validation;
- unauthenticated access returns 401.

## Deliberate non-goals

This review does not approve invitation acceptance, email delivery, resend behavior, role editing, membership activation, browser-session implementation, or platform-operator invitation workflows. OPE-285 only creates, lists, and revokes invitation records and returns the one-time URL to the authorized administrator.

## Residual risks and follow-up requirements

The plaintext token necessarily exists briefly in process memory so it can be returned once. Python does not provide deterministic memory zeroization for immutable strings, so the design minimizes lifetime rather than claiming zeroization. The next acceptance ticket must never persist the presented plaintext token and must compare its digest using the same hashing helper and tenant/invitation lifecycle rules.
