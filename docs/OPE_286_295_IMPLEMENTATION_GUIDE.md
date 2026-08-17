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

---

# OPE-289 — Create provider and model metadata migration

## The problem in simple terms

Serviq's AI gateway needs to know two different kinds of information:

1. **How a tenant connects to an AI provider**, such as OpenAI or Anthropic.
2. **Which stable Serviq model name points to which real provider model**, so the rest of the product can ask for something like `support-default` without hard-coding `gpt-*` or `claude-*` names everywhere.

The dangerous shortcut would be to put the provider API key directly into the normal PostgreSQL row. OPE-289 deliberately does not do that. PostgreSQL stores only provider metadata and an opaque `secret_ref`. The actual secret is handled by the secret-store boundary added in OPE-290.

This separation is important because normal relational tables are copied into backups, inspected during debugging, queried by administrators, and often included in analytics or database tooling. A provider API key should not become ordinary application data.

## What was built

Migration `20260815_0005_provider_model_metadata.py` adds two tenant-owned tables.

### `provider_connections`

A provider connection records:

- its UUID;
- owning `tenant_id`;
- provider type: `openai`, `anthropic`, `gemini`, or `openrouter`;
- human-readable `display_name`;
- opaque `secret_ref`;
- lifecycle status: `untested`, `active`, `invalid`, or `disabled`;
- optional `last_tested_at`;
- optional safe `last_error_code`;
- the internal user who created it;
- created/updated timestamps.

The database enforces one display name per tenant and indexes `(tenant_id, provider, status)` for later provider-management and routing queries.

The important security property is what is **not** present: there is no plaintext API-key column.

### `model_configurations`

A model configuration records:

- its UUID;
- owning tenant;
- the provider connection it uses;
- stable tenant-scoped alias;
- real upstream provider model string;
- purpose: `generation`, `embedding`, or `rerank`;
- enabled/disabled state;
- created/updated timestamps.

The alias is unique inside a tenant. This is the key abstraction that allows later domain code to say “use the support model” rather than depending directly on a provider's product naming.

## Why the database owns these rules

Application validation gives friendly errors, but it is not enough for data integrity. Background jobs, migrations, admin scripts, future services, or a programming mistake could bypass one application endpoint.

OPE-289 therefore puts the important constraints in PostgreSQL itself:

- provider values are allowlisted;
- provider status values are allowlisted;
- aliases/display names/upstream model names have non-empty bounded lengths;
- provider connections must belong to real tenants;
- creator IDs must point to real users;
- model configurations must point to real provider connections;
- tenant/display-name and tenant/alias uniqueness are database-enforced;
- deletes are restricted when referenced metadata would become invalid.

The migration also contains a real downgrade, so the two tables and their indexes can be removed in dependency-safe order.

## What the tests prove

The database integration tests run against real PostgreSQL, not SQLite. They verify the new tables exist at migration head, important constraints reject invalid data, uniqueness is tenant-aware, foreign keys are enforced, and the migration chain can upgrade and downgrade safely.

During final clean-branch validation, the schema expectation test initially still described the pre-OPE-289 database. CI caught that stale test contract. A separate micro commit updated the expected schema instead of weakening the migration.

## What this improves

OPE-289 creates the persistence foundation for tenant BYOK provider management and stable model aliases while keeping credential material outside ordinary relational data.

For a non-technical analogy, PostgreSQL now stores the **label on the key cabinet** and the **reference number for the key**, but not the key itself.

## What is intentionally not built

This ticket does not encrypt/store the API key, expose provider CRUD endpoints, call an AI provider, test connectivity, resolve aliases at runtime, perform fallback, or execute an agent. Those are separate trust and behavior boundaries.

## Completion evidence

- Linear: OPE-289 — Done.
- GitHub issue: #101.
- Final merged PR: #116.
- Final implementation is on `main`.

---

# OPE-290 — Implement tenant secret adapter and local encrypted store

## The problem in simple terms

OPE-289 intentionally stores only a `secret_ref`. Something still needs to securely turn that reference into the tenant's actual provider API key when an authorized server operation needs it.

OPE-290 creates that boundary.

The most important design decision is that business code does not know whether a secret lives in a local encrypted file today or a managed cloud secret service later. It talks to one small interface.

## The `TenantSecretStore` contract

The server-side protocol has only three operations:

```text
put_secret(tenant_id, plaintext) -> secret_ref
get_secret(tenant_id, secret_ref) -> plaintext
delete_secret(tenant_id, secret_ref)
```

Every operation requires the tenant UUID. The tenant is therefore part of the lookup boundary rather than just metadata stored next to the secret.

A caller holding a valid secret reference from tenant B cannot retrieve it while operating as tenant A. The local adapter returns the same safe “not found/unavailable” behavior instead of turning the reference into a cross-tenant credential oracle.

## The local encrypted implementation

For V1 local development, `LocalEncryptedSecretStore` stores an encrypted JSON document under `.local/tenant-secrets.json`.

Important details:

- a random opaque reference such as `sr_<random>` is generated for every stored secret;
- plaintext is encrypted with Fernet before being written;
- the encryption key is derived from the existing platform bootstrap/session secret using HKDF-SHA256 with Serviq-specific context;
- each encrypted record includes its owning tenant ID;
- file writes use a temporary file plus `os.replace`, reducing partial-write/corruption risk;
- POSIX directory/file permissions are tightened to `0700` and `0600`;
- a process lock protects read-modify-write operations inside one running process;
- malformed/corrupt encrypted data fails closed;
- `repr()` is explicitly redacted;
- stable error messages do not include the secret.

Only ciphertext, tenant ownership, and the opaque reference are persisted in the local secret document.

## Why this is an adapter instead of “just encrypting a column”

The adapter gives Serviq a replacement seam. A production deployment can later implement the same three methods using AWS Secrets Manager, GCP Secret Manager, Vault, or another approved secret service without rewriting provider CRUD, model configuration, or LLM adapters.

That is what “provider/service agnostic” means here: the rest of the product depends on the capability it needs, not on the local storage mechanism.

## Security and reliability tests

Tests prove:

- encrypt/decrypt round trips;
- different tenants cannot read each other's reference;
- delete is tenant-scoped;
- corrupt ciphertext fails safely;
- plaintext does not appear in the persisted JSON;
- the opaque reference is not the secret;
- `repr()` does not print credential material;
- writes remain valid JSON;
- the expected file permissions are used where supported.

A premium-style security review documents the boundary and limitations.

The final clean PR also fixed a lint issue as its own micro commit rather than bundling it invisibly into feature code.

## What this improves

Serviq now has a real BYOK credential boundary. Provider API keys can be used by server code without becoming normal relational fields or public API data.

## Important production limitation

The local encrypted file is a **local V1 adapter**, not a claim that one local JSON file is the final production secret backend. Its value is that it gives development/tests a real encrypted implementation and freezes the interface that a managed production implementation must satisfy.

## Completion evidence

- Linear: OPE-290 — Done.
- GitHub issue: #102.
- Final merged PR: #117.
- Final implementation is on `main`.

---

# OPE-291 — Implement provider connection CRUD APIs

## The problem in simple terms

After OPE-289 and OPE-290, Serviq had database tables and a secret store, but an authorized organization administrator still had no safe API for creating or managing a provider connection.

OPE-291 joins those two storage worlds into one user-facing server workflow.

## What APIs were added

The tenant-scoped provider module implements create, list, read, update, and delete behavior under:

```text
/api/v1/providers
```

The server derives the tenant from trusted request state. A caller cannot choose an arbitrary tenant by placing another tenant UUID in a request body.

Provider-management permission is represented by the dedicated capability:

```text
ai.providers.manage
```

The corresponding migration grants that capability to the existing V1 Owner/Admin system roles.

## Creating a provider

A create request supplies safe metadata plus a new API key.

The service:

1. verifies the current workforce user has provider-management permission in the trusted tenant;
2. writes the plaintext key into the tenant secret store;
3. receives an opaque `secret_ref`;
4. writes only metadata plus that reference into PostgreSQL;
5. returns a redacted provider view, never the API key.

The two storage systems introduce an important failure problem. If the secret write succeeds but the database transaction fails, Serviq must not silently leave an orphan secret. The service includes compensation/cleanup behavior for these cross-storage failure paths.

## Listing and reading

List/get queries are tenant-scoped in the repository. A known UUID from another tenant is not treated as permission to inspect that connection.

Responses expose provider management metadata needed by the application, but never the stored plaintext provider credential.

## Updating a provider

Metadata can be updated without replacing the key. When key replacement is requested, the workflow coordinates a new secret reference with the relational row and cleanup of the old secret.

The implementation uses row locking around replacement/deletion-sensitive paths to reduce races where concurrent updates could otherwise overwrite each other's secret references or cleanup decisions.

## Deleting a provider

Deletion is refused when a `model_configurations` row still references the provider connection. This is both a service-level product rule and backed by the database's restrictive foreign key.

When deletion is allowed, the workflow removes the relational connection and coordinates secret cleanup. Secret cleanup failures become a safe service error rather than returning raw storage exceptions.

## Errors stay stable and non-secret

The API uses stable errors for cases such as:

- not found;
- forbidden;
- duplicate/conflicting provider name;
- provider is still in use;
- secret cleanup failure.

Raw encryption exceptions, API keys, and internal stack detail are not part of the public response.

## What CI found during the clean rebuild

This ticket is a good example of why “code exists on a branch” is not the same as “production-quality ticket complete.”

When the stacked implementation was rebuilt onto the real mainline, permanent CI uncovered several integration defects:

- a provider ORM mapping initially imported a model base from the wrong location;
- the router imported `SuccessEnvelope` from an old/nonexistent contract package rather than `app.core.api`;
- tenant context belonged in the trusted principal boundary;
- the secret-store dependency name had drifted from the integration test;
- FastAPI rejected the original DELETE 204 contract because it could infer a response body;
- list service output was an immutable tuple while the declared API response model required a list.

Each defect was corrected on the ticket branch and the entire matrix was rerun. No gate was disabled to make the PR green.

## What the real PostgreSQL tests cover

The integration suite combines:

- real PostgreSQL;
- real provider metadata rows;
- the encrypted local secret-store implementation;
- FastAPI routes and dependency overrides for trusted test identity/tenant context.

It covers tenant scoping, permissions, create/list/get/update/delete, key replacement, duplicate names, secret cleanup, provider-in-use protection, and response redaction.

## What this improves

OPE-291 turns provider configuration from schema primitives into an actual safe management API. A tenant administrator can manage BYOK connections without exposing the key back to the browser or letting one tenant operate on another tenant's provider configuration.

## Completion evidence

- Linear: OPE-291 — Done.
- GitHub issue: #103.
- Final merged PR: #118.
- Final implementation is on `main`.

---

# OPE-292 — Implement normalized LLM Gateway Contract C-4 schemas

## The problem in simple terms

If OpenAI, Anthropic, Gemini, and OpenRouter objects were allowed to spread through Serviq, every agent and business module would eventually become provider-specific.

OPE-292 creates the opposite rule: everything outside an adapter speaks **Serviq's contract**.

## The normalized request

`GatewayRequest` freezes these provider-neutral concepts:

- `tenantId`;
- stable `modelAlias`;
- purpose;
- ordered messages;
- optional JSON response schema;
- `maxOutputTokens`;
- `timeoutMs`;
- streaming flag;
- `correlationId`.

The contract rejects unknown fields. Message roles are limited to system/user/assistant. Purpose is limited to the frozen C-4 values.

Two hard budgets are enforced during validation:

```text
maxOutputTokens <= 1500
timeoutMs <= 20000
```

An adapter therefore cannot accidentally receive an unbounded request from normal gateway code.

## The normalized response

`GatewayResponse` contains only Serviq-owned concepts:

- text `content` or structured data;
- normalized provider;
- upstream provider model;
- token usage;
- finish reason;
- provider request ID when available.

The provider enum is frozen to:

```text
openai
anthropic
gemini
openrouter
```

A fake test provider is intentionally **not** added to this public enum. OPE-293 models fake behavior as an implementation detail.

## Streaming

`GatewayStreamEvent` carries provider-neutral incremental content/structured data plus terminal metadata. It deliberately does not expose `ChatCompletionChunk`, Anthropic raw stream events, or any other SDK class.

## Five normalized failure categories

Provider adapters may expose exactly the C-4 categories:

- `PROVIDER_RATE_LIMITED`;
- `PROVIDER_TIMEOUT`;
- `PROVIDER_UNAVAILABLE`;
- `PROVIDER_INVALID_REQUEST`;
- `PROVIDER_AUTH_FAILED`.

`GatewayProviderError` wraps a Serviq-owned error object. Business/domain code therefore does not need to import OpenAI or Anthropic exception classes.

## Canonical fixtures and contract tests

OPE-292 adds canonical JSON request/response fixtures plus strict tests for:

- exact wire serialization;
- UUID validation;
- purpose/role validation;
- unknown fields;
- blank aliases/correlation IDs;
- token/timeout ceilings;
- provider validation;
- stream event requirements;
- all five error categories;
- proof that public contract types are owned by Serviq's schema module.

## A correctness issue discovered later

While OPE-293 and the real provider adapters were being validated, we discovered that the shared Pydantic base's `str_strip_whitespace=True` rule also affected provider-generated response text.

That is safe for IDs such as `modelAlias`, but not for model output. A stream chunk like `" world"` must not become `"world"`.

Prerequisite PR #123 fixed that semantic bug by keeping request/identifier normalization strict while using a provider-output base that preserves response and stream whitespace. The C-4 field names, enums, budgets, and provider-neutral ownership did not change.

## What this improves

OPE-292 gives Serviq one AI “language.” An agent can call the same interface regardless of which provider is selected behind it. That is the foundation for later model routing, fallback, evaluation, and cost controls.

## Completion evidence

- Linear: OPE-292 — Done.
- GitHub issue: #104.
- Final merged PR: #119.
- C-4 output-whitespace prerequisite correction: PR #123.
- Final implementation is on `main`.

---

# OPE-293 — Implement deterministic fake LLM adapter

## The problem in simple terms

A serious AI product cannot make its test suite depend on paid model calls or the public internet.

Tests must be able to say, “for this exact input/scenario, return this exact result,” including failure and streaming behavior.

OPE-293 creates that deterministic provider.

## One common adapter interface

The ticket adds `LLMAdapter`, the minimal internal protocol real and fake providers implement, plus `AdapterContext`.

`AdapterContext` contains already-resolved server-side information:

- provider;
- upstream model;
- optional API key.

Its representation redacts the API key. The adapter does not choose tenant, provider connection, or model alias itself.

## Why there is no public `fake` provider

ADR-010 records an important contract decision.

C-4's public provider enum represents the supported real provider domain. Expanding that enum just for tests would make a test implementation part of the public product contract.

Instead, the fake adapter uses synthetic upstream model identifier:

```text
serviq-fake-v1
```

and receives a normal normalized provider in test context. “Fake” remains an implementation/scenario property.

## Explicit scenarios, not magic prompt strings

Tests select a `FakeScenario` through constructor injection. The adapter never scans normal user text for secret control phrases such as “simulate timeout.”

Scenarios include:

- text success;
- structured success;
- streaming success;
- timeout;
- rate limited;
- unavailable;
- authentication failure;
- intentionally malformed structured output.

This makes failure-path tests readable and prevents normal customer messages from accidentally activating test behavior.

## Deterministic IDs and output

The fake request ID is derived from a canonical serialization of:

- C-4 request;
- provider;
- upstream model;
- selected scenario.

The same input produces the same identifier and the same output. Token usage is also synthetic and fixed for the scenario.

## Zero network dependency

The tests monkeypatch socket connection behavior to fail immediately if the fake adapter tries to open a network connection. Successful fake tests therefore prove the adapter does not quietly call a real provider.

## Streaming

The stream scenario yields a known ordered series of C-4 stream events and terminal metadata. Repeating the request yields byte-for-byte equivalent normalized events.

This testing work was what first exposed the C-4 whitespace issue described above. That discovery was valuable: the fake adapter was not merely a stub, it exercised the shared streaming contract strongly enough to reveal a bug that would also affect real providers.

## CI and security

The final ticket passed lint, strict typing, unit tests, real PostgreSQL integration, dependency audit, Trivy, Gitleaks, and CodeQL. One Python CodeQL run initially failed because GitHub returned HTTP 429 while downloading the CodeQL action itself. The failed job was rerun unchanged and passed; no code or security rule was weakened to hide the infrastructure rate limit.

## What this improves

Serviq can now build deterministic local/CI AI tests with no provider bill and no network dependency. Future routing, agent, evaluation, and fallback tickets can exercise successful and failing model behavior repeatably.

## Completion evidence

- Linear: OPE-293 — Done.
- GitHub issue: #105.
- Final merged PR: #121.
- ADR: `docs/architecture-decisions/ADR-010-fake-llm-adapter-identifiers.md`.
- Final implementation is on `main`.

---

# Architectural prerequisite for OPE-294 and OPE-295 — Freeze official SDK versions

The OpenAI and Anthropic tickets both contained a stop condition: do not invent an SDK/version inside a feature ticket. The repository did not yet have either approved provider SDK.

Instead of ignoring that requirement, implementation stopped and the architecture decision was made separately.

ADR-011 freezes:

```text
openai==2.53.0
anthropic==0.121.0
```

in the LLM Gateway dependency baseline.

The ADR also freezes the rules that:

- SDK types stay inside provider adapter modules/tests;
- public gateway objects remain C-4 types;
- API keys enter through server-resolved `AdapterContext`;
- provider exceptions are normalized before leaving an adapter;
- CI uses mocked SDK calls rather than paid live calls;
- future SDK upgrades are explicit reviewed dependency changes.

This prerequisite was merged through PR #122 before either real provider adapter was implemented.

---

# OPE-294 — Implement OpenAI generation and streaming adapter

## The problem in simple terms

C-4 defines what Serviq wants. The OpenAI SDK defines what OpenAI expects. OPE-294 is the translation layer between the two.

The rest of Serviq should never need to know how OpenAI's SDK names its request parameters, streaming classes, or exceptions.

## Credential and model boundary

`OpenAIAdapter` accepts an `AdapterContext` that has already been resolved by server-side configuration.

It verifies:

- provider context is actually `openai`;
- an API key exists and is non-blank;
- the caller has supplied an upstream model through the resolved context.

The adapter never interprets `modelAlias` itself and never reads an arbitrary tenant key from request JSON.

A request-scoped `AsyncOpenAI` client is created with:

```text
max_retries=0
```

This is intentional. Hidden SDK retries could silently multiply calls, latency, and cost beyond the C-4 timeout budget. Serviq keeps retry/fallback policy at the layer that can observe and account for it.

## Non-stream requests

The adapter preserves ordered system/user/assistant messages and forwards:

- resolved upstream model;
- bounded `maxOutputTokens`;
- bounded timeout.

For normal text generation, the provider's content becomes C-4 `content`.

## Structured output

When `responseSchema` is present, the adapter uses OpenAI's JSON Schema response format and requests strict schema behavior.

The returned provider JSON is parsed into the Serviq-owned `structured` dictionary. Raw SDK response objects do not escape the adapter.

Missing or malformed structured output becomes a safe normalized provider error.

## Streaming

For `stream=true`, the adapter requests streaming plus usage metadata.

It consumes provider chunks and emits only `GatewayStreamEvent` objects:

- content deltas are yielded in provider order;
- provider request ID is retained when available;
- finish reason is normalized;
- input/output token usage is placed into terminal metadata.

The PR #123 C-4 correction is important here: chunks such as `" world"` or `"! "` retain their exact whitespace.

## Error normalization

Official OpenAI SDK failures are reduced to C-4:

- authentication/permission -> `PROVIDER_AUTH_FAILED`;
- 429 -> `PROVIDER_RATE_LIMITED`;
- timeout -> `PROVIDER_TIMEOUT`;
- bad/not-found/unprocessable request -> `PROVIDER_INVALID_REQUEST`;
- connection/5xx/generic provider failures -> `PROVIDER_UNAVAILABLE`.

The adapter returns fixed Serviq-written messages. Raw upstream bodies, headers, SDK exception strings, and API keys are discarded.

## Mocked SDK tests

The tests inject a fake client through the client-factory seam. No live OpenAI request is made.

They cover:

- non-stream success;
- exact message/model/token/timeout forwarding;
- structured output;
- ordered streaming and whitespace;
- usage/finish/request ID;
- all required error categories;
- a representative raw authentication exception containing fake secret material, proving normalized output does not echo it;
- provider mismatch/missing key/wrong stream path;
- proof the returned types are Serviq C-4 types.

## What permanent CI found

Initial lint found import ordering, fixed as explicit style commits.

Strict mypy then caught a subtle official-SDK typing issue: an output `ResponseFormatJSONSchema` type had initially been used where the SDK expected the request-side `completion_create_params.ResponseFormat`. The final implementation uses the actual request parameter types and typed stream options.

This is why strict provider-boundary type checking is valuable. The ticket was not merged until that distinction was correct.

## Security review

`docs/security-reviews/OPE-294-openai-adapter.md` documents BYOK handling, provider binding, bounded calls, disabled hidden retries, structured output, stream integrity, error redaction, data sent upstream, and mock-only CI.

## What this improves

Serviq can now invoke OpenAI behind the same C-4 interface used by the fake provider and future providers, without leaking OpenAI SDK classes or raw errors into agent/domain layers.

## Completion evidence

- Linear: OPE-294 — Done.
- GitHub issue: #106.
- Final merged PR: #124.
- Approved SDK prerequisite: PR #122 / ADR-011.
- Security review: `docs/security-reviews/OPE-294-openai-adapter.md`.
- Final implementation is on `main`.

---

# OPE-295 — Implement Anthropic generation and streaming adapter

## The problem in simple terms

Anthropic supports the same broad product need as OpenAI, but its Messages API has different mechanics.

The clearest example is the system prompt. C-4 represents `system` as an ordinary ordered message role. Anthropic's Messages API uses a separate top-level `system` field instead.

OPE-295 performs that provider-specific translation **inside the adapter only**, so the rest of Serviq stays provider-neutral.

## Credential and provider binding

Like the OpenAI adapter, `AnthropicAdapter` accepts only server-resolved `AdapterContext`.

It fails closed when:

- the context provider is not Anthropic;
- the API key is missing/blank.

It uses the resolved `upstream_model`, not the public `modelAlias`.

The request-scoped `AsyncAnthropic` client also uses `max_retries=0`, preserving Serviq ownership of retry/fallback budgets.

## Translating system messages without changing meaning

Leading C-4 system messages are moved into Anthropic's top-level `system` value in their original order, separated explicitly.

User/assistant messages remain in the same conversation order.

If a system message appears **after** user/assistant conversation has begun, the adapter does not silently move it earlier, drop it, or pretend it is a user message. It returns:

```text
PROVIDER_INVALID_REQUEST
```

A system-only request is also rejected because there is no valid Anthropic conversational message.

This explicit failure is important. Provider portability should never mean silently changing prompt meaning.

## Non-stream output

The adapter calls the official Messages API with:

- resolved model;
- C-4 `maxOutputTokens` as Anthropic `max_tokens`;
- C-4 timeout;
- translated system/user/assistant content.

Text blocks are combined in order into normalized C-4 `content`.

Request/message ID, stop reason, input tokens, and output tokens are normalized into C-4 fields.

Unsupported provider content blocks fail safely instead of leaking an Anthropic object to downstream code.

## Structured output

When C-4 contains `responseSchema`, the adapter uses Anthropic's official `output_config.format` JSON Schema capability.

Non-stream JSON text is parsed into C-4 `structured`.

For structured streaming, provider JSON text deltas are buffered inside the adapter, validated, and emitted as a provider-neutral `structuredDelta`. Downstream code does not need to understand Anthropic's raw JSON event tokenization.

## Streaming

The adapter consumes raw Anthropic message events:

- `message_start` supplies message ID and initial usage;
- text `content_block_delta` events become C-4 text deltas in exact order;
- `message_delta` supplies stop reason and final output usage.

Only C-4 stream events leave the adapter.

The tests specifically reconstruct:

```text
Hello world! 
```

from chunks including leading/trailing spaces, proving text integrity through the shared C-4 output model.

## Error normalization and redaction

Anthropic errors are reduced to the same five C-4 categories used by OpenAI:

- auth/permission -> `PROVIDER_AUTH_FAILED`;
- 429 -> `PROVIDER_RATE_LIMITED`;
- timeout -> `PROVIDER_TIMEOUT`;
- invalid 4xx states -> `PROVIDER_INVALID_REQUEST`;
- connection, server/overload, generic provider failures -> `PROVIDER_UNAVAILABLE`.

Raw exception bodies, provider response objects, and credential material are discarded.

Mocked tests instantiate representative SDK exceptions containing fake secret/raw body text and verify normalized errors do not expose it.

## Validation path

The first PR run found only an import-order lint error. That was corrected as a separate micro commit.

The final branch then passed:

- lint;
- strict mypy;
- all gateway tests, including fake and OpenAI regression coverage;
- Compose validation;
- real PostgreSQL integration/migration chain;
- Trivy;
- dependency vulnerability audit;
- Gitleaks;
- Python CodeQL;
- JavaScript/TypeScript CodeQL.

## Security review

`docs/security-reviews/OPE-295-anthropic-adapter.md` explains the BYOK boundary, system-message semantics, structured output, stream integrity, provider data exposure, safe errors, and mock-only CI.

## What this improves

Serviq can now switch a C-4 generation workload between OpenAI and Anthropic without forcing agents or domain modules to import either provider's SDK.

The adapters are different internally because the providers are different. The product contract remains the same.

## Completion evidence

- Linear: OPE-295 — Done.
- GitHub issue: #107.
- Final merged PR: #125.
- Approved SDK prerequisite: PR #122 / ADR-011.
- Security review: `docs/security-reviews/OPE-295-anthropic-adapter.md`.
- Final implementation is on `main`.

---

# Final OPE-286 through OPE-295 batch result

The ten-ticket batch now moves Serviq from a workforce/tenant authorization foundation into a usable BYOK AI-provider foundation.

| Ticket | GitHub issue | Final merged PR | Main result |
|---|---:|---:|---|
| OPE-286 | #98 | #108 | Atomic invitation acceptance |
| OPE-287 | #99 | #109 | Tenant member list/role/status management |
| OPE-288 | #100 | #110 | Reusable adversarial tenant-isolation test harness |
| OPE-289 | #101 | #116 | Provider/model metadata schema |
| OPE-290 | #102 | #117 | Tenant secret-store contract + encrypted local adapter |
| OPE-291 | #103 | #118 | Tenant-scoped provider CRUD API |
| OPE-292 | #104 | #119 | Provider-neutral C-4 gateway contract |
| OPE-293 | #105 | #121 | Deterministic zero-network fake LLM adapter |
| OPE-294 | #106 | #124 | Official OpenAI generation/streaming adapter |
| OPE-295 | #107 | #125 | Official Anthropic generation/streaming adapter |

Supporting architectural/correctness PRs:

- **PR #122:** ADR-011 + exact OpenAI/Anthropic SDK baseline.
- **PR #123:** preserves provider-generated response/stream whitespace in C-4 output types.

Every final ticket implementation is merged to `main`. The permanent validation gates were used as blockers, not as decoration: issues found by lint, strict typing, FastAPI contract validation, real PostgreSQL integration, and provider adapter tests were corrected before merge.

The batch does **not** yet implement Gemini/OpenRouter adapters, provider connectivity testing, runtime model alias resolution/CRUD, gateway routing/fallback, or the later agent runtime. Those remain later tickets rather than hidden scope added to OPE-286 through OPE-295.

