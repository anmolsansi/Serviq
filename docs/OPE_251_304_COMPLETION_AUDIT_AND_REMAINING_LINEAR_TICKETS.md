# Serviq OPE-251–OPE-304 Completion Audit and Remaining Linear Backlog

> Audited 2026-08-22 against local/remote `main` commit `258d189`, live
> Linear, live GitHub pull requests and workflow runs, the codebase knowledge
> graph, current tests, repository specifications, and the supplied staged
> V1.3.05-to-V4 backlog. Planning documents are reference material, not runtime
> evidence.

## Executive result

- **54 tickets audited:** OPE-251 through OPE-304 inclusive.
- **50 complete with matching Linear state.**
- **3 complete but stale in Linear:** OPE-300, OPE-302, and OPE-304.
- **1 partial:** OPE-303. The upload feature is implemented and merged, but its
  absolute compensation criterion is not guaranteed if database persistence
  fails and object deletion also fails.
- **198 staged tickets are still absent from Linear:** V1 77, V2 38, V3 41,
  V4 42.
- **6 audit-discovered tickets** are added below. They do not duplicate a
  staged ticket's explicit scope.

“Complete” here means complete for the ticket's deliberately limited scope. A
completed scaffold ticket does not mean the later product feature exists.

## Evidence and test execution

### Current local results

- TypeScript lint: pass across all three apps.
- TypeScript typecheck: pass across all apps and shared packages.
- TypeScript test command: exits 0 but runs **zero tests**.
- API: Ruff pass; mypy pass over 106 files; 78 tests pass; 61 infrastructure
  integration tests skip because the Docker daemon is unavailable.
- Worker: Ruff/mypy pass; 5 tests pass.
- LLM gateway: Ruff/mypy pass; 93 tests pass.
- Compose configuration: pass for all profiles.
- npm production dependency audit: no known vulnerabilities.
- Python dependency audits: no known vulnerabilities when run explicitly with
  Python 3.14.
- Release scripts: shell syntax passes; valid SemVer accepted; leading-zero
  prerelease numeric identifier rejected.
- Local tag `v0.1.0-alpha.1` exists and points to the first merged OPE-304
  release-system commit.

### Remote integration evidence

- OPE-300 exact head `588d816...`: CI and Security succeeded.
- OPE-303 exact head `cd2b2d0...`: CI and Security succeeded, including real
  PostgreSQL and S3-compatible integration jobs.
- OPE-304 final head `243eaf0...`: CI and Security succeeded.
- PRs #147, #148, #153, #155, and #164 are merged.

### Verification limits

The Docker daemon was not running, so live PostgreSQL, object-storage, Valkey,
Keycloak, Redpanda, and observability containers were not restarted in this
audit. Current integration confidence therefore combines current unit/static
results with the exact-head GitHub integration evidence above. CodeQL, Gitleaks,
and Trivy were not rerun locally; their latest relevant GitHub runs are green.

## Ticket-by-ticket completion matrix

| Ticket | Linear | Audit verdict | Scope | Evidence or remaining gap |
|---|---|---|---|---|
| OPE-251 | Done | Complete | V1.0.01 — Freeze the V1 public demo company and synthetic tool domain | Frozen domain/tool contracts and authoritative-doc CCR/PR evidence. |
| OPE-252 | Done | Complete | V1.0.02 — Create the root monorepo toolchain files | Expected workspace/app/package boundary exists; current TS lint/typecheck pass. |
| OPE-253 | Done | Complete | V1.0.03 — Scaffold the client-console Next.js application | Expected workspace/app/package boundary exists; current TS lint/typecheck pass. |
| OPE-254 | Done | Complete | V1.0.04 — Scaffold the customer-web Next.js application | Expected workspace/app/package boundary exists; current TS lint/typecheck pass. |
| OPE-255 | Done | Complete | V1.0.05 — Scaffold the platform-console Next.js application | Expected workspace/app/package boundary exists; current TS lint/typecheck pass. |
| OPE-256 | Done | Complete | V1.0.06 — Create the shared UI package skeleton | Expected workspace/app/package boundary exists; current TS lint/typecheck pass. |
| OPE-257 | Done | Complete | V1.0.07 — Create the shared contracts package skeleton | Expected workspace/app/package boundary exists; current TS lint/typecheck pass. |
| OPE-258 | Done | Complete | V1.0.08 — Scaffold config, observability, security, and testkit packages | Expected workspace/app/package boundary exists; current TS lint/typecheck pass. |
| OPE-259 | Done | Complete | V1.0.09 — Scaffold the FastAPI API service | Expected service boundary exists; current Ruff, mypy, pytest pass. |
| OPE-260 | Done | Complete | V1.0.10 — Scaffold the durable worker service | Expected service boundary exists; current Ruff, mypy, pytest pass. |
| OPE-261 | Done | Complete | V1.0.11 — Scaffold the LLM gateway service | Expected service boundary exists; current Ruff, mypy, pytest pass. |
| OPE-262 | Done | Complete | V1.0.12 — Add local PostgreSQL with pgvector to Docker Compose | Compose contract renders; historical live-health CI evidence retained in OPE-305. |
| OPE-263 | Done | Complete | V1.0.13 — Add local Valkey cache to Docker Compose | Compose contract renders; historical live-health CI evidence retained in OPE-305. |
| OPE-264 | Done | Complete | V1.0.14 — Add local S3-compatible object storage | Compose contract renders; historical live-health CI evidence retained in OPE-305. |
| OPE-265 | Done | Complete | V1.0.15 — Add local Keycloak OIDC service | Compose contract renders; historical live-health CI evidence retained in OPE-305. |
| OPE-266 | Done | Complete | V1.0.16 — Add the optional local Redpanda event-broker profile | Compose contract renders; historical live-health CI evidence retained in OPE-305. |
| OPE-267 | Done | Complete | V1.0.17 — Add the optional local observability profile | Compose contract renders; historical live-health CI evidence retained in OPE-305. |
| OPE-268 | Done | Complete | V1.0.18 — Add root Makefile developer commands | All Make targets exist; placeholders fail honestly; current quality commands pass. |
| OPE-269 | Done | Complete | V1.0.19 — Add the baseline pull-request CI workflow | CI workflow has required triggers/gates; exact-head GitHub CI is green. |
| OPE-270 | Done | Complete | V1.0.20 — Run the post-scaffold repository audit and create repo_context.md | Current working-tree repo audit exists and was refreshed on 2026-08-22. |
| OPE-271 | Done | Complete | V1.0.21 — Add repository contribution and pull-request governance files | PR template, contribution/security guidance and CODEOWNERS exist. |
| OPE-272 | Done | Complete | V1.0.22 — Add baseline repository security scanning | Security workflow and dependency audits exist; exact-head Security is green. |
| OPE-273 | Done | Complete | V1.0.23 — Implement typed platform configuration and .env.example | Typed configuration/tests and safe example environment exist. |
| OPE-274 | Done | Complete | V1.0.24 — Replace the placeholder README with verified local setup instructions | README reflects verified setup, status, and demo limitations. |
| OPE-275 | Done | Complete | V1.1.01 — Configure SQLAlchemy, database sessions, and Alembic | DB/readiness/migrations exist; unit suite green; historical real-Postgres CI green. |
| OPE-276 | Done | Complete | V1.1.02 — Add API database readiness health check | DB/readiness/migrations exist; unit suite green; historical real-Postgres CI green. |
| OPE-277 | Done | Complete | V1.1.03 — Create tenant, workforce, and RBAC database migration | DB/readiness/migrations exist; unit suite green; historical real-Postgres CI green. |
| OPE-278 | Done | Complete | V1.1.04 — Create organization invitation database migration | DB/readiness/migrations exist; unit suite green; historical real-Postgres CI green. |
| OPE-279 | Done | Complete | V1.1.05 — Implement trusted RequestContext | Auth/tenancy APIs and adversarial tests exist; unit suite and exact-head CI green. |
| OPE-280 | Done | Complete | V1.1.06 — Implement workforce OIDC token validation | Auth/tenancy APIs and adversarial tests exist; unit suite and exact-head CI green. |
| OPE-281 | Done | Complete | V1.1.07 — Upsert internal user from verified OIDC identity | Auth/tenancy APIs and adversarial tests exist; unit suite and exact-head CI green. |
| OPE-282 | Done | Complete | V1.1.08 — Resolve tenant membership and effective capabilities | Auth/tenancy APIs and adversarial tests exist; unit suite and exact-head CI green. |
| OPE-283 | Done | Complete | V1.1.09 — Implement organization list and create APIs | Auth/tenancy APIs and adversarial tests exist; unit suite and exact-head CI green. |
| OPE-284 | Done | Complete | V1.1.10 — Implement organization detail and update APIs | Auth/tenancy APIs and adversarial tests exist; unit suite and exact-head CI green. |
| OPE-285 | Done | Complete | V1.1.11 — Implement invitation create, list, and revoke APIs | Auth/tenancy APIs and adversarial tests exist; unit suite and exact-head CI green. |
| OPE-286 | Done | Complete | V1.1.12 — Implement invitation acceptance API | Auth/tenancy APIs and adversarial tests exist; unit suite and exact-head CI green. |
| OPE-287 | Done | Complete | V1.1.13 — Implement member list and role/status update APIs | Auth/tenancy APIs and adversarial tests exist; unit suite and exact-head CI green. |
| OPE-288 | Done | Complete | V1.1.14 — Add reusable tenant-isolation repository test harness | Auth/tenancy APIs and adversarial tests exist; unit suite and exact-head CI green. |
| OPE-289 | Done | Complete | V1.2.01 — Create provider and model metadata migration | Provider/model/gateway implementation and tests exist; exact-head CI/Security green. |
| OPE-290 | Done | Complete | V1.2.02 — Implement tenant secret adapter and local encrypted store | Provider/model/gateway implementation and tests exist; exact-head CI/Security green. |
| OPE-291 | Done | Complete | V1.2.03 — Implement provider connection CRUD APIs | Provider/model/gateway implementation and tests exist; exact-head CI/Security green. |
| OPE-292 | Done | Complete | V1.2.04 — Implement normalized LLM Gateway Contract C-4 schemas | Provider/model/gateway implementation and tests exist; exact-head CI/Security green. |
| OPE-293 | Done | Complete | V1.2.05 — Implement deterministic fake LLM adapter | Provider/model/gateway implementation and tests exist; exact-head CI/Security green. |
| OPE-294 | Done | Complete | V1.2.06 — Implement OpenAI generation and streaming adapter | Provider/model/gateway implementation and tests exist; exact-head CI/Security green. |
| OPE-295 | Done | Complete | V1.2.07 — Implement Anthropic generation and streaming adapter | Provider/model/gateway implementation and tests exist; exact-head CI/Security green. |
| OPE-296 | Done | Complete | V1.2.08 — Implement Gemini generation and streaming adapter | Provider/model/gateway implementation and tests exist; exact-head CI/Security green. |
| OPE-297 | Done | Complete | V1.2.09 — Implement OpenRouter generation and streaming adapter | Provider/model/gateway implementation and tests exist; exact-head CI/Security green. |
| OPE-298 | Done | Complete | V1.2.10 — Implement provider connectivity test endpoint | Provider/model/gateway implementation and tests exist; exact-head CI/Security green. |
| OPE-299 | Done | Complete | V1.2.11 — Implement model configuration CRUD and alias validation | Provider/model/gateway implementation and tests exist; exact-head CI/Security green. |
| OPE-300 | In Review | Complete; Linear stale | V1.3.01 — Create knowledge source, document, and chunk migration | Migration 0008 plus PostgreSQL constraint/FTS tests; PR #147 CI/Security green. |
| OPE-301 | Done | Complete | V1.3.02 — Implement S3-compatible object-storage adapter and generated knowledge keys | S3 adapter/generated keys and integration test; PRs #148/#151 green. |
| OPE-302 | In Review | Complete; Linear stale | V1.3.03 — Implement URL and sitemap knowledge source create/list APIs | Tenant-scoped JSON APIs and isolation tests; PR #153 merged. |
| OPE-303 | In Review | Partial | V1.3.04 — Implement PDF, Markdown, and text knowledge upload API | Upload validation/storage tests pass, but failed DB + failed delete can leave an orphan. |
| OPE-304 | In Progress | Complete; Linear stale | V1.0.25 — Establish GitHub Releases and semantic versioning | Release workflows/scripts, tag v0.1.0-alpha.1, PR #164 CI/Security green. |

## Required tracker reconciliation

1. Move OPE-300 to Done; PR #147 is merged and its exact-head CI/Security passed.
2. Move OPE-302 to Done; PR #153 is merged.
3. Keep OPE-303 In Review/Partial until the durable cross-store failure gap
   below is resolved or the acceptance wording is explicitly changed by an
   architect.
4. Move OPE-304 to Done; PR #164 is merged, CI/Security passed, and the first
   prerelease exists.
5. Do not use the V1 milestone percentage as product-completion evidence; it
   excludes the staged backlog below.

## Audit-discovered Linear tickets

The following use the same section structure as the existing detailed Linear
issues. Tickets containing `Needs Architect Decision` are not builder-ready
until that decision is recorded.

These six audit discoveries and all 198 staged roadmap items are consolidated
in [`docs/SERVIQ_REMAINING_LINEAR_TICKETS_FULL.md`](SERVIQ_REMAINING_LINEAR_TICKETS_FULL.md).

### TICKET V1.0.26 — Lock LLM Gateway Dependencies and Make Local Audits Reproducible

#### Goal
Make LLM gateway installs and all local Python vulnerability audits deterministic
under the repository's required Python 3.14 runtime.

#### Why This Exists
The API and worker have committed uv locks, but the LLM gateway does not. Its
dependency export resolves current registry versions on every run. The unmodified
local audit command also allowed `uvx` to select Python 3.13, which failed on
Python 3.14-specific requirement hashes until the interpreter was forced.

#### Estimated Effort
1–2 focused engineering hours.

#### User-Facing Behavior
None; developer/release reliability.

#### Scope
- Commit and enforce `services/llm-gateway/uv.lock`.
- Change setup, CI, security, and release dependency commands to use frozen
  gateway resolution.
- Ensure pip-audit runs under Python 3.14 on supported developer machines.
- Add a check that dependency commands leave the worktree clean.

#### Out of Scope
- Upgrading provider SDK major versions.
- Replacing uv or pip-audit.
- Adding a dependency-management service.

#### Files to Inspect First
- `services/llm-gateway/pyproject.toml` — dependency contract.
- `Makefile` — local setup/security commands.
- `.github/workflows/ci.yml` — install path.
- `.github/workflows/security.yml` — audit path.
- `.github/workflows/release.yml` — release install path.

#### Files to Create or Edit
- `services/llm-gateway/uv.lock`
- `Makefile`
- `.github/workflows/ci.yml`
- `.github/workflows/security.yml`
- `.github/workflows/release.yml`
- `CONTRIBUTING.md`

#### Data Model
None.

#### API Contract
None.

#### UI States
None.

#### Validation Rules
Python must be 3.14.x; all three exported dependency sets must audit without
modifying tracked files.

#### Error Handling
Wrong Python or stale lock fails with a concise actionable error before audit.

#### Auth & Permissions
No new permissions or secrets.

#### Dependencies
OPE-261, OPE-272, OPE-304.

#### Integration Contract
`make setup` and `make security` become frozen, clean-worktree commands.

#### Implementation Steps
1. Generate/review the gateway lock under Python 3.14.
2. Freeze all gateway sync/export calls.
3. Force the audit interpreter to 3.14 without a machine-specific path.
4. Add clean-worktree verification in CI.
5. Update contributor documentation.

#### Test Cases
1. Fresh frozen gateway sync succeeds.
2. Stale pyproject/lock fails.
3. All three pip-audits run under Python 3.14.
4. Commands create no untracked lockfile.
5. npm and Python audits retain non-zero failure behavior.

#### Manual QA
Run setup/security from a clean checkout and verify `git status --short` stays
empty.

#### Acceptance Criteria
- [ ] Gateway lock is committed and frozen everywhere.
- [ ] Local security command selects Python 3.14 deterministically.
- [ ] All dependency audits pass on a clean checkout.
- [ ] CI and release paths use the same lock contract.
- [ ] No provider SDK behavior changes.

#### Definition of Done
All tests above, full CI/Security, documentation, and clean-worktree check pass.

#### Do Not Change
Provider adapter contracts, model names, API schemas, or runtime behavior.

---

### TICKET V1.0.27 — Pin Every GitHub Action to an Immutable Commit

#### Goal
Remove mutable action-tag supply-chain risk from CI and release workflows.

#### Why This Exists
The Security workflow pins actions by commit SHA, while CI and Release still use
mutable tags such as `actions/checkout@v4`.

#### Estimated Effort
1 focused engineering hour.

#### User-Facing Behavior
None.

#### Scope
Pin every third-party action in permanent workflows to reviewed commit SHAs and
retain readable version comments.

#### Out of Scope
Changing job behavior, permissions, runner OS, or adopting a new scanner.

#### Files to Inspect First
- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- `.github/workflows/security.yml`

#### Files to Create or Edit
- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`

#### Data Model
None.

#### API Contract
None.

#### UI States
None.

#### Validation Rules
No permanent workflow may contain an unpinned `uses:` reference.

#### Error Handling
CI fails a repository check when a mutable action reference is introduced.

#### Auth & Permissions
Existing least-privilege job permissions remain unchanged.

#### Dependencies
OPE-269, OPE-272, OPE-304.

#### Integration Contract
Workflow behavior and inputs remain frozen; only action resolution changes.

#### Implementation Steps
1. Resolve each current action tag to its official reviewed commit.
2. Replace tags with SHAs and add version comments.
3. Add a lightweight workflow-source assertion.
4. Run CI and Security.

#### Test Cases
1. Repository scan finds zero mutable `uses:` entries.
2. CI jobs pass.
3. Release validation jobs pass without publishing a release.

#### Manual QA
Inspect each action owner/repository and SHA against its official release.

#### Acceptance Criteria
- [ ] CI and Release actions are immutable.
- [ ] Version comments remain readable.
- [ ] Permissions and job behavior are unchanged.
- [ ] Automated regression check exists.

#### Definition of Done
Exact-head CI and Security are green.

#### Do Not Change
Release tags, published releases, secrets, or product code.

---

### TICKET V1.1.15 — Add Live Keycloak Workforce OIDC Integration Coverage

#### Goal
Prove the configured local Keycloak realm can issue a token that the current API
validator accepts and that invalid audience/issuer cases fail closed.

#### Why This Exists
OIDC cryptographic and discovery behavior has strong mocked tests, but the staged
backlog does not explicitly test the real Keycloak configuration against the API.

#### Estimated Effort
2–3 focused engineering hours.

#### User-Facing Behavior
None; authentication integration evidence.

#### Scope
Add an opt-in CI integration test that starts Keycloak, obtains a test workforce
token using a non-production test client, validates it through the real validator,
and tests wrong audience/issuer.

#### Out of Scope
Browser login UI, production IdP configuration, customer authentication, or
persisting real credentials.

#### Files to Inspect First
- `infra/docker/compose.yml`
- `services/api/app/core/auth.py`
- `services/api/tests/test_workforce_oidc.py`
- `.github/workflows/ci.yml`

#### Files to Create or Edit
- `infra/keycloak/serviq-test-realm.json` — new deterministic test realm/client fixture.
- `services/api/tests/integration/test_keycloak_oidc_integration.py`
- `.github/workflows/ci.yml`
- `docs/repo_context.md`

#### Data Model
None.

#### API Contract
No public route change; consumes the existing workforce OIDC validator contract.

#### UI States
None.

#### Validation Rules
Test credentials are placeholders; logs and failure artifacts contain no token.

#### Error Handling
Keycloak readiness timeout fails the integration job with container diagnostics
but redacts tokens and client secrets.

#### Auth & Permissions
Test-only realm/client; no production secret or broad GitHub permission.

#### Dependencies
OPE-265, OPE-280.

#### Integration Contract
The Compose Keycloak issuer/audience/client settings must match API configuration.

#### Implementation Steps
1. Freeze a test realm/client fixture.
2. Start Keycloak and wait on readiness.
3. Obtain and validate one token.
4. Execute negative issuer/audience cases.
5. Add safe CI cleanup and documentation.

#### Test Cases
1. Real issued token validates.
2. Wrong audience fails.
3. Wrong issuer fails.
4. Disabled/unknown subject behavior remains safe.
5. Token is absent from captured logs.

#### Manual QA
Run the opt-in integration job locally with Docker and inspect safe output.

#### Acceptance Criteria
- [ ] Real Keycloak-to-validator path passes.
- [ ] Negative trust-boundary cases fail closed.
- [ ] No token/secret leakage.
- [ ] CI cleanup always runs.

#### Definition of Done
Integration job and existing auth suite pass.

#### Do Not Change
OIDC public claims contract, customer identity, or platform-console auth.

---

### TICKET V1.3.04A — Freeze and Implement Durable Knowledge Upload Consistency

#### Goal
Guarantee that every uploaded raw object is either referenced by a durable source
record or discoverable by a durable cleanup/reconciliation process.

#### Why This Exists
OPE-303 uploads the object before committing its database row. On database
failure it attempts deletion, but suppresses `ObjectStorageError`; simultaneous
DB and delete failure can leave an untracked object.

#### Estimated Effort
Architect decision plus 2–3 focused implementation hours.

#### User-Facing Behavior
A failed upload remains failed; operators can detect and repair residual cleanup
work without exposing object keys to tenant users.

#### Scope
- Record an ADR selecting the cross-store consistency strategy.
- Implement durable cleanup state or a deterministic reconciliation sweep.
- Retry deletion idempotently with bounded backoff/DLQ.
- Emit safe metrics/logs for pending, succeeded, and exhausted cleanup.
- Cover the double-failure path.

#### Out of Scope
Knowledge parsing/indexing, customer attachments, lifecycle policies, or a new
storage service.

#### Files to Inspect First
- `services/api/app/modules/knowledge/service.py`
- `services/api/app/core/object_storage.py`
- `services/api/tests/integration/test_knowledge_file_upload_api.py`
- `services/worker/app/jobs/`
- `services/api/alembic/versions/20260819_0008_knowledge_schema.py`

#### Files to Create or Edit
Needs Architect Decision: select record-first state transition versus durable
cleanup record/sweeper before freezing exact files and migration contract.

#### Data Model
Needs Architect Decision: durable upload state/cleanup intent and retention.

#### API Contract
Existing upload response/error contract must remain compatible.

#### UI States
None in this ticket; operator surfacing may be consumed by V1.10 platform work.

#### Validation Rules
Tenant ID and generated key are server-owned; retries are idempotent and bounded.

#### Error Handling
Double failure persists a safe cleanup obligation and never reports success.

#### Auth & Permissions
Cleanup runs only as a trusted worker/platform operation.

#### Dependencies
OPE-301, OPE-303; coordinate with V1.3.06 durable outbox design.

#### Integration Contract
Expose one durable cleanup job/state that V1.10.09 DLQ operations can inspect.

#### Implementation Steps
1. Write and approve the ADR.
2. Add the minimal durable state/contract.
3. Change upload failure handling.
4. Implement idempotent cleanup/reconciliation.
5. Add double-failure tests and safe telemetry.

#### Test Cases
1. Storage success + DB success leaves one referenced object.
2. Storage success + DB failure + delete success leaves no object.
3. Storage success + DB failure + delete failure creates durable cleanup work.
4. Cleanup replay deletes once and marks success.
5. Foreign-tenant cleanup is rejected.
6. Exhausted retry is operator-visible without leaking credentials.

#### Manual QA
Inject DB and storage-delete failures, restore storage, replay cleanup, and verify
no unreferenced object remains.

#### Acceptance Criteria
- [ ] Double failure is durable and observable.
- [ ] Cleanup is idempotent, bounded, and tenant-safe.
- [ ] Existing upload API remains compatible.
- [ ] Real PostgreSQL and S3 integration tests pass.
- [ ] Premium security/reliability review passes.

#### Definition of Done
ADR, implementation, migration if selected, tests, metrics, runbook, CI/Security.

#### Do Not Change
Generated object-key layout, supported file types/sizes, or customer attachment
scope.

---

### TICKET V1.3.04B — Add Knowledge Upload Quota and Abuse Controls

#### Goal
Prevent an authorized or compromised knowledge manager from exhausting tenant or
platform object storage and request capacity.

#### Why This Exists
OPE-303 bounds each file but does not define per-tenant storage quota, upload
rate, concurrent upload limit, or safe quota-exceeded behavior. V1.10.05 covers
general platform rate policies but does not explicitly own knowledge bytes.

#### Estimated Effort
Needs Architect Decision, then 2–3 focused engineering hours.

#### User-Facing Behavior
Uploads over the frozen limit return a stable, safe error and do not store an
object or create a source row.

#### Scope
Freeze and enforce per-user request rate, per-tenant concurrent uploads, and
per-tenant stored-byte/source-count quotas with safe usage accounting.

#### Out of Scope
Billing, paid overages, customer attachments, or production cloud lifecycle.

#### Files to Inspect First
- `services/api/app/modules/knowledge/router.py`
- `services/api/app/modules/knowledge/service.py`
- `services/api/app/modules/providers/rate_limits.py`
- `services/api/app/core/object_storage.py`
- V1.10.05 staged ticket.

#### Files to Create or Edit
Needs Architect Decision: exact quota ownership, counters, limits, and migration.

#### Data Model
Needs Architect Decision: authoritative stored-byte/source-count accounting and
reconciliation rule.

#### API Contract
Freeze stable 429 rate-limit and 409/413 quota-exceeded codes before coding.

#### UI States
None; V1.9.05 will consume safe errors and remaining quota when exposed.

#### Validation Rules
All limits require exact numbers; fail closed when the authoritative limiter or
quota store is unavailable.

#### Error Handling
Rejected uploads perform no object write. Races cannot exceed quota without a
bounded documented tolerance.

#### Auth & Permissions
Existing `knowledge.sources.manage` remains required; platform overrides are
outside this ticket unless explicitly frozen.

#### Dependencies
OPE-303; coordinate with V1.10.05.

#### Integration Contract
Expose only safe usage/limit metadata; never storage credentials or raw keys.

#### Implementation Steps
1. Approve quota/rate policy.
2. Implement atomic reservation before upload.
3. Commit or release reservation after final outcome.
4. Add reconciliation for leaked reservations.
5. Add tests and safe metrics.

#### Test Cases
1. Within-limit upload succeeds.
2. Per-file limit still applies.
3. Request rate exceeded returns 429.
4. Tenant byte/source quota returns frozen error.
5. Concurrent requests cannot bypass reservation.
6. Failed upload releases reservation.
7. Foreign tenant cannot inspect or consume another quota.

#### Manual QA
Exercise limit, failure, retry, and concurrent cases against real Valkey,
PostgreSQL, and S3-compatible storage.

#### Acceptance Criteria
- [ ] Exact quota/rate numbers are architect-approved.
- [ ] Reservations are atomic/idempotent.
- [ ] Rejected uploads create no object/source.
- [ ] Safe errors and metrics exist.
- [ ] Integration/security tests pass.

#### Definition of Done
Policy decision, implementation, tests, runbook, CI/Security.

#### Do Not Change
General billing or unrelated platform rate-policy contracts.

---

### TICKET V1.9.00 — Establish Frontend Component and Browser Test Harnesses

#### Goal
Give the three Next.js applications a real test command before interactive V1
screens are built.

#### Why This Exists
The current recursive TypeScript test command succeeds while running zero tests.
The staged V1.9 UI tickets require loading, empty, error, permission, form, and
streaming coverage but do not explicitly establish the harness.

#### Estimated Effort
2–3 focused engineering hours.

#### User-Facing Behavior
None directly; prevents untested UI regressions.

#### Scope
Select the smallest repository-compatible component test runner and browser E2E
foundation, add one smoke test per app, and make zero-test execution fail.

#### Out of Scope
Testing future product screens, visual-regression SaaS, Storybook, or broad
cross-browser matrices.

#### Files to Inspect First
- `package.json`
- `pnpm-workspace.yaml`
- `apps/client-console/package.json`
- `apps/customer-web/package.json`
- `apps/platform-console/package.json`
- `.github/workflows/ci.yml`

#### Files to Create or Edit
Needs Architect Decision: choose the exact component runner and E2E tool before
freezing app-local config/test paths.

#### Data Model
None.

#### API Contract
None.

#### UI States
Each smoke fixture must prove render success and one accessible landmark/name.

#### Validation Rules
`pnpm test` fails when no tests are discovered.

#### Error Handling
Browser artifacts must be bounded and redact tokens, cookies, and response data.

#### Auth & Permissions
No production credentials; fake/local services only.

#### Dependencies
OPE-253, OPE-254, OPE-255. Must complete before V1.9.01–V1.9.12.

#### Integration Contract
Root `pnpm test` runs component tests; the future V1.11.03 E2E command consumes
the same browser foundation without duplicating configuration.

#### Implementation Steps
1. Record the minimal tool decision.
2. Add shared config only where genuinely shared.
3. Add one accessible smoke test per app.
4. Add a zero-test failure guard.
5. Wire CI and safe artifacts.

#### Test Cases
1. Each app smoke test passes.
2. Intentional render failure fails.
3. Zero discovered tests fails.
4. Browser artifact contains no seeded fake secret.

#### Manual QA
Run tests from a clean checkout at the pinned Node/pnpm versions.

#### Acceptance Criteria
- [ ] Three app smoke tests execute.
- [ ] Root test command cannot be falsely green with zero tests.
- [ ] CI runs the harness.
- [ ] Accessibility-first queries are demonstrated.
- [ ] No paid service or production secret is required.

#### Definition of Done
Decision, harness, smoke tests, CI, and contributor docs pass.

#### Do Not Change
Product UI behavior or future V1.9 feature contracts.

---

## Staged V1–V4 tickets absent from Linear

> **Conversion status:** The compact source inventory below is preserved for
> auditability. Their corrected full Linear-style conversion is consolidated in
> [the complete remaining-ticket document](SERVIQ_REMAINING_LINEAR_TICKETS_FULL.md).
> Use the full ticket sections there for Linear intake; do not hand these compact
> entries directly to a builder.

**Repository:** https://github.com/anmolsansi/Serviq
**Linear project:** Serviq
**Captured:** 2026-08-13
**Already created in Linear:** through **V1.3.04**
**Next issue to create:** **V1.3.05**

This file is the canonical staging backlog for all remaining Serviq tasks. When Linear space is available, convert each numbered task below into **one Linear issue**. Do not combine tasks.

### Linear conversion rules

Every task is intended for roughly **1–3 focused engineering hours**. When converting a task to Linear, preserve its ticket number/title and expand it into the full Premium Product Builder issue format with: Goal, Why this exists, Estimated effort, Read before coding, User-facing behavior, Exact scope, Contracts/API/DB/events/UI behavior, Do not change, Files to inspect, Step-by-step implementation, Required automated tests, Security/privacy requirements, Manual QA, Acceptance criteria, Stop conditions, Definition of done, Dependencies, and suggested labels.

Every builder must read `docs/repo_context.md` first, then the exact PRD/architecture/ADR/CCR named by the task. If the repository differs from the frozen contract, stop with `Needs Architect Decision`. Never invent API fields, database columns, permissions, security behavior, provider behavior, dependencies, or UX contracts. Never expose secrets, raw tokens, unrestricted PII, or chain-of-thought in logs/errors/traces/UI. Keep each PR limited to one ticket.

Milestones: V1 = `Phase 1 — V1 Production Foundation`; V2 = `Phase 2 — V2 Integrations & Omnichannel Scale`; V3 = `Phase 3 — V3 Autonomous Enterprise Operations`; V4 = `Phase 4 — V4 Hyperscale & Multi-Region`.

Suggested labels as applicable: `Serviq: Foundation`, `Serviq: Frontend`, `Serviq: Backend`, `Serviq: AI`, `Serviq: Security`, `Serviq: Data`, `Serviq: Infrastructure`, `Serviq: Testing`, `junior-ready`, `Vibe-code Ready`, `Human Needed`.

---

### Phase 1 — V1 Production Foundation

#### V1.3.05 — Implement SSRF-safe public knowledge fetch helper

**Goal:** worker can fetch public docs without reaching private/internal networks.
**Scope:** HTTPS, DNS resolution, block loopback/private/link-local/CGNAT/metadata/multicast/reserved IPv4+IPv6, recheck redirects, timeout/size/MIME/domain controls.
**Tests:** public success; 127.0.0.1; 169.254.169.254; private IPv6; redirect-to-private; oversized response.
**Acceptance:** every redirect target revalidated.
**Review:** premium security review.

#### V1.3.06 — Implement source sync command and durable outbox event

**Goal:** `POST /api/v1/knowledge-sources/{sourceId}/sync` increments `sync_version`, sets syncing, and writes `serviq.knowledge.sync.v1` outbox event atomically.
**Tests:** URL/file source, disabled conflict, concurrent requests, transaction rollback.
**Acceptance:** no FastAPI in-process background task.

#### V1.3.07 — Implement knowledge sync fetch worker

**Goal:** consume sync event idempotently, fetch URL/file raw content, create versioned document/content hash, emit parse event.
**Tests:** URL/file success, stale version ignored, tenant mismatch, retry/DLQ behavior.
**Acceptance:** source failure visible with safe code and bounded retries.

#### V1.3.08 — Implement PDF/Markdown/text normalization parser

**Goal:** produce safe plain-text segments plus provenance/page metadata.
**Scope:** PDF text extraction, UTF-8 md/txt, bounded output; no OCR.
**Tests:** PDF pages, headings, malformed/encrypted PDF, invalid encoding.
**Acceptance:** parser never executes embedded content and logs no raw sensitive document text.

#### V1.3.09 — Implement HTML/help-center normalization parser

**Goal:** extract title/headings/article paragraphs/lists while stripping script/style/form/navigation noise.
**Tests:** normal article, list, script removal, noisy nav, empty content failure.
**Acceptance:** no headless-browser/anti-bot bypass in V1.

#### V1.3.10 — Implement deterministic heading-aware chunker

**Goal:** split normalized text into ordered bounded chunks with overlap/token_count/provenance using the frozen chunk policy.
**Tests:** short/long/headings/lists/ties; repeat input gives identical output; no empty chunks.
**Acceptance:** chunk policy changes require evaluation/ADR.

#### V1.3.11 — Freeze embedding profile ADR and implement embedding adapter

**Goal:** architect records one V1 embedding alias/dimension/batch policy, then implement fake deterministic embeddings plus real gateway embedding path.
**Tests:** correct dimension, deterministic fake, batch mismatch, provider failure.
**Acceptance:** vector dimension is explicitly documented before indexing.
**Human/Architect decision:** required before implementation.

#### V1.3.12 — Add pgvector index migration

**Goal:** create the correct vector index/operator for the frozen embedding dimension.
**Steps:** verify ADR, create index, safe downgrade, test nearest-neighbor query and wrong dimension.
**Acceptance:** index exactly matches profile.

#### V1.3.13 — Implement chunk/embed/index worker

**Goal:** consume index job, chunk normalized document, batch-embed, persist chunks, mark source/document ready, emit C-9.
**Tests:** success, replay idempotency, embedding failure, stale version, wrong tenant.
**Acceptance:** source reaches ready only after complete successful indexing.

#### V1.4.01 — Implement tenant-scoped lexical FTS repository

**Goal:** return ranked active customer/internal-scoped lexical chunks.
**Tests:** match/no-match, disabled source excluded, internal excluded for customer, cross-tenant excluded.
**Acceptance:** filters execute in SQL, not only post-processing.

#### V1.4.02 — Implement tenant-scoped pgvector repository

**Goal:** embed query and return nearest active scoped chunks using frozen profile.
**Tests:** semantic match, no vector, disabled/foreign tenant excluded, embedding failure.
**Acceptance:** exact dimension/profile and query-level filters.

#### V1.4.03 — Implement deterministic hybrid ranker

**Goal:** merge lexical/vector candidates using architect-frozen RRF/weighted formula, dedupe chunks, stable tie-break, topK.
**Tests:** overlap, lexical-only, vector-only, ties, truncation.
**Acceptance:** identical inputs produce identical ordering.

#### V1.4.04 — Implement Retrieval Contract C-3 service

**Goal:** validate C-3, run hybrid retrieval, persist retrieval run/results, build citations, return exact response.
**Tests:** success, empty results, invalid topK, foreign sourceId, unavailable dependency.
**Acceptance:** exact C-3 field names/errors and persisted diagnostics.

#### V1.4.05 — Implement retrieval debugger API

**Goal:** authorized business user can POST a test query and GET stored retrieval diagnostics without running the agent.
**API:** architecture retrieval-query/run routes.
**Tests:** authorized success, empty result, invalid query/topK, foreign source, unauthorized.
**Acceptance:** customer users cannot access diagnostics or internal-scoped knowledge.

#### V1.3–V1.4 build order
`V1.3.05 -> V1.3.06 -> V1.3.07`; parsers `V1.3.08/V1.3.09`; chunk `V1.3.10`; embedding `V1.3.11 -> V1.3.12`; index worker `V1.3.13`; retrieval `V1.4.01/V1.4.02 -> V1.4.03 -> V1.4.04 -> V1.4.05`.

#### V1.5.01 — Create customer/conversation/message/feedback migration

Create `customers`, `customer_identities`, `conversations`, `messages`, `feedback` exactly from Architecture v1.2, including corrected partial unique index on non-null `external_ref` and `resolved_at`. Add upgrade/downgrade and constraint tests. Acceptance: multiple NULL external refs work, duplicate non-null ref fails, message sequence unique per conversation, status checks exact.

#### V1.5.02 — Implement public support tenant/deployment resolver

Resolve active tenant by support slug plus active `customer_web` agent deployment, returning only public-safe metadata. Test active, unknown, suspended, no-active-deployment. Never expose tenant secrets/internal suspension reason.

#### V1.5.03 — Implement signed anonymous customer session

Create/validate short-lived signed anonymous session containing tenant, subject/session, audience, expiry, assurance=`anonymous`. Use approved crypto/session library only. Test expiry, tamper, wrong audience, wrong tenant. Protected operations never silently downgrade to anonymous. Premium security review.

#### V1.5.04 — Implement customer conversation create API

`POST /api/v1/customer/conversations` creates an open AI-owned conversation using trusted tenant/deployment/session context. Request body must not accept tenantId/customerId. Test anonymous success, spoofed tenant input, inactive deployment, cross-tenant token, rate limit. Return safe DTO.

#### V1.5.05 — Implement customer message append + C-2 outbox event

`POST /api/v1/customer/conversations/{id}/messages` accepts `{content}` and required idempotency key, allocates ordered message sequence safely, inserts customer message, updates last_message_at, and writes exact C-2 `agent.run.requested` event in same transaction. Test duplicate key, changed request with same key, concurrent messages, oversize, wrong customer, rollback.

#### V1.5.06 — Implement customer conversation history API

Return only customer-visible messages in sequence order for owning customer. Internal notes, raw tool payloads, raw prompts and agent internals never appear. Test wrong customer/tenant hidden and internal visibility exclusion.

#### V1.5.07 — Implement authenticated customer SSE stream

Implement `GET /api/v1/customer/conversations/{id}/events` with exact public event allowlist from Architecture 5.3/C-12, keepalive, disconnect cleanup, bounded reconnect, strict serialization. Test allowed event, internal event dropped, wrong customer, malformed event, disconnect cleanup.

#### V1.5.08 — Implement customer human-request and feedback APIs

Add human-request and feedback routes. Human request idempotent with reason `customer_requested`; feedback rating 1–5 and comment <=2000. Test repeat human request, valid/invalid feedback, cross-customer access.

#### V1.6.01 — Create agent run/step/retrieval persistence migration

Create `agent_runs`, `agent_steps`, `retrieval_runs`, `retrieval_results` exactly from architecture. Test request-class/status checks, unique step ordinals, retrieval ranks/results and downgrade.

#### V1.6.02 — Consume C-2 and create agent run idempotently

Worker consumes `agent.run.requested`, verifies tenant/conversation/message/deployed agent version, creates one agent_run, carries correlation ID and invokes orchestrator entrypoint. Duplicate event cannot duplicate run. Missing/retired version becomes failed/DLQ plus recoverable customer state.

#### V1.6.03 — Implement central agent budget tracker

Enforce architecture defaults/hard limits for steps, model calls, retrieval calls, tool calls, mutation count, wall clock, tokens and timeouts. Tenant config can be stricter but never exceed hard limit. Test every boundary and wall-clock expiry. Exceeding budget returns `AGENT_BUDGET_EXHAUSTED` before attempted operation.

#### V1.6.04 — Implement strict request classifier

Classify into exactly `deterministic|knowledge|transactional|reasoning|escalation_first` using structured output or approved deterministic fast rule. Persist request_class. Unknown/malformed output fails safe. Test FAQ, status lookup, refund/action, explicit human request, malformed model output.

#### V1.6.05 — Implement budgeted retrieval agent step

Consume retrieval budget, create agent_step, call exact C-3, complete/fail step, return evidence/retrievalRunId. Customer-facing retrieval uses customer scope. Test success, empty, budget exhausted, unavailable dependency, scope enforcement.

#### V1.6.06 — Implement budgeted generation agent step

Assemble approved system instructions + user message + retrieved evidence as untrusted data, call C-4, update token/model-call counters, persist safe step summary without raw sensitive prompt. Test success, token budget, timeout, malicious retrieved instruction remains data, log redaction.

#### V1.6.07 — Implement ordered provider fallback router

Load configured primary/fallback model aliases, skip inactive/invalid providers, respect model-call/wall budgets and provider health, advance only for allowed error classes. No 429 loop. Test primary success, timeout->fallback, 429->fallback, no fallback, auth-error behavior, exhausted budget.

#### V1.6.08 — Implement grounded output guardrail

Before customer-visible answer is persisted, ensure required evidence exists, citation IDs subset actual retrieved chunks, internal-only metadata absent and response bounded. Knowledge requests with zero evidence cannot pass unless approved deterministic path. Test real/fake citations, zero evidence, internal marker, overlength.

#### V1.6.09 — Implement end-to-end knowledge-question state path

Wire explicit states: classify knowledge -> retrieval -> generation -> guard -> persist AI message -> publish safe SSE -> complete run. No unconstrained loop. Test success, no evidence, provider fallback, budget exhaustion, guard failure. Every run ends completed/escalated/failed.

#### V1.7.01 — Create tool/policy/execution/confirmation/approval migration

Create `tools`, `tool_versions`, `policies`, `policy_versions`, `tool_executions`, `action_confirmations`, `approvals` with exact statuses/indexes/uniques. Test duplicate tenant idempotency, one confirmation/approval per execution, invalid risk/status, downgrade.

#### V1.7.02 — Implement typed tool registry + JSON Schema validation

Resolve active tenant tool/version and strictly validate C-5 model arguments against frozen input schema, rejecting unknown fields. Return normalized validated proposal or `TOOL_ARGUMENT_VALIDATION_FAILED`. Test missing/extra/wrong-type, inactive, wrong tenant.

#### V1.7.03 — Implement policy engine C-6

Load correct versioned policy and deterministically return `allow|deny|require_confirmation|require_human_approval`. Missing/malformed mutation policy must deny. Test read allow, missing mutation deny, confirmation, approval, malformed rules, anonymous blocked. Premium security review.

#### V1.7.04 — Implement selected synthetic read-only demo tool

Using exact V1.0.01 demo decision, implement first private status lookup against seeded synthetic data. Validate customer ownership and normalize output. Test success, other customer denied, missing, timeout fixture, invalid args. Never use real private company data.

#### V1.7.05 — Implement selected synthetic protected mutation tool

Implement one exact state-changing demo action from V1.0.01 with preconditions, tenant/customer ownership, idempotency, external_operation_ref and deterministic ambiguous-outcome simulation. Duplicate idempotency returns original outcome. Unknown outcome enters reconciliation, never blind retry.

#### V1.7.06 — Implement customer confirmation lifecycle

Create pending confirmation when C-6 requires it; implement confirm/decline routes, expiry, ownership, one terminal decision, safe SSE event. Test confirm, decline, expired, wrong customer, concurrent double-submit.

#### V1.7.07 — Implement human approval lifecycle and C-7 event

Create pending approval, emit exact C-7, expose list/get/approve/reject APIs, enforce approver capability/tenant/expiry and atomic terminal decision. Test approve/reject/expired/wrong tenant/no capability/concurrent decision.

#### V1.7.08 — Implement policy-enforced tool execution coordinator

Only execution path: C-5 validated proposal -> create tool_execution -> C-6 policy -> optional confirmation/approval -> idempotent adapter execution -> result verification/audit. Blocked tools never call adapter. Unknown mutation outcome becomes reconciliation. Test all four policy outcomes, duplicate idempotency, failure, ambiguous result.

#### V1.7.09 — Implement transactional agent state path

Orchestrator path: generate strict tool proposal -> validate C-5 -> coordinator -> pending confirmation/approval or result -> safe response. Test read success, confirmation, approval, deny, tool failure, malformed args. Model never calls adapter directly.

#### V1.8.01 — Create support queue/escalation/internal-note migration

Create `support_queues`, `escalations`, `internal_notes` with exact priorities/statuses/SLA/indexes. Add up/down and constraint tests.

#### V1.8.02 — Create default support queue for new tenant

Ensure each tenant has exactly one `Default` support queue with approved SLA during tenant creation or frozen lifecycle hook. Test creation, idempotency, rollback. No custom routing yet.

#### V1.8.03 — Implement escalation service C-8

Validate evidence/tool IDs, choose queue, create handoff summary, set conversation `escalated` + human ownership, create escalation and outbox event atomically. Repeated active escalation returns existing case. Test reason codes, duplicate, foreign IDs, rollback.

#### V1.8.04 — Implement support queue/escalation list/detail/assign APIs

Build architecture support routes with pagination/filtering/SLA, queue/object permissions, active tenant-member assignee validation and atomic assign/reassign. Test assignment, invalid assignee, wrong tenant, concurrent assignment, role scopes.

#### V1.8.05 — Implement human message/internal note/resolve/reopen APIs

Human message becomes customer-visible message; internal note separate and never serialized to customer APIs/SSE; resolve/reopen update escalation/conversation and emit safe public events. Test visibility isolation, unauthorized agent, resolve/reopen, stale conflict.

#### V1.5–V1.8 build order
Conversation `V1.5.01 -> 02/03 -> 04 -> 05/06 -> 07 -> 08`; Agent `V1.6.01 -> 02/03 -> 04/05/06 -> 07/08 -> 09`; Tools `V1.7.01 -> 02/03 -> 04/05 -> 06/07 -> 08 -> 09`; Support `V1.8.01 -> 02 -> 03 -> 04 -> 05`.

#### V1.9.01 — Build shared Serviq design tokens and base UI primitives

Implement tokens plus Button, Input, Textarea, Select, Dialog, Toast, Skeleton, EmptyState, ErrorState, PermissionDenied and StatusBadge in `packages/ui`, with Storybook/accessibility tests. Cover focus/disabled/error/loading. Keyboard-operable, no color-only status, no business logic.

#### V1.9.02 — Build authenticated client-console application shell

Responsive sidebar/header/layout, active route, mobile drawer, tenant display/switcher shell, permission-aware nav using backend session/membership. Cover loading/no-memberships/auth-error/success. Hidden nav is not authorization. No horizontal scroll at 375px.

#### V1.9.03 — Build organization onboarding checklist UI

Render provider, knowledge, tool/policy, sandbox/evaluation and publish readiness from backend. Each step incomplete/complete/error/retry and links to page. Never mark complete from local state alone. Test 0%, partial, ready, permission, dependency error.

#### V1.9.04 — Build provider/model management UI

Provider list/add/test/replace/delete and model alias list/create/update. Secret field never repopulated or retained after save. Cover testing pending/success/failure, permission, validation and key absence from DOM/client cache after save.

#### V1.9.05 — Build knowledge source management UI

URL/file forms, source table/statuses, sync/retry/disable actions, document list/detail provenance. Mirror server validation; server authoritative. Cover empty/syncing/ready/failed/disabled/permission.

#### V1.9.06 — Build retrieval debugger UI

Query form, permitted topK/source/access controls, ranked results with score/title/source/location, empty and infrastructure-error states. Customer users cannot access. Browser does not perform ranking.

#### V1.9.07 — Build customer support chat shell and history

Support bootstrap, conversation create/resume, ordered history, responsive composer, send pending/error/retry, preserve failed draft. Do not send tenant/customer IDs from arbitrary browser state. Test new/resume/send/404 tenant/mobile keyboard.

#### V1.9.08 — Add customer SSE streaming, citations, confirmation, approval cards

Subscribe exact C-12 events, dedupe eventId, render message deltas/completion, SourceCitation, ActionConfirmationCard, ApprovalStatusCard, bounded reconnect and recoverable errors. Unknown/internal events ignored and telemetered. Prevent double confirmation.

#### V1.9.09 — Build client conversation review list/detail

Paginated/filterable tenant conversation list and safe timeline with allowed run metadata. Exclude raw prompts, chain-of-thought, secrets and tool internals. Cover loading/empty/error/permission/cross-tenant 404.

#### V1.9.10 — Build human support inbox and case workspace

Queues/case list, filters, assignment/SLA, handoff summary, evidence, tool history, approvals, customer context, internal notes, human response composer, resolve/reassign/reopen. Internal notes visually distinct and never customer API. Test stale conflicts/permissions.

#### V1.9.11 — Build agent configuration/version/publish UI

Agent list/version tabs, draft config, primary/fallback models, budgets, retrieval/citation/tool/policy refs, evaluate, publish, rollback. Published version immutable. Client mirrors hard limits. Test rejection/evaluation/publish/rollback.

#### V1.9.12 — Build team/access management UI

List active/suspended members and pending invitations; create invite with roles; one-time URL; revoke; update roles/suspend; protect last-owner conflict. Cover denied/read-only and expired/revoked invitation states.

#### V1.10.01 — Create usage/audit/platform-control/privacy migration

Create `usage_events`, `audit_events`, `platform_feature_flags`, `rate_limit_policies`, `data_subject_requests` exactly from Architecture v1.2 and seed frozen V1 rate defaults. Test checks/uniques/up/down.

#### V1.10.02 — Implement immutable audit writer + query API

Consume exact C-10, allowlist metadata, append-only audit rows, tenant list/detail filters. Reject secret-bearing metadata. Test duplicate idempotency, tenant isolation, permissions, provider-key redaction.

#### V1.10.03 — Implement usage event ingestion + overview analytics API

Consume C-11 idempotently and expose date-filtered conversation volume, AI resolution/containment, escalation, latency, provider/tool outcomes, retrieval outcomes and estimated model usage/cost. Distinguish estimated vs measured. Test duplicates/date/tenant.

#### V1.10.04 — Build analytics and audit client-console screens

Date-filtered metrics with measured/estimated labels plus audit filters/detail. API error must never display as numeric zero. Cover loading/empty/error/permission.

#### V1.10.05 — Implement platform feature-flag/rate-policy APIs and Valkey cache

PostgreSQL authoritative; Valkey caches config <=60s and runtime counters. GET/PATCH platform routes validate keys/hard ceilings and invalidate cache. Cache outage falls back to DB/frozen safe defaults, never unlimited. Platform operator only; premium review.

#### V1.10.06 — Implement privacy export request/job

Verified customer creates export request, polls, receives short-lived signed download. Job gathers only that customer’s exportable data, writes artifact, expires artifact <=7 days and URL <=24h. Test anonymous denied, cross-customer exclusion, object failure, cleanup.

#### V1.10.07 — Implement privacy deletion/pseudonymization job

Verified customer requests deletion. Idempotent worker applies architecture retention store-by-store, marks customer deleted, removes direct identifiers/content where required, pseudonymizes retained audit refs, records completion. Test restart, tenant isolation, retained pseudonymous audit, duplicate request. Premium privacy review.

#### V1.10.08 — Build platform-operator console V1 screens

Tenants, system health, provider health, queues/jobs/DLQ, feature flags, rate limits, usage and security pages using only platform APIs. Tenant roles denied. No arbitrary SQL/shell/secret display.

#### V1.10.09 — Implement dead-letter list/replay platform APIs

Safe platform-only list/detail/replay. Replay preserves original idempotency key and adds replay sequence; one active replay command per item. Test operator-only, duplicate replay, invalid schema, already-successful conflict.

#### V1.10.10 — Implement retention cleanup scheduler

Durable scheduled jobs for expired invitations, confirmations/approvals, export artifacts, expired idempotency records and app-owned retention. Idempotent, bounded, metric-emitting. Do not delete outside frozen policy.

#### V1.11.01 — Add end-to-end OpenTelemetry trace propagation

Instrument ingress/auth/conversation/agent/retrieval/provider/policy/tool/worker/outbox and propagate trace/correlation. Exporter failure cannot break request. No raw prompt, secret, cookie or unrestricted tool payload in spans. Verify full trace in Tempo.

#### V1.11.02 — Add structured JSON logging + secret/PII redaction

Standardize architecture log fields and redact Authorization, cookies, API keys, passwords, session tokens, provider secrets and raw prompts. Plant fake secrets in tests and assert absence.

#### V1.11.03 — Add required V1 10-scenario E2E suite

Using fake LLM/synthetic demo data automate grounded FAQ, status lookup, protected mutation, confirmation, approval, tool failure, escalation, support takeover, analytics, audit. Tag `portfolio-v1`; failure artifacts secret-safe.

#### V1.11.04 — Add adversarial tenant-isolation API suite

Seed tenant A/B with overlapping data and attack providers, knowledge, conversations, tools, approvals, support, analytics and audit across tenants. Expected 403/404. Any cross-tenant data/side effect release blocker.

#### V1.11.05 — Add baseline k6 REST/SSE load scenarios

Reproducible non-LLM REST, conversation/message fake-agent path, cached deterministic path and concurrent SSE. Report commit, hardware, dataset, duration, concurrency/RPS, p50/p95/p99, errors, fake/real provider flag.

#### V1.11.06 — Implement outbound webhook HMAC delivery with SSRF protections

CCR-001: production HTTPS/443 only, no credentials/fragments, block private/loopback/link-local/metadata/reserved, DNS check save+delivery, peer validation, redirects disabled, 5s connect/10s total, 64KiB response cap, HMAC, bounded retry/DLQ. Premium security review.

#### V1.11.07 — Add release security/quality CI gate

Block release on lint, typecheck, unit, integration, migration up/down, API contracts, tenant isolation, security/secret scans, E2E and docs/link checks. Required jobs no `continue-on-error`. Safe failure reports.

#### V1.11.08 — Publish V1 benchmark evidence report

Write `docs/benchmarks/v1-baseline.md` with exact command, commit, infrastructure, data size, duration, RPS/concurrency, p50/p95/p99, error, bottlenecks and fake/real model. Never claim 10M from architecture.

#### V1.11.09 — Complete V1 public-demo README and non-affiliation disclosure

Product description, architecture links, real public support-corpus disclosure, synthetic private-data statement, non-affiliation disclaimer, verified local setup, demo flows, screenshots, benchmark link and honest limitations. Do not publish copyrighted corpus copies.

#### V1.11.10 — Run V1 release readiness review and create fix-only backlog

Use `product_quality_bar.md` and `code_review.md`. Record Critical/High/Medium findings with exact files/contracts and create micro-fix tasks. Do not broaden into V2. V1 ready only when release blockers and 10 E2E scenarios green.

---

### Phase 2 — V2 Integrations & Omnichannel Scale

Phase 2 starts only after V1 release readiness passes. Before each ticket, architect updates `docs/repo_context.md` and confirms V2 ADR/contracts. Builders never invent vendor payloads/auth/dependencies.

#### V2.0.01 — Run post-V1 repository audit for V2
Re-run Premium Product Builder `repo_audit.md`; update `docs/repo_context.md` with actual V1 paths, versions, service boundaries, tests, auth, deployment baseline and known constraints. Acceptance: later V2 tickets reference current paths.

#### V2.0.02 — Write V2 PRD delta
Create scoped PRD delta for integrations/channels/single-region scale. Freeze vendors/channels, success metrics, non-goals, privacy/security impacts and migration compatibility. No builder ambiguity.

#### V2.0.03 — Write V2 architecture/CCR delta
Freeze V2 API/event/schema/shared-type additions and compatibility plan, including integration adapter, channel envelope, webhook/callback auth, provider-routing cache and scaled deployment boundaries.

#### V2.1.01 — Create Shopify development-store integration metadata migration
Add tenant integration metadata: provider/type, store identifier/domain, secret_ref, scopes/version/status, last-verified timestamps. No plaintext token. Up/down tests.

#### V2.1.02 — Implement Shopify secret/auth adapter
Implement exact Shopify development/test-store auth/token flow frozen by V2 architecture. Server-only tokens, scope validation, rotation/revocation and safe metadata. Mock external calls. Premium security review.

#### V2.1.03 — Implement Shopify connection create/test/disconnect APIs
Tenant APIs save connection metadata, test access, list masked status and disconnect/revoke. Validate store identity/scopes. Test bad token, wrong tenant, revoked token, timeout, rate limit.

#### V2.1.04 — Implement Shopify customer/order read adapter
Typed read-only tools for frozen order/customer lookup against development-store data. Validate ownership mapping, normalize bounded output, never raw Shopify response to LLM. Fixture contract tests.

#### V2.1.05 — Implement Shopify cancel-order action adapter
One frozen protected Shopify mutation through Serviq tool/policy/idempotency pipeline. Validate order state/ownership/idempotency/ambiguous reconciliation. Never bypass C-5/C-6.

#### V2.1.06 — Implement Shopify refund/request action adapter
Exact V2 refund/return action selected by architect, with amount/currency validation, policy preconditions, idempotency/external ref, normalized result, timeout/reconciliation tests.

#### V2.1.07 — Add Shopify integration UI
Connection card/form, test status, scopes, disconnect confirmation and read-only health metadata. Never token. Loading/error/permission and development-store disclaimer.

#### V2.1.08 — Add Shopify V2 E2E scenarios
Development/test-store lookup, protected cancel/refund, provider error, revoked auth, idempotent replay, human escalation on ambiguous result.

#### V2.2.01 — Freeze generic help-desk/CRM connector interface
Architect defines exact adapter methods/events for customer lookup, ticket create/update, handoff, external refs and webhook callback. No vendor yet. Fake connector contract tests.

#### V2.2.02 — Create generic integration registry and credential metadata schema
Versioned connector registration, tenant connection metadata, capabilities, status, secret_ref, last sync/error. Migration/isolation tests. No vendor-specific columns outside frozen metadata.

#### V2.2.03 — Implement connector health/test framework
Reusable service for testing tenant integration with timeout, normalized error, capability report, status persistence and rate limit. Fake connector tests.

#### V2.2.04 — Implement Zendesk-style ticket adapter against sandbox/dev account
Only after V2 architecture names vendor/version. Create ticket + public/internal note + status lookup through generic contract, fixture tests, secret-safe logs.

#### V2.2.05 — Implement external ticket handoff mapping
When escalation selects external help desk, create one ticket, persist external ref, safe handoff summary, idempotent duplicate prevention. Test retry/partial failure.

#### V2.2.06 — Build integration management UI
Generic list/detail capability/status plus vendor-specific config from frozen schema. Cover disconnected/testing/active/error/revoked/permissions.

#### V2.3.01 — Freeze omnichannel inbound/outbound message contract
Normalized envelope for email/SMS/WhatsApp-like adapters: tenant/channel/externalConversation/externalMessage/sender/direction/content/attachment refs/timestamps/idempotency. Contract fixtures.

#### V2.3.02 — Add channel connection metadata migration
Create channel_connections and external thread/message mappings exactly from V2 architecture with tenant/provider/status/secret refs and unique external IDs.

#### V2.3.03 — Implement inbound email adapter using test mailbox/provider
Verify webhook/poll auth, normalize envelope, dedupe external message, map/create Serviq conversation, persist customer message. No direct agent call outside C-2.

#### V2.3.04 — Implement outbound email response adapter
Consume customer-safe Serviq message events and send one threaded reply. Idempotency, bounce/failure status, no internal-note leakage.

#### V2.3.05 — Implement SMS-like channel adapter against sandbox provider
After ADR: inbound verification, phone identity normalization, conversation mapping, outbound replies, opt-out/compliance, rate limits, idempotency. Premium security/privacy review.

#### V2.3.06 — Implement WhatsApp-like channel adapter against sandbox provider
Same normalized contract, approved template/session-window, signature, message dedupe, outbound mapping. Vendor decisions frozen in ADR first.

#### V2.3.07 — Add omnichannel conversation indicators to support inbox
Show channel badge, safe external thread ID, delivery status and send restrictions while reusing conversation model/workspace.

#### V2.4.01 — Add exact response cache layer
Tenant/config/knowledge-version keyed exact cache for deterministic/grounded safe responses. Frozen TTL/invalidation. No private tool result caching unless explicitly safe. Hit/miss/invalidation tests.

#### V2.4.02 — Add semantic cache candidate lookup
Tenant-scoped embedding lookup for cacheable public knowledge questions only. Threshold frozen by evaluation; cached response stores evidence/version. Reject stale knowledge/agent version.

#### V2.4.03 — Add semantic cache safety verifier
Verify tenant, knowledge version, agent version, access scope, no customer-specific intent and threshold before serving hit. Near-match private question must never get public cache.

#### V2.4.04 — Implement capability-aware model router
Route classification/simple grounding/complex reasoning using tenant rules, capability, latency/cost budget and provider health. Strictly bounded/observable. Deterministic route tests.

#### V2.4.05 — Add shadow evaluation mode for candidate model/config
Asynchronously duplicate selected production-safe requests to candidate, discard candidate output from user path, store eval metrics only. Privacy/redaction. No double tool execution.

#### V2.4.06 — Build evaluation comparison UI
Compare versions on correctness, grounding, citations, tool selection, policy, escalation, latency and cost. Explicit gates; model grade not sole truth.

#### V2.5.01 — Containerize API/worker/gateway with production images
Multi-stage OCI, non-root, pinned dependencies, health/readiness, small runtime, SBOM input. CI builds all. No Kubernetes yet.

#### V2.5.02 — Add local multi-replica load profile
Multiple stateless API/worker replicas behind local proxy; verify session/tenant behavior not process-memory dependent. Sticky vs non-sticky tests.

#### V2.5.03 — Add clustered Valkey test profile
Optional V2 profile proving rate/cache logic across replicas. Test node outage and safe fallback.

#### V2.5.04 — Add Kafka partitioning/consumer-group scale tests
Freeze partition keys by tenant/conversation/aggregate; multiple consumers; verify ordering, idempotency, lag and rebalance.

#### V2.5.05 — Create first AWS single-region Terraform foundation
After deployment ADR define network, container runtime, managed Postgres/cache/broker/object storage/secrets, IAM, logs/OTel with no manual prod-critical resources. `terraform plan` only until explicit spend approval. Human Needed.

#### V2.5.06 — Deploy V2 staging in one AWS region
Only after explicit budget/credential approval. Deploy immutable images, migrations, synthetic data, smoke/E2E/security, cost estimate and teardown. Human Needed.

#### V2.5.07 — Add horizontal autoscaling policy and test
Configure API/worker autoscaling using frozen CPU/concurrency/queue-lag. Controlled staging load; record scale latency, saturation, errors, cost. Do not infer 10M.

#### V2.5.08 — Publish V2 single-region benchmark report
Compare V1 baseline vs V2 single region with reproducible fake-provider workload. Record infrastructure/cost, RPS/connections, p95/p99, queue lag, DB/cache saturation, bottlenecks and V3 target.

---

### Phase 3 — V3 Autonomous Enterprise Operations

#### V3.0.01 — Run post-V2 repository audit
Refresh repo_context with actual service extraction, integrations, channels, deployment, metrics, costs, bottlenecks and tests. No stale paths.

#### V3.0.02 — Write V3 PRD delta
Freeze proactive support, multi-agent, multilingual, enterprise isolation, quality/coaching and partitioning scope, measurable outcomes and non-goals.

#### V3.0.03 — Write V3 architecture/contract delta
Freeze workflow-run schema/events, agent handoff, localization model, isolation modes, partition routing, QA/coaching events and service extraction boundaries.

#### V3.1.01 — Create proactive workflow definition/version schema
Versioned tenant workflow definitions, triggers, status, schedule/event conditions, policy refs, agent/tool refs and published versions. Immutable published versions.

#### V3.1.02 — Implement proactive trigger evaluator
Evaluate only approved triggers such as delayed order/repeated failure/SLA/subscription/external event. Creates durable workflow command, never direct message/mutation. Idempotency/replay tests.

#### V3.1.03 — Implement proactive workflow run persistence
Create workflow_runs/steps with status, correlation, tenant, trigger, current step, retries, deadline and terminal outcome. State-transition tests.

#### V3.1.04 — Implement workflow step executor shell
Execute one frozen step type through existing retrieval/model/tool/policy contracts. Enforce budgets/deadlines/persist transitions. No arbitrary code/script step.

#### V3.1.05 — Implement proactive outbound notification gate
Verify tenant policy, channel consent/opt-out, quiet hours, frequency cap and eligibility before proactive message. Denied trigger ends safely with audit reason.

#### V3.1.06 — Add proactive workflow client UI
List workflows, draft/published versions, triggers, allowed tools/channels, test event, publish/rollback and run history. Published immutable. Standard UI states.

#### V3.1.07 — Add proactive workflow E2E suite
Trigger -> policy -> outbound message/action -> customer response -> escalation using synthetic events, including duplicate trigger and opt-out denial.

#### V3.2.01 — Freeze specialist-agent registry contract
Define specialist roles, exact input/output, allowed tools/handoffs. No free-form agent spawning.

#### V3.2.02 — Add specialist-agent configuration schema
Versioned specialist configs, parent refs, model alias, budgets, tools and allowed handoff targets. Migration/isolation tests.

#### V3.2.03 — Implement agent-to-agent handoff contract
Bounded handoff with tenant, parentRun, childAgentVersion, task summary, evidence/tool refs, budget allocation and correlation. Child returns structured result only unless contract permits.

#### V3.2.04 — Implement child-run budget inheritance
Parent allocates bounded subset of remaining model/tool/time/token budget. Child cannot exceed parent. Nested/cancel tests.

#### V3.2.05 — Implement parallel read-only specialist execution
Approved independent read-only children concurrently with bounded fan-out/deadline. Deterministic merge. Mutations serialized through policy coordinator.

#### V3.2.06 — Implement multi-agent trace visualization
Client diagnostic view parent/child runs, timings, evidence/tool summary, model aliases and outcomes without chain-of-thought. Permission/redaction tests.

#### V3.2.07 — Add multi-agent regression/evaluation suite
Cases prove handoff selection, no recursive runaway, budget containment, deterministic merge, mutation serialization and escalation on child failure.

#### V3.3.01 — Add tenant locale/language configuration schema
Persist supported customer languages, default locale, knowledge-language metadata and localization settings. No translation yet.

#### V3.3.02 — Implement language detection contract
Bounded model/deterministic detector with strict language-code output. Low-confidence/unsupported follows PRD fallback.

#### V3.3.03 — Add multilingual knowledge ingestion metadata
Store document/chunk language; preserve original text; prevent cross-language retrieval unless configured. Migration/backfill/tests.

#### V3.3.04 — Implement language-aware retrieval
Filter/prefer correct-language chunks with approved fallback. Test English/Hindi/Spanish fixtures and unsupported isolation.

#### V3.3.05 — Implement localized response generation guard
Respond in selected language; citations reference original approved sources; tool args remain canonical; IDs/codes not translated.

#### V3.3.06 — Internationalize customer/client UI framework
Translation resources, locale routing/selection, localized validation/error copy, date/number formatting. No hard-coded strings in target surfaces.

#### V3.3.07 — Add multilingual E2E/evaluation suite
Grounded FAQ, status, confirmation, escalation, human takeover in selected languages. Score grounding separately from fluency.

#### V3.4.01 — Add tenant isolation mode configuration
Persist logical/dedicated-schema/dedicated-database/dedicated-worker-pool and provisioning status. Default logical; changes platform operator only.

#### V3.4.02 — Implement tenant data-source routing interface
Repositories obtain data source through placement resolver, not global direct DB. Logical maps current DB; dedicated modes use provisioned refs. Callers don't know physical placement.

#### V3.4.03 — Implement dedicated worker-pool routing
Events/jobs carry placement/workload class for isolated tenants. Unknown placement fails safe.

#### V3.4.04 — Add per-tenant encryption-key reference support
Extend secret/object/data encryption adapters to tenant key refs where required. No custom crypto; rotation metadata/audit. Premium security review.

#### V3.4.05 — Implement enterprise data-retention overrides within platform bounds
Tenant-specific approved retention only within min/max/legal/platform constraints. Versioned/audited; cleanup consumes effective policy.

#### V3.4.06 — Build enterprise isolation controls in platform console
Platform operator inspect/provision/change allowed isolation/placement with confirmation/audit. Tenant admin view only.

#### V3.4.07 — Add enterprise isolation adversarial test suite
Run isolation suite across logical/dedicated modes including cache/event/object placement. No fallback to wrong shared tenant data.

#### V3.5.01 — Create quality-review sample schema
Persist sampled conversations, status, rubric version, reviewer, AI evaluator result, human score, defect categories and coaching recommendations.

#### V3.5.02 — Implement deterministic conversation sampling job
Frozen sampling by volume/channel/escalation/risk; no duplicates; exclude privacy-deleted content; async review tasks.

#### V3.5.03 — Implement AI quality evaluator with strict rubric output
Versioned evaluator prompt/schema scores grounding, policy, tool correctness, escalation, tone and resolution. Advisory only; evidence refs, no hidden reasoning.

#### V3.5.04 — Implement human QA review API
Reviewer scores rubric, adds tags/comments, overrides AI score, marks reviewed. Permission/audit and immutable history.

#### V3.5.05 — Build QA review workspace
Queue/list/detail with conversation/evidence/action context, AI advisory score, rubric form, coaching note and filters. Internal only.

#### V3.5.06 — Implement support-agent coaching summary job
Aggregate reviewed defect categories by agent/team/date and generate safe coaching summary from structured data. Do not infer protected traits.

#### V3.5.07 — Extract retrieval service behind stable network contract
Only if measurements justify. Move retrieval module to independent service preserving exact C-3 and contract tests. Caller change only transport adapter.

#### V3.5.08 — Extract tool execution service behind stable network contract
Move tool coordinator/adapters to isolated service preserving C-5/C-6/idempotency/audit. Failure/circuit tests.

#### V3.5.09 — Introduce partition-key routing for high-volume tenant data
Using benchmark evidence, freeze shard/partition key for conversations/events/analytics. Implement routing helper and shadow-read validation before physical move.

#### V3.5.10 — Publish V3 partitioned single-region benchmark
Measure service-extracted partition-aware architecture. Report API/SSE/event/retrieval/tool throughput, DB/cache/broker saturation, cost and multi-region bottlenecks.

---

### Phase 4 — V4 Hyperscale & Multi-Region

V4 starts only after V3 partitioned single-region evidence. It is evidence-driven and does not authorize a 10M claim without reproducible tests.

#### V4.0.01 — Run post-V3 hyperscale repository/infrastructure audit
Update repo_context with topology, partitioning, traffic profiles, DB/cache/broker limits, SSE measurements, IaC/deployment, costs and bottlenecks. V4 targets measured constraints only.

#### V4.0.02 — Write V4 scale PRD with explicit capacity definitions
Freeze separate targets for registered users, concurrent clients, active conversations, REST RPS, agent runs/s, provider calls/s, tool calls/s, retrieval QPS, event throughput, availability, RTO/RPO. 10M staged target, not claim.

#### V4.0.03 — Write multi-region architecture and data-placement contracts
Freeze region model, tenant home region, global/regional control plane, routing, write ownership, replication, failover, residency, global IDs, event routing, cache and unsupported cross-region operations.

#### V4.1.01 — Add tenant region/placement metadata migration
Persist home region, allowed regions, placement version, failover region, residency policy and provisioning state. Backfill existing tenants to current region.

#### V4.1.02 — Implement region-aware tenant placement resolver
Trusted tenant -> allowed regional service/data endpoints from authoritative metadata. Versioned cache. Unknown/stale placement fails closed or frozen redirect, never guesses.

#### V4.1.03 — Add signed global routing token contract
Short-lived server-generated routing token: tenant, region, placement version, audience, expiry. Edge/regional ingress validates; clients cannot choose region. Premium security review.

#### V4.1.04 — Implement region-aware API ingress middleware
Global request -> trusted tenant placement -> local or approved redirect/proxy. Reject mismatch/stale token. Preserve request/trace/idempotency.

#### V4.1.05 — Implement region-aware customer SSE routing
Route stream to home region, preserve reconnect/resume and process independence. Test wrong region, reconnect, failover prep and tenant isolation.

#### V4.1.06 — Add regional service-discovery configuration to IaC
Terraform outputs regional endpoints, DNS/discovery, health targets, certs and env config without hard-coded app region lists.

#### V4.1.07 — Build platform placement view
Platform console home/failover region, placement version/state, health and safe operator migration/failover actions. Tenant admin cannot mutate region.

#### V4.2.01 — Freeze conversation/database shard key ADR
Using V3 benchmark select physical shard strategy/routing key. Document rebalancing, hotspots, global IDs and non-spanning query constraints.

#### V4.2.02 — Implement shard routing library with shadow validation
Repositories request shard handle. Initially shadow-compute target and compare to current location, metric only, no customer move.

#### V4.2.03 — Add shard-placement metadata and migration tooling
Persist shard assignment/range/hash-ring version plus resumable migration state/checksums. No live move yet. Up/down/rollback tests.

#### V4.2.04 — Implement online tenant shard migration copy phase
Copy tenant/partition in bounded batches with checkpoints/checksums while source authoritative. No dual-write. Restart/throttle tests.

#### V4.2.05 — Implement shard migration change-capture/replay phase
Capture/replay writes during copy via frozen outbox/CDC. Preserve aggregate ordering/idempotency. Duplicate/out-of-order tests.

#### V4.2.06 — Implement shard cutover and rollback switch
After consistency checks, atomically change placement version/authoritative shard, keep rollback window, invalidate caches, monitor. Premium database/security review.

#### V4.2.07 — Add hot-tenant workload isolation
Route approved high-volume tenants to dedicated API/worker/retrieval pools without contract changes. Test hot tenant cannot starve standard.

#### V4.2.08 — Partition Kafka topics/consumer groups for hyperscale load
Measured partition counts/keys, consumer autoscaling, lag alarms and rebalance tuning. Ordering/idempotency tests; document max tested throughput.

#### V4.2.09 — Add distributed SSE connection registry/metrics
Track active connections by region/tenant shard using rebuildable state/metrics only as needed. Not authoritative conversation state. Node death cleanup/cardinality tests.

#### V4.2.10 — Implement edge-safe deterministic/semantic cache strategy
Only explicitly cache-safe public/deterministic responses at edge/regional cache with tenant/agent/knowledge version keys. Private/tool responses not edge-cacheable without new contract.

#### V4.3.01 — Define and test regional health/failover decision contract
Freeze health inputs, quorum/timeout, authority, auto/manual conditions, cooldown and split-brain prevention. Simulation evaluator before traffic switch.

#### V4.3.02 — Implement regional control-plane configuration replication
Replicate tenant/agent/provider metadata/policy/placement config per architecture. Secrets follow approved design. Explicit version/conflict rules.

#### V4.3.03 — Implement regional knowledge/index replication workflow
Replicate/rebuild object/document/chunk/index using versioned hashes. Retrieval serves only complete ready regional version. Test stale/incomplete.

#### V4.3.04 — Implement regional conversation failover policy
On home-region failure follow frozen supported mode: read-only degraded, new-conversation alternate, or full replicated failover. Never invent cross-region writes.

#### V4.3.05 — Implement provider-routing by region
Select provider/model respecting BYOK, regional availability/data policy, latency, quotas and fallback. Regulated data never unapproved region.

#### V4.3.06 — Add backup/restore automation and deletion replay verification
Encrypted backups, isolated restore, replay privacy deletions before exposure, integrity checks, measure RTO/RPO, evidence/runbook.

#### V4.3.07 — Add controlled regional failover runbook automation
Operator workflow validates target health, freezes/redirects traffic, updates placement, monitors and rolls back. Confirmation/audit. No unchecked destructive action.

#### V4.3.08 — Run scheduled disaster-recovery game day
Simulate region/service/DB/cache/broker failures in staging, execute runbook, measure actual RTO/RPO/consistency, create fix tasks from gaps.

#### V4.4.01 — Create distributed load-generator architecture
Multiple k6/load-generator nodes so generator not bottleneck. Aggregate synchronized results and prove generator CPU/network headroom. Record topology.

#### V4.4.02 — Add staged SSE concurrency test: 100k connections
Fake-provider/minimal-message workload at 100k concurrent connected clients. Record success, memory, network, p95 delivery, reconnect, error and cost.

#### V4.4.03 — Add staged SSE concurrency test: 500k connections
Only after 100k passes and fixes. Same evidence format; record infrastructure changes and cost.

#### V4.4.04 — Add staged SSE concurrency test: 1M connections
Only after 500k passes. Do not change workload invisibly. Publish failure if unmet.

#### V4.4.05 — Add staged concurrency tests beyond 1M toward 10M
Create procedure/template for later separate 2M, 5M, 10M steps only after evidence and explicit spend approval. This ticket creates procedure, not false result. Human Needed.

#### V4.4.06 — Add REST/API high-throughput cached-path benchmark
Measure stateless cached/deterministic RPS separately from SSE/AI. Increase to first bottleneck; p50/p95/p99/errors/cache hit/CPU/network/DB avoidance. Never call AI RPS.

#### V4.4.07 — Add agent-worker throughput benchmark with fake providers
Measure agent runs/s through queues, retrieval mocks/real local index, policy/tool mocks and fake model. Record queue lag/worker saturation.

#### V4.4.08 — Add retrieval hyperscale benchmark
Measure lexical/vector/hybrid QPS across realistic corpus sizes/shards, topK, p95/p99, cache hit, CPU/memory plus quality checks.

#### V4.4.09 — Add chaos test for API/worker node loss under load
Randomly terminate bounded stateless replicas under staging load. Verify autoscaling/retry/idempotency, no duplicate protected mutation and acceptable recovery.

#### V4.4.10 — Add chaos test for cache/broker degradation
Inject cache loss and broker lag/partition/rebalance. Verify authoritative fallback, backpressure, DLQ/idempotency and no unlimited flood.

#### V4.4.11 — Add chaos test for database shard impairment
Simulate one shard slow/unavailable. Verify bulkheads, tenant-scoped blast radius, safe errors/escalation and no wrong-shard routing. Premium database/security review.

#### V4.4.12 — Add cost-per-million-requests/connections model
Using measured bills/metrics calculate cost by workload: cached REST, SSE connected-hour, retrieval, fake-agent infra and real provider AI separately. Document assumptions/sensitivity.

#### V4.4.13 — Publish V4 multi-region/hyperscale evidence report
Every tested stage, commit, regions, services, instance classes, shard/partition counts, generator topology, dataset, duration, p50/p95/p99, errors, failover, RTO/RPO and cost. State highest actually demonstrated capacity only.

#### V4.4.14 — Run independent release/security architecture review
Premium Product Builder review + threat model + infrastructure/data-consistency review across routing, secrets, region placement, sharding, failover, privacy, idempotency and load evidence. Critical/High findings become micro-fix issues and block V4 claim/release.

---

# Conversion checklist for future Linear creation

- Recheck Serviq Linear issues before creating anything.
- Identify the highest numbered ticket already present.
- Start from the next missing ticket in this file.
- Never recreate an existing issue.
- One heading = one issue.
- Expand compact specification into full Premium Product Builder issue format.
- Keep effort 1–3 hours; if not possible, stop for architect decision.
- Preserve V1/V2/V3/V4 milestone.
- Add `junior-ready` to implementation tickets.
- Add `Vibe-code Ready` only when no human decision/credentials/spend gate exists.
- Add `Human Needed` for architecture decisions, vendor accounts, credentials, legal/privacy judgment or cloud spend.
- Add exact `blockedBy` relationships when prerequisites are mandatory.
- Do not start V2 implementation before V1 release readiness, V3 before V2 gates, or V4 before V3 scale evidence.
- Do not claim 10M capacity unless reproducibly demonstrated.


## Backlog reconciliation notes

- The staged list above is preserved from the supplied canonical staging file.
  It contains compact conversion candidates, not automatically builder-ready
  issue bodies.
- Before creating a Linear issue, expand one candidate into the full detailed
  format used by OPE-251–OPE-304 and run the ticket intake checklist.
- The uniform “1–3 hours” claim is not accepted for deployment, multi-region,
  game-day, high-concurrency, or independent-review work. Re-estimate those
  after their prerequisite architecture and evidence exists.
- Do not create V2 tickets until the V1 release gate is earned; apply the same
  evidence gate from V2 to V3 and V3 to V4.
- Do not bulk-create all 198 issues. Create the next dependency-ready tranche
  so Linear remains an execution system rather than a speculative inventory.
