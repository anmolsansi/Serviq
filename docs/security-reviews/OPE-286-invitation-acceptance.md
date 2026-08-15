# OPE-286 — Invitation acceptance security review

## Scope reviewed

This review covers only `POST /api/v1/invitations/accept` and the database transition that turns one pending workforce invitation into an active membership plus role mappings.

## Assets at risk

- Invitation bearer token.
- The tenant named by the invitation.
- The verified workforce identity accepting it.
- Membership activation state.
- RBAC role mappings.
- Cross-tenant isolation.

## Threats and controls

### Bearer-token disclosure

**Risk:** A plaintext invitation token in logs, database rows, exceptions, validation output, or responses could let another party reuse the invitation.

**Controls:**

- Request model uses `SecretStr`.
- Existing global validation handling returns only field/message metadata, never submitted input values.
- Service extracts plaintext only to hash it with the existing SHA-256 helper, then drops the local reference immediately.
- Repository lookup receives only `token_hash`.
- No acceptance response contains token or hash.
- Tests assert representative plaintext tokens and their digests never appear in captured logs or error payloads.

**Residual:** Python strings cannot be reliably zeroized. The implementation minimizes reference lifetime but does not claim memory zeroization.

### Token probing / validity oracle

**Risk:** Different public errors for invalid token, wrong email, expired, revoked, accepted, or corrupted-role invitations could expose state to an attacker.

**Control:** All of those cases map to the same `INVITATION_ACCEPTANCE_REJECTED` response. Missing or unverified caller email is separate because it describes the caller's own authentication assurance rather than invitation state.

### Wrong-person acceptance

**Risk:** Possession of a forwarded or stolen link could add the wrong workforce user to a tenant.

**Controls:**

- Route requires a server-owned internal workforce user ID.
- Route separately requires the cryptographically verified `VerifiedWorkforceIdentity` produced by the OIDC validation boundary.
- `email_verified` must be true and email must be present.
- Caller email is normalized with the exact same helper used by invitation creation.
- Normalized caller email must equal persisted `email_normalized`.

### Replay / double acceptance

**Risk:** Two concurrent requests could both see `pending`, create duplicate access, or report two successes.

**Controls:**

- Lookup selects the unique `token_hash` row using PostgreSQL `FOR UPDATE`.
- The first transaction owns the row lock through membership/roles and accepted-state update.
- A concurrent waiter resumes only after commit and then sees non-pending state, so it fails.
- Database uniqueness on `(tenant_id,user_id)` and `(membership_id,role_id)` remains defense in depth.
- Real PostgreSQL test sends two acceptance requests concurrently and requires exactly one `200` and one rejection plus one membership/role set.

### Corrupted or cross-tenant role assignment

**Risk:** An invitation row may have been corrupted, manually edited, or linked to a role that is no longer valid for the target tenant.

**Controls:**

- Acceptance loads invitation-requested role IDs and re-runs the OPE-285 assignability rule.
- Tenant-owned roles must belong to the invitation tenant.
- Approved global workforce roles remain limited to the existing allowlist.
- Missing, foreign, or otherwise unassignable role mappings reject acceptance before membership state changes.
- Integration test inserts a deliberately foreign-tenant invitation-role mapping and verifies fail-closed behavior.

### Existing membership state

**Risk:** Invitation acceptance could overwrite an existing membership or discard roles.

**Controls:** ADR-007 freezes exact behavior. New membership is created active; existing active membership is reused; suspended membership is reactivated because Architecture explicitly freezes create/activate semantics. Existing role mappings are preserved and only missing invited mappings are added. Existing `created_by_invitation_id` is never rewritten.

### Partial transaction

**Risk:** Membership could be created/reactivated but role mapping or invitation state update could fail afterward.

**Controls:** The invitation service owns one SQLAlchemy transaction. The tenancy activation helper does not commit. Membership, role mappings, and invitation accepted fields are flushed inside the same transaction. A forced role-mapping failure test verifies the invitation stays pending and a newly staged membership does not remain.

### Lifecycle ambiguity

**Risk:** Partially inconsistent invitation columns might accidentally pass based on status alone.

**Controls:** Acceptance requires all of: `status='pending'`, `revoked_at IS NULL`, `accepted_at IS NULL`, `accepted_by_user_id IS NULL`, unexpired timestamp, and matching normalized email. Ambiguity fails closed.

## Cross-tenant review

The acceptance route accepts no client-supplied tenant ID. Tenant identity comes only from the locked invitation row found by digest. Role revalidation is performed against that exact tenant. Membership creation/activation uses that same tenant ID. This prevents a caller from redirecting a valid invitation token toward a different organization.

## Review conclusion

The OPE-286 design preserves the existing secret, identity, tenant, and RBAC boundaries. Required acceptance is one-time under PostgreSQL concurrency, verified-email bound, tenant-role revalidated, and atomic. No blocker remains for merge if the permanent CI and Security workflows pass.