# Serviq implementation guide — OPE-286 through OPE-295

## Why this document exists

This file explains the implementation work for Linear tickets OPE-286 through OPE-295 in plain language. It is intentionally more explanatory than a normal engineering changelog. A reader should be able to understand what was added, why the change was necessary, how the important pieces work together, what security or reliability problem each decision addresses, and what remains outside the ticket.

The document grows as the tickets are completed. Each ticket keeps its own section so code reviewers, future engineers, product teammates, and non-technical readers can trace the project from workforce invitation completion into the BYOK/LLM gateway foundation.

---

# OPE-286 — Implement invitation acceptance API

## The problem in simple terms

OPE-285 let an authorized organization administrator create an invitation link for a workforce user. The database stored only a one-way hash of the random invitation token, which meant Serviq could safely issue the link without keeping a reusable plaintext secret.

That was only the first half of the workflow. OPE-286 adds the second half: the invited person presents the one-time token after signing in, Serviq proves that the signed-in person's verified email is the email the administrator invited, and Serviq turns that invitation into real tenant membership and role assignments exactly once.

The difficult part is not the HTTP endpoint itself. The difficult part is guaranteeing all of the following at the same time:

- a stolen or forwarded link cannot add a different verified user;
- the token is never stored or logged in plaintext;
- an expired, revoked, or already-used invitation cannot be reused;
- a corrupted invitation cannot smuggle in a role from another tenant;
- two requests racing with the same token cannot both succeed;
- membership, roles, and invitation status cannot become partially updated;
- an existing membership is handled predictably instead of duplicated or overwritten.

## Frozen API

OPE-286 adds:

```text
POST /api/v1/invitations/accept
```

The request is:

```json
{
  "token": "one-time-invitation-token"
}
```

Unknown body fields are rejected. The token field is represented by Pydantic `SecretStr`, which makes accidental object representation safer. Serviq's global request-validation error handler reports only field names and validation messages, not the submitted value, so a malformed request does not echo the bearer token.

The successful response uses the existing safe `InvitationView`. It shows the accepted invitation metadata and roles but has no token, token hash, or invite URL field.

## Verified identity requirement

Invitation acceptance does not trust an email typed into the request. The route requires two server-owned values:

1. the internal Serviq `user_id`; and
2. the `VerifiedWorkforceIdentity` produced only after OIDC token verification.

A small principal helper now reads the verified identity from trusted request state, just like the existing principal helper reads the internal user ID. This does not change OIDC cryptography or token parsing.

The identity must contain:

```text
email_verified = true
email = present
```

The email is then passed through the exact OPE-285 invitation normalization helper. That means creation and acceptance cannot disagree because one lowercases differently or trims differently.

## Token handling

The service receives the `SecretStr`, extracts the plaintext only long enough to call the existing `hash_invitation_token()` helper, then drops that local reference.

The repository never receives plaintext. Its lookup parameter is the SHA-256 digest:

```text
submitted plaintext token
        ↓
existing hash helper
        ↓
token_hash
        ↓
SELECT invitation WHERE token_hash = ... FOR UPDATE
```

The database still contains no plaintext-token column.

Python cannot guarantee that a string's memory has been physically zeroed after use, so the implementation does not make that false claim. Instead it minimizes how many functions see plaintext and how long the service retains a reference to it.

## Why `FOR UPDATE` matters

A normal database read would create a race:

1. request A reads `pending`;
2. request B reads `pending` before A commits;
3. A accepts;
4. B also thinks acceptance is allowed.

OPE-286 changes the acceptance lookup to use PostgreSQL row locking with `FOR UPDATE`.

Only one transaction can own the invitation row lock at a time. The first request completes the membership/role/status transaction and commits. The second request then continues, sees `status='accepted'`, and receives the same safe rejection used for other unusable invitations.

This makes the invitation row the serialization point for that one bearer token.

## Fail-closed invitation validation

Serviq does not trust only the `status` column. Acceptance requires all of these facts to agree:

```text
invitation exists for token_hash
status == pending
revoked_at is null
accepted_at is null
accepted_by_user_id is null
expires_at is later than now
normalized verified caller email == invitation email_normalized
```

If any fact fails, Serviq returns the same public `INVITATION_ACCEPTANCE_REJECTED` error. Invalid token, wrong email, expired token, revoked invitation, already accepted invitation, or inconsistent/corrupted state therefore do not become separate token-validity oracles.

Missing or unverified caller email returns `VERIFIED_EMAIL_REQUIRED`, because that describes the caller's own authentication assurance rather than revealing invitation state.

## Revalidating requested roles

The invitation was validated when it was created, but acceptance happens later. Data could have been manually corrupted, a migration could have changed something, or a role could no longer satisfy the assignability rule.

Acceptance therefore loads every role attached to the invitation and runs the same OPE-285 tenant-safe role policy again.

Allowed roles remain:

- roles owned by the invitation's tenant; or
- the explicitly approved global workforce system roles from the existing allowlist.

A foreign-tenant or otherwise unassignable role causes the whole acceptance to fail before membership state is changed.

## Existing membership behavior: ADR-007

The ticket required duplicate-membership behavior to be explicit. The Architecture says acceptance "creates/activates membership," while the database enforces exactly one membership row per `(tenant_id, user_id)`.

ADR-007 freezes the behavior:

### No existing membership

Create one active membership and set:

```text
created_by_invitation_id = accepted invitation ID
```

### Existing active membership

Reuse the same membership. Do not replace it. Do not rewrite its origin field. Preserve existing roles and add only missing roles from the invitation.

### Existing suspended membership

Reactivate that same membership because the frozen Architecture explicitly says acceptance can activate membership. The valid invitation is the explicit tenant-issued authorization for that reactivation. Preserve existing roles and add only missing invited roles.

This avoids both dangerous extremes: silently destroying existing access state or ignoring the frozen activation behavior.

## Cross-module transaction design

The Architecture says modules should call exported service interfaces rather than another module's repository.

For that reason, the invitation service does not directly manipulate membership tables. The tenancy module now exports `activate_membership_from_invitation()`.

That tenancy service:

- locks the exact existing membership row when present;
- creates or activates the membership;
- reads current membership-role IDs;
- adds only missing invited role mappings;
- flushes but does **not** commit.

The invitation service owns the outer transaction. Therefore this sequence is one atomic unit:

```text
lock invitation
validate lifecycle/email
revalidate invitation roles
create or activate membership
add missing membership-role mappings
set accepted_by_user_id
set accepted_at
set invitation status = accepted
commit once
```

If role mapping or any later database operation fails, SQLAlchemy rolls the transaction back. A newly created membership disappears again, a suspended membership stays suspended, partial role mappings disappear, and the invitation remains pending.

## New and changed code

### `docs/architecture-decisions/ADR-007-invitation-existing-membership-acceptance.md`

Documents the duplicate/existing membership rule, concurrency model, and failure behavior before implementation.

### `services/api/app/core/principal.py`

Adds the trusted dependency that exposes `VerifiedWorkforceIdentity` from server-owned request state. OIDC validation itself is unchanged.

### `services/api/app/modules/tenancy/repository.py`

Adds the exact persistence helpers needed for invitation-driven membership activation: row locking, new membership staging, existing role-ID lookup, and missing role mapping insertion.

### `services/api/app/modules/tenancy/service.py`

Adds the exported cross-module service for create/reactivate/reuse membership behavior. It deliberately does not commit so the invitation service retains transaction ownership.

### `services/api/app/modules/invitations/schemas.py`

Adds a strict secret-aware accept request model.

### `services/api/app/modules/invitations/errors.py`

Adds safe acceptance errors that do not disclose whether a token was valid for another state or user.

### `services/api/app/modules/invitations/repository.py`

Adds digest-only invitation lookup with PostgreSQL `FOR UPDATE`.

### `services/api/app/modules/invitations/service.py`

Implements verified-email matching, token hashing, lifecycle checks, role revalidation, membership activation, and the accepted transition in one transaction.

### `services/api/app/modules/invitations/router.py`

Adds the public acceptance endpoint while preserving all OPE-285 organization invitation routes unchanged.

### `services/api/app/main.py`

Registers the new acceptance router.

### `services/api/tests/integration/test_invitation_acceptance_api.py`

Adds real-PostgreSQL tests for the ticket's security, lifecycle, transaction, and concurrency requirements.

### `docs/security-reviews/OPE-286-invitation-acceptance.md`

Records the required security review of bearer-secret handling, token probing, verified identity, replay, tenant roles, existing membership state, and rollback behavior.

## What the automated test proves

The integration matrix verifies:

- matching verified email succeeds;
- case/whitespace normalized verified email still matches;
- repeated use of the same token fails;
- wrong verified email fails without consuming the invitation;
- unverified email fails;
- a completely invalid token fails safely;
- revoked, accepted, and expired invitations cannot be used;
- a deliberately corrupted invitation pointing at a foreign tenant's role is rejected;
- two concurrent requests produce exactly one success and one rejection;
- the concurrent case leaves one membership and one role mapping, not duplicates;
- a suspended membership is reactivated without deleting its existing role;
- a forced role-mapping failure rolls back a newly created membership and leaves the invitation pending;
- representative plaintext tokens and token hashes do not appear in captured logs or acceptance error bodies.

## What this improves for the product

Before OPE-286, an administrator could issue an invitation but there was no safe server-side conversion from invitation to access. After OPE-286, Serviq has a complete one-time workforce invitation protocol: creation protects the secret, and acceptance protects identity, tenant scope, roles, replay, concurrency, and atomicity.

This is a prerequisite for a usable Team & Access experience because a real invited teammate can now join an organization with the roles the administrator selected.

## What OPE-286 deliberately does not do

It does not:

- change invitation creation/list/revoke behavior;
- change the seven-day expiry;
- send invitation email;
- implement resend;
- change OIDC token validation;
- redefine roles or permissions;
- implement general member-management PATCH behavior;
- grant platform-operator access;
- add provider/LLM functionality.

Those concerns remain separate tickets.