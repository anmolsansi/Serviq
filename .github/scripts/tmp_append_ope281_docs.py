from pathlib import Path

focused = Path("docs/OPE_279_285_IMPLEMENTATION_GUIDE.md")
focused_marker = "# OPE-281 — Upsert internal user from verified OIDC identity"
focused_section = r'''

---

# OPE-281 — Upsert internal user from verified OIDC identity

## What problem this ticket solves

OIDC gives Serviq a verified external identity such as `(issuer, subject)`, but the rest of Serviq should not use that external pair as a foreign key everywhere. Memberships, role assignments, audit records, ownership, and future workflows need one stable internal `users.id`.

OPE-281 creates the bridge between those two identity systems.

The primary identity key remains the exact `(oidc_issuer, oidc_subject)` pair. Email is deliberately **not** used as the identity key because email can change and the same email string is not a cryptographic identity guarantee.

## Existing database contract reused

This ticket does not add a migration. OPE-277 already created the `users` table with:

- UUID primary key;
- `oidc_issuer`;
- `oidc_subject`;
- non-null email;
- non-null display name;
- `active|disabled` status;
- unique `(oidc_issuer, oidc_subject)` constraint.

`services/api/app/modules/workforce/models.py` maps that existing table into SQLAlchemy. The mapping exists so repository/service code can use the frozen schema without creating a second database representation.

## Layering added

The new workforce module follows the repository architecture:

```text
models.py      -> existing database table mapping
repository.py  -> exact persistence queries
service.py     -> business rules and transaction ownership
schemas.py     -> stable internal result DTO
errors.py      -> typed fail-closed domain errors
```

No routes or memberships are introduced in this ticket.

## Internal user DTO

`InternalWorkforceUser` contains only the stable internal fields downstream services need: user UUID, OIDC issuer/subject, email, display name, and status. It is frozen to prevent a caller from rewriting resolved identity after the service returns it.

## Exact identity lookup

`find_user_by_oidc_identity()` performs one tenant-independent lookup using both issuer and subject. It never searches by email and never picks the first matching-looking user.

This also means the same subject string under a different issuer is treated as a different external identity, matching the database unique constraint.

## First-login transaction

`upsert_verified_workforce_user()` accepts only the `VerifiedWorkforceIdentity` DTO produced by OPE-280. A raw JWT cannot enter the persistence service.

The service owns one transaction. It first checks whether the exact identity already exists.

If it does not, it stages an active user and flushes it inside a database savepoint. The savepoint matters because two servers can receive the first login for the same person at nearly the same time.

The PostgreSQL unique constraint is the final concurrency authority. If both requests try to insert:

1. one transaction wins and creates the row;
2. the losing insert raises a uniqueness error inside the savepoint;
3. only the savepoint is rolled back, not the entire service transaction;
4. the loser re-reads the winning `(issuer, subject)` row;
5. both callers receive the same stable internal user UUID.

If the integrity error did not produce a matching winner, the service re-raises it instead of hiding an unrelated database problem.

## Repeated login and safe profile synchronization

When the identity already exists and is active, the same UUID is returned.

The verified identity may update safe profile fields:

- a changed normalized email replaces the stored profile email;
- a supplied changed display name replaces the stored display name;
- if a later token omits display name, the existing display name is preserved.

New users require email because the frozen `users.email` database column is non-null. If the verified identity has no email, the service fails with `WORKFORCE_IDENTITY_PROFILE_INVALID` rather than inventing an address or writing invalid data. For a new user whose verified DTO has email but no display name, the email becomes the initial display label.

## Disabled users fail closed

A verified OIDC token does not override Serviq's internal account state.

If the matching Serviq user has status `disabled`, the service raises `WORKFORCE_USER_DISABLED`. It never silently changes the row back to active. This keeps Serviq's administrative disable control authoritative even when the upstream identity provider still considers the identity valid.

## PostgreSQL integration tests

`tests/integration/test_workforce_user_upsert.py` runs against the real PostgreSQL migration head and verifies:

- first login creates a user;
- repeat login returns the same UUID;
- safe email/display-name synchronization;
- same subject under a second issuer creates a separate identity;
- disabled users fail closed and remain disabled;
- two concurrent first-login calls result in exactly one row and the same returned UUID;
- missing verified email fails before a database write.

The tests use unique OPE-281 issuer prefixes and clean their rows after each scenario so they do not pollute later integration tests.

## What this improves

After OPE-281, downstream Serviq code has one dependable internal workforce identifier. The user identity is stable across repeated logins, concurrent login races cannot create duplicate users, and a valid OIDC token cannot silently re-enable an internally disabled account.

## What remains

This ticket does not choose a tenant, create a membership, resolve permissions, create a session, or expose an API route. OPE-282 takes the stable internal `users.id` plus a trusted tenant ID and resolves the active membership/capability set.
'''

if focused_marker not in focused.read_text():
    focused.write_text(focused.read_text() + focused_section)

build = Path("docs/SERVIQ_BUILD_GUIDE.md")
build_marker = "# OPE-281 — stable internal workforce user identity"
build_section = r'''

---

# OPE-281 — stable internal workforce user identity

OPE-281 connects the verified OIDC identity from OPE-280 to Serviq's existing `users` table. The primary identity is always the exact `(oidc_issuer, oidc_subject)` pair, never email.

The ticket adds a workforce domain module with an ORM mapping for the already-created users table, an exact identity repository query, a frozen internal-user DTO, typed disabled/profile errors, and a transaction-owning upsert service. No database migration or membership logic is added.

On first login, the service inserts an active user. On repeat login, it returns the same internal UUID and safely synchronizes changed email/display-name profile data. A missing email fails before persistence because the frozen database contract requires a non-null email. A disabled internal user remains disabled even when the external OIDC identity is valid.

Concurrent first login is handled using the database unique constraint plus a nested savepoint. If two callers race, one insert wins. The losing savepoint rolls back and reloads the winning row, so both successful callers resolve the same `users.id` instead of creating duplicates or returning an avoidable 500.

Real PostgreSQL integration tests cover first/repeat login, multiple issuers, profile synchronization, disabled-user behavior, concurrent first-login contention, and incomplete verified profile input.

The detailed implementation narrative is in `docs/OPE_279_285_IMPLEMENTATION_GUIDE.md`.
'''

if build_marker not in build.read_text():
    build.write_text(build.read_text() + build_section)
