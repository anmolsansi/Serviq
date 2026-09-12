# Serviq Product Status and Roadmap Reconciliation

> Evidence snapshot: 2026-09-12, `main` / `origin/main` at `3e1b9aa`.
> Detailed source, diagnostic and CI evidence: [system audit](SYSTEM_AUDIT_2026-09-12.md).

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
chunking, and the deterministic fake embedding gateway/profile.

The last milestone is V1.3.11 / OPE-319 (merged PR #222). It fixes vector dimension
1536 but does not provide semantic embeddings or an index. The next original
roadmap step is V1.3.12; its index/operator/migration decisions remain open.

## Integration gaps that change the execution order

1. The API has no runtime session/principal composition. Trusted user/tenant state
   is read but never populated; integration tests inject it. V1.1.16 must connect
   the existing OIDC/upsert/membership boundaries before usable authenticated APIs.
2. Frozen async SQLAlchemy dependencies fail on macOS arm64 because greenlet is
   omitted. V1.0.28 must make runtime dependencies portable.
3. Gateway validation 422s reflect raw embedding input, including unauthenticated
   malformed requests. V1.3.11A must satisfy the existing privacy contract.
4. File size/concurrency controls apply after multipart spooling; durable upload
   cleanup has no scheduled caller. V1.3.04C/D cover resource admission and recovery.
5. URL sync raw versions bypass file-byte accounting; stale/crashed writes and
   concurrent raw-object identity need recovery evidence (V1.3.07A).
6. No parse consumer persists normalized artifacts or produces the index handoff
   assumed by V1.3.13 (V1.3.09A). Successful fetch leaves a source `syncing`.
7. Sitemap support and real semantic embedding transport have no active runtime
   implementation (V1.3.07B / V1.3.11B); their product/contract decisions are explicit.
8. Main is unprotected with no rulesets. Existing [GitHub #205](https://github.com/anmolsansi/Serviq/issues/205)
   remains the single administrative work item (V1.0.29).

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

The [canonical inventory](SERVIQ_REMAINING_LINEAR_TICKETS_FULL.md) has 215 total
records: 14 implemented records retained for traceability and 201 backlog records.
It adds the previously omitted implemented V1.3.06A publisher and 10 audit follow-ups.
This is a record count, not effort, a completion percentage or a Linear issue count.

The live Serviq project query returned 17 issues: 12 Done, 3 In Progress and 2 In
Review. OPE-306/307 are implemented with closed GitHub issues but remain In Progress;
OPE-303/304/305 also remain nonterminal. Those states were recorded, not changed.
GitHub had no open PRs and one open issue (#205) at audit time. Earlier 55-issue/95%
claims describe an old tracker snapshot and must not be used as current status.

## Remaining V1 product work

- Durable normalization/index pipeline, semantic embeddings, vector migration and
  tenant/access-scoped retrieval with measured relevance and citations.
- Customer identity/ownership, conversations/messages, SSE and bounded agent state.
- Typed synthetic tools, policy, confirmation, human approval and idempotent side effects.
- Support queues, escalation, human messages/notes/assignment/resolution.
- Authenticated console, provider/knowledge management, customer chat and operator UI.
- Audit/usage, analytics, privacy export/deletion, retention and dead-letter operations.
- App telemetry, isolation/E2E/load/security gates, benchmarks, release acceptance.

V2–V4 remain staged product/architecture work. Do not bulk-create or execute those
phases before the preceding phase's accepted scope and evidence justify it.

## Verification and limits

- 315 local tests passed: API 87, worker 120, gateway 104, frontend 4.
- 84 local integration tests skipped because their infrastructure was unavailable.
- All Python/web lint and typechecks passed; all frozen Python locks checked.
- All three web apps built with webpack. Default Turbopack builds were blocked by
  subprocess port binding even after elevated retry; default build acceptance remains unverified.
- Compose config passed; Docker daemon/socket was absent locally.
- `make e2e` and `make load-test` failed as explicit unimplemented targets.
- Local production dependency audits found no known vulnerabilities.
- Current-main CI/Security passed; DB migration/integration, object storage and
  Keycloak validator checks ran there. Worker/quota integration evidence is from
  earlier PR heads; see the audit for exact jobs, SHA and counts.
- No deployed application, real provider call, browser support flow, load result,
  backup/restore or production rollback was verified.

## Staff Engineer assessment and next tranche

Release risk is high despite passing component tests. The weakest assumption is
that individually tested helpers are already connected through real trust and
persistence boundaries. The runtime probes disproved that for authentication and
portable async dependencies; code composition shows the ingestion gap.

Keep the current modular API, durable worker, gateway, PostgreSQL and object-store
architecture. Fix proven runtime/privacy failures and enforce merge checks, then
freeze session composition and ingestion handoffs. Decide vector operator/index,
semantic model/profile compatibility and reindex cutover. Prove one non-empty,
tenant-isolated upload/fetch → normalize → chunk → embed/index → retrieve path.
Then implement the customer/agent/support journey with thin product UIs around it.

A fake-only vertical slice is a viable low-cost contract test. It cannot replace
semantic relevance evaluation. Adding another service would increase operational
work without resolving the missing composition; no new service is recommended.

Needs Architect Decision: server session/cookie/CSRF/tenant-switch contract;
normalized persistence/index event; URL/sitemap lifecycle; vector metric/index and
provider compatibility; production secrets, deployment and incident ownership.
Recovery acceptance needs a disposable staging database, guarded migration plan,
backup/restore, pending-job preservation and rollback evidence. Existing CI
migration reversibility is useful but does not prove data recovery in production.

## Source-of-truth order

Current deployed acceptance, current source/tests, live GitHub, live tracker state,
then accepted PRD/ADRs and staged plans. A planning document never proves a feature
shipped. The [Build Guide](SERVIQ_BUILD_GUIDE.md) explains actual behavior and usage;
[repo_context.md](repo_context.md) records paths and implementation boundaries.
