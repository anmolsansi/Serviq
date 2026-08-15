# ADR-007 — Invitation acceptance with an existing membership

## Status

Accepted for OPE-286.

## Context

OPE-286 must convert a valid workforce invitation into an active tenant membership and the invitation's requested role assignments in one transaction. The frozen Architecture says invitation acceptance "creates/activates membership and assigned roles transactionally," while the ticket requires duplicate-membership behavior to be explicit before implementation.

The `memberships` table has a unique `(tenant_id, user_id)` constraint and only two statuses: `active` and `suspended`. A user may therefore already have exactly one membership for the invited tenant when they present a valid invitation.

This ADR clarifies the implementation behavior without changing the database, invitation expiry, role model, OIDC validation, or token-hashing contract.

## Decision

A valid invitation is an explicit tenant-authorized grant for the verified email address named by that invitation.

When acceptance reaches the membership step:

1. **No membership exists**: create one with `status='active'` and `created_by_invitation_id` equal to the accepted invitation ID.
2. **An active membership already exists**: reuse that membership. Do not replace it and do not rewrite `created_by_invitation_id`.
3. **A suspended membership already exists**: reactivate that exact membership by setting `status='active'` and updating `updated_at`. This follows the frozen Architecture language that acceptance "creates/activates membership." The invitation itself is the explicit authorization for that activation.
4. Preserve every existing membership-role mapping. Add only invitation-requested mappings that are missing.
5. Never remove or replace existing roles during acceptance.
6. Revalidate every invitation role against the same tenant-safe assignability rule used during invitation creation before creating or reactivating membership state.
7. Membership creation/reactivation, missing role mappings, and the invitation `accepted` transition share one database transaction.

## Concurrency rule

Acceptance locks the invitation row selected by `token_hash` using PostgreSQL `FOR UPDATE`. That row is the serialization point for one bearer invitation. The first transaction that validates and accepts it changes status to `accepted`; a concurrent waiter sees the committed non-pending status and fails safely.

The unique `(tenant_id, user_id)` membership constraint and unique `(membership_id, role_id)` membership-role constraint remain database backstops.

## Failure behavior

Invalid token, wrong verified email, missing/unverified email, expired/revoked/already-accepted lifecycle, corrupted role assignments, or a failed membership-role write causes the transaction to fail closed. No partial new membership, reactivation, role mapping, or accepted invitation state may remain.

Public errors intentionally do not distinguish whether a supplied bearer token was syntactically valid but belonged to another email or had a non-acceptable lifecycle. This reduces token-validity disclosure.

## Security rationale

Silently replacing an existing membership would risk deleting legitimate access. Silently retaining a suspended state would contradict the Architecture's explicit activation behavior and make a newly issued valid invitation unusable. Reactivating the same row only after verified-email and valid-invitation checks preserves identity continuity while requiring an explicit tenant-issued invitation.

## Scope

This ADR applies only to OPE-286 invitation acceptance. It does not define member-management PATCH behavior, administrative unsuspension outside invitation acceptance, invitation resend, or platform-operator access.