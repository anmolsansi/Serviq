# Serviq Product Status and Roadmap Reconciliation

> Original evidence snapshot: 2026-09-12, `main` / `origin/main` at `3e1b9aa`.
> V1.1.16 authentication/session status updated 2026-09-13.
> Detailed original source, diagnostic and CI evidence: [system audit](SYSTEM_AUDIT_2026-09-12.md).

## Current truth

**Backend foundations are implemented; the complete V1 application is not.**
The three Next.js apps remain scaffold pages. A customer cannot yet ask a
question, receive a grounded streamed answer, approve an action, or reach a
human inbox. The intended demo uses synthetic delivery support and separate
synthetic payment/refund data, with no real-money movement.

Completed implementation slices include tooling/CI/security, workforce and tenant
primitives, organization/member/invitation APIs, provider/model management and
adapters, knowledge registration/uploads and durability/quota controls, transactional
outbox/sync publication, URL/file fetch with parse handoff, pure normalization and
chunking, and the deterministic fake embedding gateway/profile. The backend now
also composes opaque workforce browser sessions into the trusted request-principal
boundary, with server-owned active tenant selection and membership-validated tenant
switching. The client-console UI that consumes that contract remains future work.

The original audited milestone was V1.3.11 / OPE-319 (merged PR #222). It fixes
vector dimension 1536 but does not provide semantic embeddings or an index. The
next original roadmap step is V1.3.12; its index/operator/migration decisions remain
open. Audit follow-ups may execute out of numerical order when they close a proven
runtime or security boundary, as V1.1.16 does.

## Integration gaps that change the execution order

1. **V1.1.16 resolved at the backend trust boundary.** Authorization Code + PKCE
   creates an opaque Valkey workforce session. Middleware restores trusted user and
   verified identity state, plus an optional server-owned active tenant, before
   protected route dependencies run. `POST /auth/tenant` revalidates membership
   before changing context. Client-controlled tenant headers are not authorization.
   V1.9.02 still owns the usable client-console shell and tenant-switch UI.
2. **V1.0.28 resolved.** Async SQLAlchemy now declares the portable asyncio/greenlet
   dependency required by supported runtime environments.
3. **V1.3.11A resolved.** Private gateway authentication and bounded/redacted
   validation now execute before unsafe request-body reflection.
4. File size/concurrency controls still apply after multipart spooling (V1.3.04C).
   The missing durable upload-cleanup runtime caller was separately resolved by
   V1.3.04D.
5. URL sync raw versions bypass file-byte accounting; stale/crashed writes and
   concurrent raw-object identity need recovery evidence (V1.3.07A).
6. No parse consumer persists normalized artifacts or produces the index handoff
   assumed by V1.3.13 (V1.3.09A). Successful fetch leaves a source `syncing`.
7. Sitemap support and real semantic embedding transport have no active runtime
   implementation (V1.3.07B / V1.3.11B); their product/contract decisions are explicit.
8. **V1.0.29 resolved.** Main now enforces branch protection, required status checks,
   and conditional integration gates.

These are missing connections and failure paths, not a reason to rebuild the
working validators, parsers, chunker or outbox publisher.

## Reconciled inventory and tracker

| Phase | Remaining implementation/backlog records |
|---|---:|
| V1 | 80 |
| V2 | 38 |
| V3 | 41 |
| V4 | 42 |
| **Total** | **201** |

These counts are the 2026-09-12 inventory snapshot. The
[canonical inventory](SERVIQ_REMAINING_LINEAR_TICKETS_FULL.md) had 215 total
records: 14 implemented records retained for traceability and 201 backlog records.
V1.1.16 is an audit follow-up tracked through GitHub rather than a dedicated Linear
issue, so completion of that follow-up should not be misreported as a Linear state
transition or silently used to recalculate the historical inventory counts.

The live Serviq project query from the original audit returned 17 issues: 12 Done,
3 In Progress and 2 In Review. OPE-306/307 had implemented code and closed GitHub
issues but remained In Progress; OPE-303/304/305 also remained nonterminal. Those
states were recorded, not changed. V1.1.16 has no dedicated Linear issue to reuse;
do not create a duplicate solely to mirror the GitHub follow-up.

## Remaining V1 product work

- Durable normalization/index pipeline, semantic embeddings, vector migration and
  tenant/access-scoped retrieval with measured relevance and citations.
- Customer identity/ownership, conversations/messages, SSE and bounded agent state.
- Typed synthetic tools, policy, confirmation, human approval and idempotent side effects.
- Support queues, escalation, human messages/notes/assignment/resolution.
- Authenticated client-console product UI around the completed backend session contract,
  plus provider/knowledge management, customer chat and operator UI.
- Audit/usage, analytics, privacy export/deletion, retention and dead-letter operations.
- App telemetry, isolation/E2E/load/security gates, benchmarks, release acceptance.

V2–V4 remain staged product/architecture work. Do not bulk-create or execute those
phases before the preceding phase's accepted scope and evidence justify it.

## V1.1.16 authentication/session contract

V1.1.16 deliberately reuses the existing FastAPI API, OIDC validator, workforce
mapper, tenancy service, PostgreSQL membership data and Valkey. It does not add a
new service or database migration.

The browser receives an opaque `serviq_session` cookie. Its server-side record owns
the internal workforce user ID, verified identity fields, optional active tenant
and random CSRF token. Middleware restores those values into trusted request state.
A tenant is selected automatically only when exactly one active membership exists.
Otherwise the client must use the authenticated tenant-switch endpoint, which
validates the requested membership in PostgreSQL before updating the session.

The selected tenant is routing context, not a cached permission grant. Tenant-
scoped services continue to enforce current active membership and capability data.
A supplied `X-Serviq-Tenant-ID` value therefore cannot switch authorization context.
State-changing auth operations require the session-bound CSRF token. Session-store
outage returns a stable fail-closed 503. Post-login redirects must match the exact
configured client origin, preventing host-prefix redirect tricks. ADR-030 contains
the full decision and rollback behavior.

## Verification and limits

The original 2026-09-12 audit recorded:

- 315 local tests passed: API 87, worker 120, gateway 104, frontend 4.
- 84 local integration tests skipped because their infrastructure was unavailable.
- All Python/web lint and typechecks passed; all frozen Python locks checked.
- All three web apps built with webpack. Default Turbopack builds were blocked by
  subprocess port binding even after elevated retry; default build acceptance remains unverified.
- Compose config passed; Docker daemon/socket was absent locally.
- `make e2e` and `make load-test` failed as explicit unimplemented targets.
- Local production dependency audits found no known vulnerabilities.

V1.1.16 adds HTTP-level regression coverage that does not override trusted principal
dependencies. It covers real opaque-session request composition, forged tenant-header
resistance, membership-validated tenant switching, CSRF failures/success, exact-
origin redirect rejection, missing/expired sessions, and safe session-store outage
behavior. Final acceptance still requires CI, Security and the repository's required
integration gates on the exact final PR head. Passing CI is not deployed acceptance.

No deployed application, real provider call, browser support journey, load result,
backup/restore or production rollback is claimed by this follow-up. The rollback is
code-only because V1.1.16 has no database migration; incompatible sessions can be
discarded and users can reauthenticate.

## Staff Engineer assessment and next tranche

The original audit's weakest assumption was that individually tested auth helpers
were already connected through a real request trust boundary. V1.1.16 closes that
specific backend composition defect rather than adding another identity service or
trusting a browser-selected tenant. The remaining product risk moves upward to the
actual client-console login/session UX and outward to the unfinished ingestion,
retrieval, customer, agent, tool/policy and support journeys.

Keep the current modular API, durable worker, gateway, PostgreSQL and object-store
architecture. Complete the ingestion handoffs, decide vector operator/index and
semantic model/profile compatibility, and prove one non-empty, tenant-isolated
upload/fetch → normalize → chunk → embed/index → retrieve path. Build the V1.9.02
client-console shell against the V1.1.16 `/auth/session` and `/auth/tenant` contract
instead of inventing a second auth mechanism. Then implement the customer/agent/
support journey with thin product UIs around proven service boundaries.

A fake-only vertical slice is a viable low-cost contract test. It cannot replace
semantic relevance evaluation. Adding another service would increase operational
work without resolving the remaining composition; no new service is recommended.

Remaining architect decisions include normalized persistence/index event, URL/
sitemap lifecycle, vector metric/index and provider compatibility, production
secrets, deployment and incident ownership. Recovery acceptance needs a disposable
staging database, guarded migration plan, backup/restore, pending-job preservation
and rollback evidence. Existing CI migration reversibility is useful but does not
prove data recovery in production.

## Source-of-truth order

Current deployed acceptance, current source/tests, live GitHub, live tracker state,
then accepted PRD/ADRs and staged plans. A planning document never proves a feature
shipped. The [Build Guide](SERVIQ_BUILD_GUIDE.md) explains actual behavior and usage;
[repo_context.md](repo_context.md) records paths and implementation boundaries.
