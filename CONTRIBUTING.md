# Contributing to Serviq

Read the Linear ticket, linked GitHub issue, and `docs/repo_context.md` before coding. Inspect the exact files named by the ticket and do not treat architecture plans as proof that code already exists.

Use one ticket per branch and pull request. A typical branch name is `ope-271-repository-governance`. Do not develop directly on `main`. Push small commits with the ticket identifier and a short explanation.

Use `make setup` to install dependencies. Before review, run `make lint`, `make typecheck`, and `make test`. `make security` runs local dependency vulnerability audits; CodeQL, Gitleaks, and Trivy run in GitHub Actions. The `make e2e` and `make load-test` targets are intentional non-zero placeholders, so do not report them as passing. Use `make dev` for core local infrastructure and `make down` to stop it.

## Python dependency reproducibility

Serviq's API, worker, and LLM gateway require Python 3.14.x and each Python service owns a committed `uv.lock`. Normal setup and security commands validate every lock before use and then operate with frozen dependency resolution. A stale `pyproject.toml`/`uv.lock` pair is a failure condition; `make setup` and `make security` must not silently repair or replace the lock.

Use `make dependency-lock-check` when you want to verify lock freshness without installing dependencies or running audits.

Python vulnerability audits run `pip-audit==2.10.1` through `uvx --python 3.14`, so the audit tool itself uses the same required Python line instead of whichever interpreter happens to be selected on a contributor machine. Dependency exports are frozen and normal setup/audit commands must not create or modify tracked lockfiles.

When intentionally changing Python dependencies, edit the owning service's `pyproject.toml`, regenerate that service's `uv.lock` under Python 3.14, review both changes together, and commit the lock update with the dependency change. Do not hand-edit a lockfile to make validation pass.

Do not silently invent or change architecture-owned API, database, event, authentication, authorization, or shared contracts. If a required contract is missing, record `Needs Architect Decision: ...`. If an approved contract changes, reference its Contract Change Record under `docs/contract-changes/`.

Use `.github/pull_request_template.md` to report the ticket, summary, important files, validation, manual QA, contract-change status, security impact, unresolved architect decisions, completed scope, deferred work, and follow-up work. A pushed branch or open pull request is not the same as a completed ticket.

## Release and versioning policy

GitHub Releases are Serviq's official public version history. Releases are created only from commits contained in `main` and use Semantic Versioning with a leading `v`: `vMAJOR.MINOR.PATCH`. Development releases use an explicit prerelease suffix such as `v0.2.0-alpha.1`, `v0.5.0-beta.1`, or `v1.0.0-rc.1`.

Every pull request must declare one release-impact choice and should carry the matching label before merge:

- `release:major` for an approved breaking compatibility change;
- `release:minor` for backward-compatible functionality;
- `release:patch` for a backward-compatible bug/security fix;
- `release:skip` when the change should not appear in generated release notes.

Use the more specific type labels (`feature`, `fix`, `security`, `infrastructure`, `testing`, `dependencies`, `refactor`, `performance`, `documentation`) when they describe the change. `.github/release.yml` uses these labels to organize GitHub-generated release notes.

Do not create or move a published release tag to point at different code. If a release is wrong, publish a new patch/prerelease version rather than rewriting history. Stable `v1.0.0` is reserved for the point where the project has explicitly met its production-readiness criteria; pre-1.0 and alpha/beta/RC releases must not be described as production-ready.

The release workflow lives at `.github/workflows/release.yml`. It runs the repository quality gates before publishing and supports both an authorized manual release from `main` and a semantic-version tag that already points to a commit contained in `main`. Operator instructions are in `docs/RELEASING.md`.

Long-form implementation explanations belong in the cumulative `docs/SERVIQ_BUILD_GUIDE.md`. Explain what changed, how it works, why it was done, what it improves, how it was validated, and what is intentionally still missing. Do not create a separate long-form worklog for each ticket unless the repository convention is explicitly changed.
