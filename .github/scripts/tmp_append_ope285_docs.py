from pathlib import Path

focused = Path("docs/OPE_279_285_IMPLEMENTATION_GUIDE.md")
focused_marker = "# OPE-285 — Implement invitation create, list, and revoke APIs"
focused_section = r'''

---

# OPE-285 — Implement invitation create, list, and revoke APIs

## What problem this ticket solves

An organization administrator needs a safe way to invite another workforce user before that person has a Serviq membership. This sounds like a normal CRUD feature, but invitations are security-sensitive because an invitation carries two forms of authority:

1. a bearer secret that will later prove possession of the invitation; and
2. requested roles that determine what the new member may eventually do.

OPE-285 therefore treats invitation management as an authorization and secret-handling workflow, not just a database form.

## Stop conditions resolved before implementation

The database schema already existed from OPE-278, but the ticket correctly identified four missing implementation contracts. ADR-006 freezes all four before API code:

- deterministic invitation-email normalization;
- secure token generation and one-way hashing;
- the one-time public invitation URL format;
- exactly which role IDs may be assigned through an invitation.

The same ADR also freezes the member-management capability and revoke-conflict semantics so create/list/revoke cannot drift apart.

## Email normalization

Serviq stores and compares the normalized email rather than whichever capitalization or surrounding spaces the administrator typed.

The helper performs this sequence:

1. trim leading/trailing Unicode whitespace;
2. Unicode `casefold()` the complete address;
3. require normalized length 3–320, matching the database constraint;
4. reject whitespace inside the address;
5. require exactly one `@`;
6. require non-empty local and domain parts;
7. reject a domain beginning/ending with a dot or containing an empty dot-separated label.

For example:

```text
" Invitee@Example.COM "
        ↓
"invitee@example.com"
```

This is intentionally one deterministic Serviq matching rule. It is not an attempt to accept every historical RFC mailbox syntax. The future acceptance flow must reuse this helper so create and accept never disagree about who an invitation belongs to.

## Token generation

`generate_invitation_token()` uses:

```text
secrets.token_urlsafe(32)
```

The `32` requests 32 bytes, or 256 bits, of cryptographically secure random material before URL-safe encoding.

The token is not based on:

- UUIDs;
- timestamps;
- email addresses;
- tenant IDs;
- Python's normal pseudo-random generator.

That matters because the future acceptance URL is a bearer credential. Anyone who possesses a valid unexpired token may later present it to the acceptance endpoint.

## Why SHA-256 is used here

The plaintext token is immediately hashed with SHA-256 and only the lowercase hexadecimal digest is given to the ORM/database layer.

A slow password hash is designed to compensate for weak, human-chosen passwords. This invitation secret is different. It begins with 256 bits of random entropy. The security requirement is therefore to avoid storing a usable bearer credential, while retaining a deterministic verifier for the next ticket.

The schema contains `token_hash` and no plaintext-token column. OPE-285 does not add one.

Both the plaintext token and its hash are considered sensitive for logs. Knowing the hash should not be necessary for normal operational logging, so it is not logged either.

## Plaintext lifetime

The service deliberately does **not** generate a token as soon as the request arrives.

It first:

1. proves the caller has an active membership in the organization;
2. proves the caller has `organization.members.manage`;
3. resolves and validates all requested role IDs.

Only then does it generate the plaintext token, hash it immediately, and create the invitation row.

This minimizes how long sensitive plaintext exists in process memory. Python strings cannot be reliably zeroized after use, so the implementation does not claim memory zeroization. It reduces lifetime and prevents the token from crossing unnecessary code boundaries.

## One-time invite URL

After the database transaction succeeds, the create service builds:

```text
{SERVIQ_PUBLIC_BASE_URL}/invite?token={URL-encoded-token}
```

The origin comes from typed platform configuration, not from client input.

Only the successful POST response uses `InvitationCreateView`, which contains `inviteUrl`. The normal `InvitationView` used by GET and DELETE has no invite URL, plaintext token, or token hash.

Because the database stores only the digest, Serviq cannot reconstruct the invite URL later. This is intentional. The administrator receives the bearer URL once and future resend/email-delivery behavior must be designed separately.

## Role assignability

A role ID is invitation-assignable only when:

```text
role belongs to target tenant
OR
role is approved global workforce system role "owner" or "admin"
```

The query rejects:

- another tenant's role;
- missing roles;
- global non-system roles;
- any other global system role, even if `is_system=true`.

The final rule is important defense in depth. A future internal or platform-related role cannot suddenly become assignable through invitations merely because it happens to live in the same `roles` table. Global assignability is an explicit allowlist, not a side effect of `is_system`.

## Authorization

All three endpoints require the exact CCR-005 capability:

```text
organization.members.manage
```

The service reuses OPE-282's active-membership/capability resolver.

Authorization behavior is:

- no active membership in target tenant -> non-disclosing 404;
- active membership without member-management capability -> 403;
- Owner/Admin -> permitted because CCR-005 grants that capability;
- platform-operator access is not introduced here.

## Invitation creation transaction

POST creation runs one SQLAlchemy transaction:

1. resolve active membership/capability;
2. validate all requested roles;
3. generate secure plaintext token;
4. hash token immediately;
5. calculate `expires_at = now + 7 days`;
6. insert pending invitation with only `token_hash`;
7. flush so PostgreSQL enforces pending-email and hash uniqueness;
8. insert all invitation-role mappings;
9. flush mappings;
10. leave transaction successfully;
11. construct the one-time `inviteUrl` for the response.

If any role mapping or database constraint fails, the transaction cannot leave a partially-created invitation behind.

The PostgreSQL partial unique index remains the concurrency authority for "one pending invitation per tenant and normalized email." A duplicate maps to HTTP 409.

## Safe list behavior

GET is tenant-scoped and returns only safe metadata:

- invitation ID;
- normalized email;
- status;
- expiry;
- requested role IDs/keys/display names;
- inviter user ID;
- accepted user/timestamps when present;
- created/updated timestamps.

The serializer has no place for token, token hash, or invite URL. This is stronger than remembering to delete a secret field from a generic database serialization.

## Revoke behavior

DELETE looks up the invitation using both target tenant ID and invitation ID.

Only an invitation that is:

```text
status == pending
AND
expires_at > current time
```

may become revoked.

A successful revoke sets:

- `status = revoked`;
- `revoked_at = now`;
- `updated_at = now`.

Already revoked, accepted, or time-expired invitations return the same 409 lifecycle conflict. Re-revoke is intentionally not reported as a successful idempotent operation because the repository had no frozen idempotent-delete contract.

A user from another tenant receives non-disclosing 404 even if they know a valid invitation UUID.

## API routes

OPE-285 adds exactly:

```text
GET    /api/v1/organizations/{organizationId}/invitations
POST   /api/v1/organizations/{organizationId}/invitations
DELETE /api/v1/organizations/{organizationId}/invitations/{invitationId}
```

They reuse Serviq's `{data: ...}` and `{error: {...}}` envelopes.

Important public failures are:

- unauthenticated -> 401;
- inaccessible tenant/invitation -> 404;
- active member without capability -> 403;
- unassignable role -> 422;
- duplicate pending normalized email -> 409;
- invalid revoke lifecycle -> 409;
- malformed email/body/duplicate role IDs/client-supplied token field -> 422.

## Real PostgreSQL and API security tests

The integration suite creates two tenants plus Owner, Admin, support-only, and foreign-tenant users. It also creates:

- one tenant-owned role in Tenant A;
- one foreign Tenant B role;
- one support-only role;
- one deliberately unapproved global `is_system=true` role representing internal/platform-like scope.

The suite verifies:

### Create and secret handling

- Owner can create an invitation;
- input email is normalized;
- requested tenant role plus approved global Admin role are returned;
- create response contains one token-bearing `inviteUrl`;
- the query token can be extracted exactly once from that URL;
- database `token_hash` equals SHA-256 of the returned token;
- stored hash is not the plaintext token;
- expiry is seven days within a tiny execution-time tolerance;
- neither plaintext token nor hash appears in captured logs.

### Authorization and roles

- Admin can create;
- support-only member receives 403;
- foreign user cannot list/revoke Tenant A invitations;
- Tenant B role is rejected for a Tenant A invitation;
- unapproved global system/platform-like role is rejected.

### Conflict and serialization

- duplicate normalized pending email returns 409;
- list response includes neither token, hash, nor `inviteUrl`;
- revoke response includes neither token, hash, nor `inviteUrl`.

### Lifecycle

- pending invitation can be revoked;
- revoke timestamp is returned;
- repeated revoke returns lifecycle conflict;
- an accepted invitation inserted as a fixture cannot be revoked as pending.

### Input safety

- malformed email fails validation;
- empty role list fails;
- duplicate role IDs fail;
- a client attempt to supply a `token` field fails because unknown fields are forbidden;
- unauthenticated list fails with 401.

## Premium security review

`docs/security-reviews/OPE-285-invitation-management.md` records the explicit review of tenant access, privilege assignment, global-role allowlisting, entropy, hashing, secret lifetime, serializers, log redaction, duplicate-pending behavior, transaction atomicity, lifecycle enforcement, cross-tenant probing, and public URL origin.

The permanent OPE-272 Security workflow still has to pass on the final PR head. The written review is additional design evidence, not a replacement for automated scanning.

## What this improves

After OPE-285, an authorized Serviq organization administrator can safely create, inspect, and revoke workforce invitation records without storing a usable invitation secret or exposing another tenant's invitations. Role assignment is validated before persistence, and the database plus application layer jointly enforce one live invite per normalized email.

## What remains

OPE-285 deliberately does not accept invitations, create memberships from invitations, send invitation email, resend links, or implement browser session population. The next acceptance ticket must reuse the exact normalization and token-hash helpers frozen here so create and acceptance form one consistent security protocol.
'''
if focused_marker not in focused.read_text():
    focused.write_text(focused.read_text() + focused_section)

build = Path("docs/SERVIQ_BUILD_GUIDE.md")
build_marker = "# OPE-285 — secure invitation create, list, and revoke APIs"
build_section = r'''

---

# OPE-285 — secure invitation create, list, and revoke APIs

OPE-285 adds workforce invitation management without ever storing a plaintext invitation token. The new routes are GET/POST `/api/v1/organizations/{organizationId}/invitations` and DELETE `/api/v1/organizations/{organizationId}/invitations/{invitationId}`.

ADR-006 resolves the ticket's security stop conditions before implementation. Serviq now has one deterministic invitation-email normalization rule, 256-bit `secrets.token_urlsafe(32)` bearer-token generation, SHA-256 storage of the random token, a one-time `{SERVIQ_PUBLIC_BASE_URL}/invite?token=...` response URL, and an explicit assignable-role policy. Tenant-owned roles are allowed, while global roles are assignable only when they are the approved workforce `owner` or `admin` roles. Foreign and other global system/platform-like roles are rejected.

All invitation operations require an active target-tenant membership plus `organization.members.manage`. Missing membership is non-disclosing 404; a same-tenant member without the capability receives 403.

Create validates authorization and roles before generating the secret, then hashes the token immediately. Invitation metadata and all role mappings are one transaction, and PostgreSQL's partial unique index remains the authority for one pending invitation per normalized tenant/email. The invitation expires exactly seven days after creation. Only the successful create response contains `inviteUrl`; normal list/revoke serializers contain no token, token hash, or invite URL.

Revoke is tenant-scoped and pending-only. Accepted, already-revoked, or time-expired invitations return lifecycle conflict rather than being treated as pending. A foreign tenant cannot probe an invitation ID through revoke.

Real PostgreSQL/API tests verify Owner/Admin creation, support denial, foreign-tenant isolation, foreign/global-platform role rejection, duplicate pending-email conflict, normalized email, one-time token URL, stored SHA-256 digest, seven-day expiry, log redaction, secret-free list/revoke responses, successful pending revoke, repeated-revoke conflict, accepted-invite conflict, strict input validation, and unauthenticated access.

The premium security review is recorded at `docs/security-reviews/OPE-285-invitation-management.md`. The full non-technical implementation narrative is in `docs/OPE_279_285_IMPLEMENTATION_GUIDE.md`.

This ticket does not implement invitation acceptance or email delivery. Those later workflows must reuse the exact normalization and hashing helpers established here.
'''
if build_marker not in build.read_text():
    build.write_text(build.read_text() + build_section)
