# ADR-006 — Workforce invitation normalization, secret, URL, and assignable-role policy

## Status

Accepted for OPE-285.

## Context

The invitation schema is already frozen and stores only `token_hash`, but OPE-285 has explicit stop conditions for four implementation details that were not yet frozen: email normalization, token hashing, public invite URL construction, and which role IDs may be assigned through an invitation.

These choices affect security and interoperability, so they are recorded before route/service code.

## Decision

### Email normalization

For Production V1 workforce invitations:

1. Trim leading/trailing Unicode whitespace.
2. Apply Unicode `casefold()` to the complete address.
3. Require total normalized length 3–320 characters, matching the database constraint.
4. Reject whitespace inside the normalized address.
5. Require exactly one `@`, with a non-empty local part and non-empty domain.
6. Require the domain to contain no leading/trailing dot and no empty dot-separated label.

The exact normalized result is persisted in `organization_invitations.email_normalized` and is the value used by the pending-invite uniqueness rule.

This is intentionally a deterministic Serviq identity-matching normalization rule, not a claim that all possible RFC mailbox syntax is supported. Expanding accepted address syntax requires an explicit follow-up decision so invitation acceptance uses the same rule.

### Invitation token generation

Use Python's `secrets.token_urlsafe(32)`. The argument requests 32 cryptographically secure random bytes before URL-safe encoding, providing 256 bits of random secret material.

No pseudo-random generator, timestamp, UUID, email, tenant ID, or deterministic value may be used as an invitation bearer secret.

### Token hashing

Immediately hash the plaintext token with SHA-256 over its UTF-8 bytes and persist only the lowercase hexadecimal digest.

This is appropriate for the invitation token because it is a uniformly random 256-bit bearer secret rather than a human-chosen password. The security goal is to avoid retaining a usable bearer credential if the database is read. A password-style slow KDF is not required for this high-entropy random token.

The plaintext token and token hash are both classified as sensitive for logging. Neither may be written to logs, traces, metrics, audit metadata, error messages, or list responses.

### Invite URL

Build the one-time create-response URL from the frozen `SERVIQ_PUBLIC_BASE_URL` configuration:

```text
{SERVIQ_PUBLIC_BASE_URL without trailing slash}/invite?token={URL-encoded plaintext token}
```

The plaintext token appears only in this successful POST response. It is not reconstructable later from storage, so GET invitation responses never include `inviteUrl`.

### Assignable invitation roles

A requested role ID is assignable only when one of these conditions is true:

1. the role is owned by the target tenant (`roles.tenant_id == target tenant`); or
2. it is one of the explicitly approved global workforce system roles from CCR-005: `owner` or `admin`.

A role is rejected when:

- it belongs to another tenant;
- it is any other global role, even if `is_system = true`;
- it is a global non-system role;
- it does not exist.

This allowlist prevents future platform/internal system roles from becoming assignable merely because they are stored in the same RBAC table. Platform-operator access remains a separate trust boundary.

### Member-management capability

Create, list, and revoke operations require the exact CCR-005 capability:

```text
organization.members.manage
```

The caller must also have an active membership in the target organization.

### Expiry and revoke behavior

- New invitations expire exactly seven days after creation using an injected/default UTC clock.
- Only `pending` invitations may transition to `revoked`.
- Re-revoking an already-revoked invitation is a conflict, not an idempotent success.
- Accepted and expired invitations also return the same lifecycle-conflict category.
- Cross-tenant or inaccessible invitation IDs use non-disclosing not-found behavior.

## Consequences

- Invitation acceptance in the next ticket must reuse the same email-normalization and token-hash helpers rather than define new rules.
- A plaintext token cannot be retrieved after the create response is lost.
- Adding a new globally assignable workforce role requires updating the explicit allowlist/contract.
- No email delivery behavior is introduced by this ADR.
