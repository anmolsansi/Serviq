# Serviq system audit — 2026-09-12

## Verdict and scope

**High risk for release; foundation implemented, complete V1 application not available.**
The audit started with a clean `main`, fetched `origin`, and confirmed both at
`3e1b9aa0a9b6d38238d844a1eeb96aaa89365a02`. This is an audit and documentation
change, not implementation of the remaining product. No deployment, tracker
mutation, commit, PR, or merge is part of this change. Existing GitHub #205 is
reused as the reference for repository protection. No target release or new
main Linear issue was invented.

Code, entrypoints, migrations, tests, ADRs, and live GitHub/Linear were inspected.
The MCP graph was consulted first, but returned an older knowledge service and
worker map; current source was used when graph results were insufficient.
The 50 audit checks below adapt the microtask workflow to this documentation
request. Their completion means an area was assessed, not that its feature ships.

## What works, and where execution stops

| Area | Implemented boundary | Missing boundary |
|---|---|---|
| Identity and tenancy | OIDC validator, workforce upsert, membership/RBAC services, organization/invitation/member routes | Actual HTTP session/authentication composition and server-owned active tenant context; browser PKCE login |
| Providers | Credential storage adapter, provider/model CRUD, normalized generation/streaming adapters, internal connectivity test | Production secret storage, agent-driven generation/budgets/fallback and live vendor acceptance |
| Knowledge admission | URL/sitemap metadata; validated file upload; durable cleanup intent; tenant quotas and Valkey rate limits | Pre-parser file byte/concurrency boundary; scheduled cleanup; complete source lifecycle management |
| Durable ingestion | Transactional sync event, PostgreSQL-to-Kafka publisher, URL/file fetch, versioned document and parse outbox handoff, retries/DLQ | Parse consumer/persistence/index handoff; sitemap traversal; raw URL object budget/recovery |
| Transformations | Pure PDF/Markdown/text/HTML normalizers and deterministic heading-aware chunker | Runtime consumer wiring and persistence of normalized/chunked output |
| Embeddings | Private deterministic fake route; alias `serviq-embedding-v1`, 1536 dimensions, 100 inputs, 32,000 characters/input | Semantic provider embeddings, input-safe validation errors, vector dimension/index migration |
| Retrieval | `knowledge_chunks.tsv` and GIN schema foundation | Tenant/access-filtered lexical/vector repositories, ranker, C-3 service, debugger, relevance evidence |
| Customer/agent/support | Product contracts and roadmap | Customer sessions, conversations/messages/SSE, bounded agent, tools/policy/approval, human handoff |
| Web | Three separate Next.js App Router scaffold pages and 4 smoke/config tests | Authenticated workflows, support chat, settings, inbox, analytics, platform controls |
| Operations | Local Compose, source quality/security/release workflows; subsystem runbooks | Enforced merge checks, app telemetry/alerts, privacy jobs, deployment and recovery acceptance |

Successful sync deliberately leaves a source `syncing`: `services/worker/app/jobs/knowledge_sync.py`
creates the document and `serviq.knowledge.parse.v1` outbox obligation, while
`services/worker/app/main.py` runs only publication and sync consumption. No
consumer calls the pure normalization/chunking libraries or makes sources ready.
A document marked `active` and a recent `last_synced_at` do not prove indexing.
ADR-027 explicitly says fake vectors are not semantic embeddings or relevance evidence.

## Findings and follow-up ownership

Priorities describe release impact, not proof of an exploit in a deployed system.
Proposed IDs below are local backlog identifiers, not newly created Linear issues.

| ID / priority | Finding and evidence | Required outcome |
|---|---|---|
| V1.1.16 / P1 | `services/api/app/core/principal.py` reads `request.state.serviq_user_id`, `serviq_workforce_identity`, and `serviq_tenant_id`; `app/main.py` installs no auth middleware and no production code writes those fields. Route integration tests override principal dependencies. Live Keycloak tests call the validator directly. | Wire the architecture's server session → verified identity → internal user → authorized tenant boundary; prove HTTP requests without principal overrides. Coordinate with V1.9.02. |
| V1.0.28 / P1 | API and worker declare plain `sqlalchemy`, whose locked greenlet marker omits macOS `arm64`. Frozen environments lack greenlet. Closing an API async session raises `ValueError: the greenlet library is required to use this function`; an ordinary organization request returns 500 locally. | Declare the supported asyncio dependency surface, regenerate frozen locks, and test session lifecycle on Apple Silicon and Linux. |
| V1.3.04C / P1 | `knowledge/router.py` awaits `request.form(...)` before `create_file_source` checks file size and reserves concurrency. `max_part_size` does not bound file parts in the installed parser. | Enforce streamed total/file limits and request admission before temporary-file spooling; close multipart resources on all paths. |
| V1.3.11A / P1 | Gateway has no custom validation-error handler. A 32,021-character synthetic embedding input produces a 32,178-byte 422 response containing the input, with or without authentication. Body validation happens before the route-body token check. This contradicts ADR-027's no-raw-input response rule. | Redact validation errors; authenticate and bound request bodies before expensive parsing; cover malformed and oversized authenticated/unauthenticated requests. This reflects the caller's input, not another tenant's data. |
| V1.0.29 / P1 | GitHub reports `main.protected=false`, no rulesets, and branch protection 404. Existing issue [#205](https://github.com/anmolsansi/Serviq/issues/205) remains open. | Enforce PR and quality/security/integration gates using stable check contexts; handle path-filtered jobs without deadlocking unrelated PRs. |
| V1.3.09A / P1 | Only sync/retry topics are consumed. Parse event is durable but has no runtime consumer; V1.3.13 starts at an index job without an implemented producer for that handoff. | Freeze and implement normalization persistence and index handoff, with stale-version, tenant, retry, replay and crash tests. |
| V1.3.04D / P1 | `reconcile_due_upload_cleanups` exists in API cleanup service but has no production scheduler/caller. Worker starts only sync/publisher loops. | Run bounded durable cleanup continuously, preserve tenant/key validation, expose exhaustion and prove restart recovery. |
| V1.3.07A / P1 | URL sync writes a new `/sync/{version}/raw` object without upload byte reservations/cleanup intents. File quota does not cover URL versions. PUT occurs before the final database lock/version recheck. S3 file reads use unbounded `body.read()`. | Budget and reconcile fetched versions, bound reads, and prove stale/crashed/rebalanced fetch cleanup and raw-byte immutability. Same-version concurrent overwrite is a code-review risk; no live race reproduction was run. |
| V1.3.07B / P2 | API accepts `sitemap`; `run_knowledge_sync` rejects it terminally with `KNOWLEDGE_SYNC_SOURCE_TYPE_UNSUPPORTED`, as ADR-023 requires. | Explicitly decide whether V1 exposes unsupported registration or adds bounded permitted traversal. Do not call sitemap ingestion complete. |
| V1.3.11B / P1 before semantic acceptance | `_resolve_adapter` always returns `FakeLLMAdapter`; hash-derived vectors have no semantic relevance. No remaining ticket explicitly owns real embedding transport. | Freeze provider/model/profile compatibility, secret access, timeout/cost/retry limits and data reindex policy before enabling semantic retrieval. Preserve the offline fake for tests. |

Additional existing roadmap work remains necessary:

- **V1.3.12–13:** dimension/index migration, chunk/vector persistence, atomic ready-state
  transitions, stale-version cleanup and index cutover. The current vector column is
  dimensionless and has no ANN index; a GIN text index is not a vector search service.
- **V1.4.01–05:** access-scoped retrieval, hybrid ranking and grounded citations.
- **V1.5–8:** customer ownership/session boundary, messages/SSE, bounded agent,
  idempotent tools, policy/confirmation/approval and human case lifecycle.
- **V1.9.01–12:** design primitives and all three usable product surfaces. Existing
  browser config lists zero tests; client-console auth UI must depend on V1.1.16.
- **V1.10:** immutable audit/usage events, analytics, operator controls, privacy
  export/deletion, retention and DLQ operations. Upload cleanup scheduling should
  not wait for a broad customer-data retention project.
- **V1.11:** trace propagation, safe logging, ten-scenario E2E, adversarial isolation,
  load/REST/SSE tests, outbound webhooks, benchmark and release acceptance.
- **Deployment:** no deployed URL or running application was verified. Production
  secret-store selection, backup/restore, migration recovery, rollout topology and
  operating ownership are still release gates. Local file secret storage has only
  an in-process lock; multi-process production safety is not established.

## Verification ledger

Local runtime: macOS Apple Silicon, Node `25.8.1`, Python `3.14.0`, uv `0.12.3`.
CI pins Node `24.18.0`, Python `3.14.6`, uv `0.12.9`, pnpm `10.15.0`.
The environment's default pnpm differed; the cached CI-pinned pnpm was used for
the successful frozen install. These local results are not exact CI-toolchain parity.

| Check | Result | Scope/limit |
|---|---|---|
| Fetch/checkout | PASS | Clean main already matched origin at the audited SHA |
| `uv lock --check` in all services | PASS | Frozen lock freshness only; does not detect missing optional asyncio extras |
| Frozen install | PASS with pinned pnpm + each `uv sync --frozen` | Initial default pnpm failed on noninteractive purge/build policy; transient generated config was removed |
| `pnpm test` | PASS: 4 tests | One Vitest smoke/config file; Playwright list reports 0 tests |
| API pytest | PASS: 87; SKIP: 76 | Database, object storage, Valkey and Keycloak opt-in tests not run locally |
| Worker pytest | PASS: 120; SKIP: 8 | Broker/database/object-storage integration not run locally |
| Gateway pytest | PASS: 104 | Mocked provider/fake embedding coverage; no paid vendor call |
| Web lint/typecheck | PASS | All workspace scripts present ran |
| Ruff/mypy | PASS | API 119, worker 29, gateway 23 files checked by mypy |
| Default `next build` | ENVIRONMENT BLOCKED | Turbopack subprocess port binding failed with `Operation not permitted`, including elevated retry |
| `pnpm --filter './apps/*' exec next build --webpack` | PASS | All three static apps built; alternate compiler evidence, not default Turbopack acceptance |
| Compose config | PASS | `docker compose -f infra/docker/compose.yml --profile '*' config --no-interpolate --quiet` |
| Local Docker integration | BLOCKED | Docker socket absent; no local migrations or infrastructure startup executed |
| `make e2e`, `make load-test` | EXPECTED FAIL | Explicit unimplemented targets, exit 2 |
| Production dependency audits | PASS | pnpm audit and pip-audit 2.10.1 against frozen exports: no known vulnerabilities on this run |
| Live deployment/browser journey/load/recovery | NOT VERIFIED | Application features and environment absent |

Totals: **315 local tests passed; 84 skipped**. Do not add CI test counts to this
number: CI reruns overlapping suites.

### GitHub evidence checked live

- Audited SHA [CI run 34502946052](https://github.com/anmolsansi/Serviq/actions/runs/34502946052):
  quality, database integration, object storage and live Keycloak jobs passed.
  Logs show 67 database tests passed / 9 skipped, one object-store test passed,
  six Keycloak tests passed, and the same default unit counts as above.
  Migration upgrade, downgrade to `20260814_0002`, re-upgrade, and downgrade to base passed.
- Audited SHA [Security run 34502945992](https://github.com/anmolsansi/Serviq/actions/runs/34502945992):
  Python/TypeScript CodeQL, Gitleaks, Trivy and dependency audit passed.
  This is CI scanner evidence from September 10, not a newly executed local CodeQL/Trivy scan.
- [Knowledge Sync run 34317215569](https://github.com/anmolsansi/Serviq/actions/runs/34317215569)
  and [Outbox Publisher run 34317215575](https://github.com/anmolsansi/Serviq/actions/runs/34317215575)
  passed at earlier PR head `1879ba91cbdebb5dfea806af0e451f84cd2911d2`.
- [Knowledge Quota run 33875483187](https://github.com/anmolsansi/Serviq/actions/runs/33875483187)
  passed at earlier PR head `f7ab06fb361ecae4eb52bd96615e4aca89a39e1f`.
  These three path-filtered workflows are PR-only and are **not current-main integration reruns**.

### Targeted diagnostic observations

1. Unmodified API with repository test configuration and a synthetic bearer header:
   organization GET returned 500 because async session cleanup lacks greenlet.
2. Replacing **only** the database session dependency with a no-op isolated the
   principal boundary: organization GET returned `401 UNAUTHENTICATED`, validator
   invocation count was zero, and `app.user_middleware` was empty. No identity or
   tenant dependency was overridden. This diagnoses missing composition; it is
   not a real-Keycloak authenticated success test.
3. Installed `Request.form(max_part_size=8)` accepted a 32-byte file part.
   This small synthetic probe proves the parameter does not impose file size;
   it does not load-test disk exhaustion. Runtime validation still rejects
   over-limit uploaded files, but after parsing/spooling.
4. Oversized synthetic gateway embedding input returned 422 and reflected raw
   input with and without a bearer header. Only booleans/lengths/status were
   retained; no real document or credential was used.

## Tracker and inventory reconciliation

The live Serviq project query returned 17 issues: 12 Done, 3 In Progress,
2 In Review. This is the returned project membership, not a reconstruction of
all historical OPE-251–319 issues. The earlier 55-issue/95% snapshot is obsolete.

| Live issue | State | Reconciliation |
|---|---|---|
| OPE-308–319 | Done | Upload durability/quota, frontend harness, safe fetch, sync, publisher, normalization, chunking, dependency remediation, fake embeddings |
| OPE-306 | In Progress | Immutable actions implemented; GitHub #173 closed; CI policy passes. Tracker closeout pending. |
| OPE-307 | In Progress | Live validator coverage implemented; GitHub #175 closed; current-main Keycloak CI passes. Tracker closeout pending; HTTP login still absent. |
| OPE-303 | In Review | File upload slice exists; preserve review state and distinguish new admission finding. |
| OPE-304 | In Progress | Release automation exists; no product deployment acceptance inferred. |
| OPE-305 | In Review | Historical execution record, not a new runtime capability. |

The canonical inventory now retains 14 implemented records (13 previously
listed plus the omitted V1.3.06A publisher), and 201 implementation/backlog
records: V1 80, V2 38, V3 41, V4 42. The 201 includes 10 new audit follow-ups;
two implemented records still have nonterminal Linear closeout. Counts measure
records, not effort or completion percentage. Known defects remain separately
visible even when the original implementation slice is retained as implemented.

## Recommended sequence and unresolved decisions

First fix portable async dependencies and gateway validation exposure, enforce
#205, and freeze the workforce session handoff. In parallel planning terms,
finish ingestion prerequisites before V1.3.13: pre-parser admission, automatic
cleanup, URL object lifecycle, and durable parse persistence. Then freeze
V1.3.12 index/operator behavior and real embedding transport; prove a non-empty
tenant-isolated ingestion-to-retrieval slice before customer/agent/UI work.

Keep the current API + worker + gateway architecture. Connecting the existing
boundaries is lower cost than introducing another orchestration service. A
fake-only vertical slice is useful for repeatable contract tests, but a semantic
benchmark requires a real approved profile and data provenance.

Needs Architect Decision: session storage/cookie/CSRF/logout and tenant-switch
contract; normalized artifact/index event contract; vector distance/index and
existing-data migration; provider/model compatibility and reindex policy;
bounded URL/sitemap/source lifecycle; production secrets and operational owner.
These are targeted intake blockers, not a reason to redo completed pure libraries.

Deployment acceptance requires a dedicated environment, migration and rollback
plan, verified backup/restore, isolated secrets, bounded telemetry, and one full
synthetic support journey. Do not replay destructive migration downgrades on a
shared or production database merely because CI exercises a disposable one.

## Audit microtask ledger

Each item is roughly 2% of this audit. Definition of done: inspect the named
boundary, record an executable result or explicit evidence limit, and reconcile
the affected documentation. Dependencies: baseline checks 01–05 precede source
assessment; checks 41–50 use all preceding evidence. These are audit checkpoints,
not 50 feature tickets or artificial commits. Checkpoints after each five items
reassessed evidence scope; no skipped integration test became a passing check.

| # | Assessed boundary / definition of done | Result |
|---|---|---|
| 01 | Read skills and applicable instructions | Assessed |
| 02 | Preserve initial worktree and confirm remote | Clean |
| 03 | Fetch origin and check out latest main | Verified SHA |
| 04 | Inspect branches, open PRs/issues | No open PR; #205 open |
| 05 | Reconcile live Linear project snapshot | 17 returned issues |
| 06 | Compare graph with current entrypoints | Stale graph fallback documented |
| 07 | Verify manifests and runtime pins | Local/CI drift recorded |
| 08 | Check all Python locks | Passed |
| 09 | Refresh frozen dependency environments | Passed with pinned pnpm |
| 10 | Map all three frontend entrypoints | Scaffolds |
| 11 | Inspect OIDC validator and live test boundary | Library tested; HTTP gap |
| 12 | Trace request principal population | Missing |
| 13 | Inspect workforce upsert and disabled user handling | Implemented service |
| 14 | Inspect organization/member/permission integration | Dependency overrides noted |
| 15 | Inspect invitations and trust boundaries | Implemented routes; session prerequisite |
| 16 | Inspect provider/model API composition | Implemented slice |
| 17 | Inspect credential storage boundary | Local encrypted adapter |
| 18 | Inspect gateway generation/connectivity composition | Adapter/connectivity slice |
| 19 | Inspect embedding profile and route | Fake-only |
| 20 | Probe gateway validation/privacy boundary | Reproduced reflection |
| 21 | Inspect knowledge registration/upload API | Implemented slice |
| 22 | Inspect quota accounting and admission order | Pre-parser gap |
| 23 | Probe multipart file-size behavior | File limit not enforced there |
| 24 | Trace durable upload cleanup caller | Scheduler absent |
| 25 | Inspect sync command transaction/versioning | Implemented slice |
| 26 | Inspect publisher transaction/retry boundary | Implemented; earlier integration evidence |
| 27 | Inspect consumer offsets/retries/DLQ | Implemented; earlier integration evidence |
| 28 | Inspect raw URL/file lifecycle and sitemap | Budget/recovery/traversal gaps |
| 29 | Inspect normalizers and chunker activation | Pure libraries only |
| 30 | Inspect vector/FTS schema and retrieval | Dimension/index/service gaps |
| 31 | Inventory customer/agent/tool/support runtime | Absent product subsystems |
| 32 | Inventory telemetry/privacy/retention | Mostly future work |
| 33 | Run API suite and portable session probe | 87 pass/76 skip; greenlet defect |
| 34 | Run worker suite | 120 pass/8 skip |
| 35 | Run gateway suite | 104 pass |
| 36 | Run frontend smoke/browser listing | 4 pass/0 browser tests |
| 37 | Run Python/web lint and types | Passed |
| 38 | Attempt default builds and alternate compiler | Turbopack blocked; webpack passed |
| 39 | Validate Compose and local infrastructure access | Config passes; Docker absent |
| 40 | Exercise E2E/load targets | Explicit failures |
| 41 | Inspect current-main quality/migration jobs | CI passed; limits recorded |
| 42 | Inspect worker/quota integration workflow evidence | Earlier heads only |
| 43 | Inspect CI scanners and run dependency audits | No known dependency vulnerabilities |
| 44 | Verify branch protection/rulesets | Absent; #205 reused |
| 45 | Assess deployment/backup/recovery readiness | Not demonstrated |
| 46 | Reconcile repository context | Current paths and limitations |
| 47 | Reconcile build guide | Current behavior and usage |
| 48 | Reconcile implemented records/backlog counts | 14 implemented/201 backlog |
| 49 | Define focused audit follow-ups and dependencies | 10 local candidate records |
| 50 | Review documentation links/counts/diff and report limits | Final documentation review |
