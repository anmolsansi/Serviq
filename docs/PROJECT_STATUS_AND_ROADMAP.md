# Serviq Product Status and Roadmap Reconciliation

> Evidence snapshot: 2026-08-22, repository `main` at `258d189`. Sources:
> current code/tests, repository specifications, the supplied engineering
> playbook and staged ticket file, live Linear, and live GitHub.

## Product intent

Serviq is a multi-tenant AI customer-operations platform, not a generic
chatbot. A complete flow retrieves grounded tenant knowledge, identifies the
customer, invokes only typed customer-specific tools, applies deterministic
policy, requests confirmation or approval, executes idempotently, reconciles
side effects, escalates with context, and leaves an audit record.

The product has three trust surfaces: a tenant/workforce console, an
end-customer experience, and a separately controlled platform console. V1 uses
a synthetic delivery-support journey plus a separate synthetic payment/refund
integration. V2 broadens channels and integrations; V3 focuses on enterprise
controls; V4 explores global scale and ecosystem features. V2–V4 are roadmap
intent, not implemented capabilities.

## Current truth

### Done

- Monorepo, quality tooling, Compose infrastructure, CI, security workflows,
  and release-source reconciliation.
- Workforce OIDC, users, organizations, memberships, invitations, roles, and
  permission enforcement.
- Provider/model CRUD and connectivity foundations with protected credentials.
- Knowledge URL/sitemap registration and PDF/Markdown/text uploads.
- Nine migrations through knowledge permissions.
- Substantial focused Python tests/static checks for implemented behavior.

### Partial

| Capability | Existing evidence | Missing acceptance evidence |
|---|---|---|
| Knowledge | records, uploads, storage, schema | safe fetch, parse, embed, index, retrieval quality |
| Providers | normalized adapters/connectivity tests | production routing, budgets, fallback in agent flows |
| Worker | service and health foundation | durable jobs, retries, idempotent recovery |
| Web apps | three separated Next.js apps | workflows, accessibility, frontend tests, browser E2E |
| Observability | optional local stack | app traces/metrics, SLOs, alerts, runbooks |
| Delivery | quality/security workflows | staging acceptance, rollback/recovery evidence |

### Left for V1

- ingestion, embeddings, indexing, hybrid retrieval, and citation quality;
- customer identity, conversations/messages, SSE, and bounded agent runtime;
- synthetic tools with policy, confirmation, approvals, reconciliation, and
  compensation;
- support inbox, takeover, ownership, notes, tags, and resume;
- tenant, customer, and platform product interfaces;
- analytics, audit, privacy, retention, and operational controls;
- app observability, E2E/load testing, deployment, and launch evidence.

The honest status is **foundation implemented; end-to-end V1 not yet built**.

## Tracker reconciliation

Linear displayed V1 at 95% and V2–V4 at 0%. Its 55 created issues were 51 Done,
one In Progress, and three In Review. OPE-300, OPE-302, OPE-303, and OPE-304
were non-terminal even though their relevant changes were merged. Those
statuses should be reconciled. OPE-305 is historical execution evidence, not a
new product feature.

The V1 percentage is not product completion: it covers only the created
foundation/history set and excludes the staged backlog, including 77 V1 items.

GitHub had no open pull requests or issues. Local and remote `main` agreed at
the latest OPE-304 reconciliation merge. GitHub agrees with the source; Linear
has workflow-status debt.

The supplied backlog contains 198 tickets not yet represented in Linear:

| Phase | Tickets | Character |
|---|---:|---|
| V1 | 77 | ingestion, runtime, tools, support, UI, operations, launch |
| V2 | 38 | channels, integrations, product breadth |
| V3 | 41 | enterprise controls, governance, scale |
| V4 | 42 | global scale, ecosystem, advanced platform |
| **Total** | **198** | planning inventory, not an accepted estimate |

V1 breakdown: V1.3 9, V1.4 5, V1.5 8, V1.6 9, V1.7 9, V1.8 5,
V1.9 12, V1.10 10, V1.11 10.

The compact tickets are useful as a dependency map, but are not uniformly
builder-ready. Several nominal 1–3 hour items contain deployment, high-scale
performance, multi-region recovery, security review, or game-day programs.
Re-estimate demonstrated scope and risk rather than counting tickets.

## Recommended execution sequence

1. Reconcile the four stale Linear statuses with merged evidence.
2. Decide the embedding provider/model, dimension, index/distance choice,
   hybrid ranking formula, and retrieval benchmark before schema hardens.
3. Build the ingestion spine: SSRF-safe fetch, extraction, normalization,
   chunking, embeddings, indexing, durable jobs, deletion, and visible errors.
4. Prove tenant-isolated hybrid retrieval with deterministic citations and a
   non-empty end-to-end ingestion benchmark.
5. Build customer auth, conversation/message state, resumable SSE, execution
   budgets, and durable agent semantics.
6. Complete one vertical synthetic delivery/refund flow through typed tools,
   policy, confirmation/approval, idempotency, reconciliation, compensation,
   handoff, and audit.
7. Add UI and operations around behavior already proven.
8. Earn V1 with integration, browser, load, security, privacy, backup/restore,
   rollback, and deployed staging acceptance before V2.

Do not bulk-create all 198 Linear issues now. Create the next dependency tranche
only when decisions and acceptance contracts are ready. Keep V2–V4 at theme
level until V1 evidence changes the design. This prevents the planning system
from becoming a second product.

## Decisions required

| Decision | Why | Latest responsible point |
|---|---|---|
| Embedding profile/index | fixes vector schema, cost, retrieval behavior | before embedding migration |
| Hybrid ranking/benchmark | prevents unmeasurable tuning | before retrieval acceptance |
| Customer identity/session | defines tenancy, privacy, ownership | before customer APIs |
| Customer attachments | changes malware, storage, privacy, retention, UI | before conversation schema freezes |
| Production secret store | credentials need a production boundary | before real staging vendors |
| Deployment/ownership | determines migration, rollback, incidents | before staging release work |
| E2E/load harnesses | release gates need executable proof | before feature-complete claims |
| Retention/deletion | crosses messages, documents, audit, backups | before persistent customer data |

## Staff Engineer devil's-advocate assessment

### Verdict

The foundation is credible and the next vertical tranche is buildable, but the
full roadmap is **not ready for blind execution**. It mixes executable work,
unresolved architecture choices, aspirational scale targets, and operational
programs under one uniform small-ticket estimate.

### Principal risks

- **Security/privacy:** SSRF, trust-surface separation, exfiltration, credential
  storage, attachment safety, and derived-data deletion need threat evidence.
- **Tenant isolation:** every query, job, cache key, vector lookup, stream, and
  telemetry signal—not only routes—must preserve organization scope.
- **Idempotency:** agent/tool/payment/refund/approval/reconciliation retries need
  stable operation keys and replay tests.
- **Migration/rollback:** production backup, restore, expand/contract rollout,
  and rollback proof are absent.
- **Observability:** app traces, redaction, cardinality limits, SLOs, alerts, and
  runbooks are future work.
- **Deployment:** no accepted staging/production topology or ownership exists. A
  source release is not a product release.
- **Testing:** 61 API integration tests were skipped in this audit, frontend
  suites do not exist, and E2E/load targets intentionally fail.
- **Scope economics:** 198 uniformly small tickets hide high variance and risk
  premature V2–V4 work before V1 evidence.

Keep the selected modular monolith, durable worker, gateway, PostgreSQL, and
S3-compatible boundaries. Prove one support journey before adding services,
general orchestration, extra channels, or global abstractions. Prefer database
constraints, stable operation IDs, and explicit states over new infrastructure.

## Verification performed

- local and remote `main` alignment and clean starting worktree;
- architecture graph and repository-wide source inventory;
- supplied and repository product/architecture documents against code;
- live Linear and GitHub state;
- TypeScript lint/type-check passed; its test command ran no tests;
- API: 78 passed, 61 skipped; worker: 5 passed; gateway: 93 passed;
- Ruff and mypy passed for all Python services;
- Compose configuration rendered successfully.

Not verified: security scanners, enabled PostgreSQL/object-storage integration,
browser flows, load, external providers, deployment, backup/restore, rollback,
or real-device acceptance.

## Source-of-truth order

1. deployed acceptance evidence;
2. current code, migrations, and tests;
3. live GitHub merge state;
4. live Linear state;
5. approved PRD/architecture/ADRs;
6. staged tickets and planning playbooks.

Planning documents describe intent. They do not override code or prove a
capability shipped.

The ticket-level evidence, tracker reconciliation, audit-discovered follow-up
issues, and complete staged V1–V4 inventory are maintained in
`OPE_251_304_COMPLETION_AUDIT_AND_REMAINING_LINEAR_TICKETS.md`.
