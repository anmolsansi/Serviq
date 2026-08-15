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

---

# OPE-287 — Implement member list and role/status update APIs

## The problem in simple terms

After invitation acceptance existed, Serviq could add a teammate to an organization, but an administrator still needed a safe way to see the team and manage an existing member. OPE-287 adds that management layer.

This sounds like a normal list-and-edit screen, but membership administration is one of the easiest places to create a security problem. A bad implementation could let one organization edit another organization's member by guessing a UUID, grant a platform-only role to a tenant user, expose internal OIDC identifiers, or let two administrators simultaneously remove the final Owner and lock the organization out of administration.

OPE-287 therefore treats member management as a tenant-isolation and concurrency problem, not just a CRUD problem.

## APIs added

```text
GET   /api/v1/organizations/{organizationId}/members
PATCH /api/v1/organizations/{organizationId}/members/{membershipId}
```

The list route supports bounded pagination:

```text
limit  = 1..100, default 50
offset = 0 or greater
```

Rows are ordered by `(created_at, id)` so the same database state produces deterministic pages.

The PATCH body can change `roleIds`, `status`, or both. Unknown fields are rejected, duplicate role IDs are rejected, the role list is bounded, and an empty PATCH is rejected.

## Safe member response

The Team & Access UI needs useful workforce information, but it does not need raw identity-provider linkage values.

The response contains:

- membership ID;
- internal user ID;
- email;
- display name;
- active/suspended status;
- role ID, key, and display name.

It deliberately does **not** expose `oidc_issuer` or `oidc_subject`. Those values are internal identity-linking data.

## Authorization

The implementation reuses Serviq's existing effective-capability resolver and requires:

```text
organization.members.manage
```

It does not create a second authorization system based on hard-coded role names in the router. An active Owner/Admin receives this capability from the existing role bootstrap. An ordinary tenant role does not.

A caller who is not an active member of the target organization receives the existing non-disclosing not-found behavior. This avoids confirming whether a foreign tenant or membership exists.

## Tenant isolation

Every target membership lookup includes both:

```text
membership_id = requested UUID
tenant_id     = organization from route
```

That means knowing a real membership UUID from tenant B is not enough to mutate it through a tenant-A URL.

The list repository also filters by the organization tenant ID, so a tenant-A page cannot include tenant-B rows.

## Role safety

A tenant administrator may assign:

- roles owned by the same tenant; or
- the frozen global workforce system roles `owner` and `admin`.

The service rejects:

- a role owned by another tenant;
- a different global system role, including a synthetic platform-operator role used by the attack test;
- duplicate IDs in the request.

Role replacement is explicit. If `roleIds` is supplied, the membership's existing role mappings are replaced by the validated requested set inside the same transaction. If `roleIds` is omitted, roles remain unchanged.

## Protecting the last active Owner

This is the most important correctness rule in OPE-287.

Imagine an organization has exactly two active Owners. Administrator A removes the Owner role from the first membership while Administrator B simultaneously suspends the second membership. If both transactions count Owners before either commits, both might see “two Owners” and both might proceed, leaving zero.

OPE-287 serializes member mutations for one tenant by locking the organization's tenant row with PostgreSQL `FOR UPDATE` before the last-owner decision.

The transaction then asks:

1. Is the target currently active?
2. Does it currently have the global Owner role?
3. Would the requested status or replacement role set stop it from being an active Owner?
4. If yes, how many active Owner memberships exist while the tenant lock is held?

If the answer is one or fewer, the mutation returns:

```text
409 LAST_ACTIVE_OWNER
```

and nothing changes.

Using one tenant row as the serialization point is intentionally conservative. Team administration writes are relatively infrequent, and a simple lock that is easy to audit is preferable to a more clever join-locking scheme that could allow a race.

## Atomic PATCH behavior

Authorization, target membership lookup, role validation, final-owner checking, role replacement, and status mutation happen inside one SQLAlchemy transaction.

If any later validation fails, the previous roles/status remain intact. There is no state where a role replacement committed but the status update did not, or vice versa.

## Important files

### `services/api/app/modules/members/schemas.py`

Defines strict PATCH input and safe member/role response shapes.

### `services/api/app/modules/members/repository.py`

Contains tenant-scoped membership queries, user/role loading, tenant-row locking, active-owner counting, and role replacement persistence.

### `services/api/app/modules/members/service.py`

Owns authorization, role allowlisting, last-owner logic, and the atomic update workflow.

### `services/api/app/modules/members/router.py`

Exposes the two protected routes and stable errors.

### `services/api/tests/integration/test_member_management_api.py`

Exercises the security and lifecycle matrix against real PostgreSQL.

### `docs/security-reviews/OPE-287-member-management.md`

Explains the tenant, role-escalation, response-data, input, atomicity, and concurrency threats in detail.

## What the tests prove

The real PostgreSQL test creates two organizations with deliberately overlapping human-facing values and verifies:

- Owner can list members;
- Admin can list members;
- an ordinary member cannot list or patch;
- pagination is bounded and deterministic;
- tenant-A pages never contain the known tenant-B membership;
- a known tenant-B membership UUID cannot be patched through tenant A;
- tenant A cannot list tenant B;
- valid tenant role replacement succeeds;
- duplicate role IDs fail validation;
- a foreign-tenant role is rejected;
- a platform system role is rejected;
- unknown mass-assignment fields are rejected;
- a non-owner can be suspended;
- removing one of two Owners succeeds;
- the remaining active Owner cannot be suspended;
- the remaining active Owner cannot lose its Owner role;
- rejected final-owner operations leave the persisted row unchanged.

The final PR passed lint, strict type checking, unit tests, Compose validation, the PostgreSQL integration/migration chain, Trivy, dependency audits, CodeQL for JavaScript/TypeScript and Python, and Gitleaks before squash merge.

## What this improves for the product

Serviq now has the backend required for a real Team & Access administration page instead of only invitation issuance. An organization administrator can view workforce membership, change tenant-safe roles, suspend/re-enable access, and do so without risking cross-tenant changes or accidentally deleting the final active Owner.

## What OPE-287 deliberately does not do

It does not add new database tables, change invitation acceptance, change OIDC validation, create platform-operator behavior, or redesign the role catalog. Those remain separate concerns.

---

# OPE-288 — Add reusable tenant-isolation repository test harness

## The problem in simple terms

Serviq is multi-tenant. That means many companies can use the same application and database, but company A must never see or change company B's private records.

Writing one isolation test per feature is necessary, but repeating ad-hoc setup has a hidden weakness: a test can pass for the wrong reason. For example, if tenant A's member is called “Alice” and tenant B's is called “Bob,” a query missing `tenant_id` might still appear correct because the test filtered by a unique name. The test would not actually prove isolation.

OPE-288 creates a reusable adversarial foundation that future domains can build on.

## Deliberately confusing fixture data

`TenantIsolationFixture` gives a test known IDs for:

- tenant A and tenant B;
- an Owner in each tenant;
- an ordinary member in each tenant;
- Owner memberships;
- ordinary memberships;
- one tenant-owned role per tenant.

The seed helper intentionally uses overlapping visible values:

```text
organization display name: Shared Organization
user display name:         Shared Person
user email:                shared-person@example.com
role display name:         Shared Agent
```

The UUID and tenant ownership are therefore the only reliable separators.

The role database key remains tenant-specific because the existing schema requires globally unique keys, but the human-visible role name is still identical.

## Why known foreign UUIDs are important

A secure UI might never show tenant B's UUID to tenant A, but authorization cannot depend on obscurity. An attacker could learn a UUID through logs, copied links, browser history, another vulnerability, or simple disclosure.

The harness therefore gives the test the real tenant-B UUID directly and asks production routes to defend against it.

This is stronger than testing only “the UI does not list foreign rows.”

## Reusable assertions

The support module adds small assertions for three common isolation questions.

### List isolation

```text
assert_list_excludes_foreign(...)
```

Proves a known tenant-B resource ID is absent from tenant-A results.

### Direct get/update/delete attack

```text
assert_foreign_resource_hidden(status_code)
```

Proves the existing Serviq non-disclosing `404` behavior is preserved for a known foreign resource.

### Mutation integrity

```text
assert_value_unchanged(before=..., after=...)
```

Proves a rejected cross-tenant mutation did not quietly alter the tenant-B database row before returning an error.

## Real PostgreSQL instead of mocked tenant filters

The harness inserts rows into the actual migration-created `tenants`, `users`, `roles`, `memberships`, and `membership_roles` tables. The integration test exercises the real FastAPI routes and repositories.

It does **not** mock the repository filter it is supposed to prove.

## Privileged attacks

An isolation test is weaker if it only uses an unprivileged caller. OPE-288 authenticates as tenant A's Owner, a user with meaningful organization/member administration capabilities, and still requires tenant B to remain inaccessible.

That proves “high privilege inside one organization” does not become “global privilege across all organizations.”

The test then reverses the fixture and attacks tenant A as tenant B's Owner, catching accidental assumptions that tenant A is special simply because it was created first.

## Existing domains covered immediately

The first harness application attacks two already-built domains.

### Organization

Tenant-A Owner attempts:

```text
GET   /api/v1/organizations/{tenantB}
PATCH /api/v1/organizations/{tenantB}
```

Both must be hidden, and the tenant-B display name is read before/after to prove the failed PATCH did not mutate it.

### Membership

Tenant-A Owner lists tenant A and must not receive tenant-B membership IDs. The Owner then PATCHes a known tenant-B membership UUID through the tenant-A URL. The request must fail and tenant-B membership status must remain unchanged.

The reverse direction is also tested.

## Files added

### `services/api/tests/support/tenant_isolation.py`

Typed fixture, real-PostgreSQL seed/cleanup, and reusable isolation assertions.

### `services/api/tests/support/README.md`

Explains how later tickets should extend the harness without changing production authorization just to make tests easier.

### `services/api/tests/integration/test_tenant_isolation_harness.py`

Applies the harness to organization and membership read/mutation attacks.

### `services/api/tests/__init__.py` and `services/api/tests/support/__init__.py`

Make test/support packages explicit so static analysis resolves the reusable module exactly once.

### `docs/security-reviews/OPE-288-tenant-isolation-harness.md`

Records the security objective, limitations, privileged attack approach, cleanup rules, and what future domains still need to prove themselves.

## How future domains should use it

A new tenant-owned domain should create one record under tenant A and one under tenant B, preferably with the same visible name/value. It should then use the harness's known foreign IDs to test list, direct read, update/delete, and persisted-state integrity where applicable.

The harness is a foundation, not a magic proof. A future feature still needs domain-specific assertions around its own repository/API behavior.

## What this improves for the product

OPE-288 turns tenant isolation from a repeated testing convention into a reusable security control. It reduces the chance that a future feature appears tenant-safe only because its fixture data happened to be unique, and it gives every later domain a common adversarial vocabulary for testing foreign UUID attacks.

## What OPE-288 deliberately does not do

It does not introduce PostgreSQL Row Level Security, alter production authorization, change API status semantics, change schema, or grant any platform role. Current tenant isolation remains enforced by the application/repository predicates already defined by the architecture.