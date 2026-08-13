# PRD: Serviq — Production V1

**Status:** Product decisions synchronized v1.2  
**Product:** Serviq  
**Audience:** Product, engineering, design, QA, security, DevOps, and contributors  
**Document authority:** This PRD defines what Production V1 must do. `ARCHITECTURE.md` defines how it is built. `TECH_STACK.md` freezes technology choices. `PRODUCT_SPECIFICATION.md` describes the longer-term product.

## 1. Problem

Businesses want AI support systems that can answer questions and take useful actions, but most chatbot demos are unsafe or incomplete in production. They often lack grounded knowledge, tenant isolation, authorization, reliable tool execution, human handoff, observability, and a way for business teams to govern the system without changing code. Serviq must provide one production-quality customer operations platform that businesses can configure and customers can use end to end.

## 2. Users

- **End Customer:** asks support questions, receives grounded answers, performs permitted actions, confirms sensitive actions, requests a human, and gives feedback.
- **Tenant Owner:** owns the business organization in Serviq and controls organization settings, members, providers, integrations, and security-sensitive configuration.
- **Tenant Administrator:** manages day-to-day organization configuration, members, knowledge sources, agents, policies, and integrations.
- **Support Manager:** manages support queues, assignments, SLAs, escalations, and support quality.
- **Support Agent:** handles escalated conversations, sees the AI handoff package, communicates with customers, and resolves cases.
- **Knowledge Manager:** adds, syncs, disables, and validates approved knowledge sources.
- **AI Configuration Manager:** configures model providers, routing, prompts, run budgets, tools, and agent versions.
- **Analyst/Auditor:** reviews operational metrics, AI-quality metrics, and audit history without mutation permissions.
- **Serviq Platform Operator:** operates Serviq itself across tenants, including health, incidents, provider status, queue health, feature flags, and platform-level abuse controls.

## 3. Goals

1. A new tenant can move from an empty organization to a published customer-support agent without a source-code change.
2. The reference demo passes 100% of its required end-to-end scenarios for grounded answers, tool actions, confirmation, approval, escalation, human takeover, analytics, and audit history.
3. Every sensitive mutation is preceded by a recorded policy decision and produces a durable audit event.
4. Automated tenant-isolation tests report zero cross-tenant reads or writes across API, database, retrieval, cache, event, and tool boundaries.
5. Under the documented reference load, non-LLM API paths target p95 latency below 300 ms. Scale claims are published only with reproducible benchmark configuration and results.

## 4. Non-Goals

Production V1 intentionally does **not** include the following. These are deferred rather than implemented at reduced quality.

- Voice, phone, email, SMS, WhatsApp, or social-message channels.
- Serviq billing, subscriptions, invoicing, or marketplace packaging.
- Verified 10 million concurrent-user capacity or 10 million requests per second. The architecture keeps a scale-out path, but those numbers require measured proof.
- Multi-region active-active production deployment.
- A dedicated vector database or dedicated search cluster unless V1 measurements prove PostgreSQL-based retrieval insufficient.
- Real private customer, order, payment, or ticket data from the public companies referenced by the portfolio demo.
- Autonomous high-impact actions that tenant policy marks as human-only.
- Arbitrary model-generated code execution, arbitrary shell execution, or unrestricted database access.
- Multilingual product guarantees. Production V1 user-facing copy and evaluation are English-first.

## 5. V1 Scope

1. **Organization and workforce access [MAS-1].** A user can create an organization, invite members, assign supported roles, switch between organizations they belong to, and manage tenant-scoped settings. Server-side authorization is required for every protected action.
2. **BYOK AI providers [MAS-2].** An authorized user can connect OpenAI, Anthropic, Gemini, or OpenRouter with a provider key, test connectivity, mask the saved credential after creation, choose a default model, and configure ordered fallbacks.
3. **Knowledge sources [MAS-3].** An authorized user can register approved web URLs, sitemap/source manifests, PDF files, Markdown files, and plain-text files. The system shows `pending`, `syncing`, `ready`, `failed`, and `disabled` states. Source provenance and version history are retained.
4. **Grounded retrieval [MAS-4].** Serviq performs tenant-scoped hybrid retrieval over active knowledge, returns source provenance with each result, excludes disabled/deprecated content, and can expose retrieval diagnostics to authorized business users.
5. **Customer support conversation [MAS-5].** A customer can start or resume a conversation, send messages, receive streamed responses, see citations when enabled, retry recoverable failures, request a human, and submit feedback. Anonymous and tenant-verified customer sessions are supported as separate policies.
6. **Bounded agent runtime [MAS-6].** Every agent run follows explicit states, maximum step/model/tool budgets, timeout budgets, and deterministic completion, failure, or escalation outcomes. The model cannot bypass policy or tool boundaries.
7. **Customer context and typed tools [MAS-7].** The Production V1 reference configuration is the DoorDash reference support/delivery domain plus a separate Stripe reference payment domain, with all private customer/order/delivery/payment/refund/support records kept synthetic. The source-manifest policy is `doordash-stripe-allowlist-v1`. The first three frozen tool keys are exactly `demo.get_delivery_order_status` (read-only status), `demo.check_order_resolution_eligibility` (read-only eligibility/policy), and `demo.create_refund` (protected mutation). The public demo never claims DoorDash uses Stripe, never accesses DoorDash private systems, and never moves real money.
8. **Policy, confirmation, and approval [MAS-8].** Mutating tools are deny-by-default unless a tenant policy allows them. A policy can allow, deny, require customer confirmation, or require human approval. Approved execution is idempotent, expiry-aware, and audited.
9. **Human escalation and support inbox [MAS-9].** Serviq can escalate automatically or on customer request. The handoff includes customer context, conversation summary, evidence, tool history, policy decisions, errors, pending approvals, reason code, and recommended next action. A support agent can take over and resolve or reassign the case.
10. **Client configuration console [MAS-10].** Business users receive a polished console for onboarding, knowledge, AI agents, providers, tools, policies, conversations, support inbox, team/access, and environment settings. Permission-denied states are explicit and never rendered as generic errors.
11. **Analytics and audit [MAS-11].** Authorized users can view conversation volume, AI resolution/containment, escalation, latency, tool outcomes, provider outcomes, retrieval outcomes, cache effectiveness, feedback, estimated AI usage/cost, and queryable audit events for security-sensitive activity.
12. **Platform operations [MAS-12].** Serviq operators can view tenant lookup, system health, provider health, queue lag, worker health, failed jobs/dead-letter state, feature flags, platform rate-limit controls, global usage, and security/audit events through a separate trust boundary.
13. **Production quality foundation [MAS-13].** The repository includes local reproducible startup, CI, security scanning, automated tests, observability hooks, migration discipline, contract-change control, rate/failure handling, and repeatable performance tests. The deterministic/mock mode must run without paid external AI calls.

## 6. Future Scope (V2+)

- Voice and telephony support with speech-to-text and text-to-speech.
- Email, SMS, WhatsApp, Slack/Teams, and social-channel adapters.
- Real Shopify and other commerce integrations using development/test environments first.
- CRM/help-desk integrations such as Zendesk, Salesforce, HubSpot, or equivalent systems.
- Additional domain packs for SaaS, travel, hospitality, fintech, and other industries.
- Multilingual retrieval, evaluation, and localized business/user interfaces.
- Billing and usage plans for a hosted Serviq SaaS offering.
- Advanced quality management, agent coaching, workforce forecasting, and QA sampling.
- Dedicated search/vector infrastructure when measured scale requires it.
- Region-aware tenant placement, dedicated tenant deployments, and multi-region active-active serving.
- Additional autonomous workflows only after policy, evaluation, and audit controls exist for the domain.

## 7. User Flows

### 7.1 Client Onboarding and Publish

1. Tenant Owner signs in and clicks **Create organization**.
2. System creates the tenant and opens the onboarding checklist.
3. Owner invites team members and assigns roles.
4. AI Manager adds at least one supported provider key and tests it.
5. Knowledge Manager adds at least one approved source and waits for `ready` status.
6. Administrator configures allowed tools and action policies.
7. AI Manager creates a draft agent version and runs sandbox scenarios.
8. System shows evaluation results and blocking failures.
9. Authorized user publishes the version.
10. System creates an immutable published version and exposes the customer channel configuration.

### 7.2 Grounded Customer Question

1. Customer opens the support experience.
2. System identifies the tenant and creates or resumes the customer session.
3. Customer sends a question.
4. System classifies the request and checks deterministic/cache paths.
5. Retrieval searches only active knowledge for that tenant.
6. Agent produces a response grounded in retrieved evidence.
7. Output validation checks the response and citation references.
8. Customer receives a streamed answer and citations when the tenant enables them.
9. Conversation and run metadata are persisted for authorized review.

### 7.3 Customer-Specific Read

1. Customer asks for account/order/status information.
2. Serviq determines whether the current customer identity is sufficient.
3. If insufficient, customer sees a verification-required state instead of protected data.
4. Agent proposes the typed read-only tool.
5. Policy layer validates tool and customer access.
6. Tool returns normalized verified data.
7. Customer receives an answer based on the verified tool result.

### 7.4 Protected Mutation

1. Customer requests a state-changing action.
2. Agent proposes a typed action and arguments.
3. Policy engine returns `allow`, `deny`, `require_confirmation`, or `require_human_approval`.
4. If confirmation is required, the customer sees an explicit action summary and confirms or cancels.
5. If human approval is required, Serviq creates an approval task and informs the customer that review is pending.
6. Approved execution uses an idempotency key.
7. Serviq verifies the tool result and records the final state.
8. Customer sees completed, pending, or failed status in plain language.

### 7.5 Human Escalation and Takeover

1. Escalation is triggered by policy, low evidence, repeated bounded failures, explicit customer request, or a human-only action.
2. Serviq creates an escalation with a reason code and target queue.
3. Support Agent sees the full handoff package.
4. Agent accepts or is assigned the case.
5. Customer sees that a human has joined.
6. AI mutation execution is paused unless the workflow explicitly permits a pending approved action.
7. Human responds, uses allowed tools, adds internal notes, and resolves or reassigns the case.
8. Resolution outcome is recorded for analytics and future evaluation.

### 7.6 Provider Failure

1. Agent requires a model call.
2. Primary provider times out, rate-limits, or returns a normalized provider error.
3. Gateway attempts the configured fallback only if the run budget and tenant policy allow it.
4. If a deterministic or retrieval-only response remains safe, Serviq returns it.
5. Otherwise Serviq escalates or returns a temporary-failure state without inventing an answer from model memory.
6. Provider failure, fallback, latency, and final outcome are observable.

### 7.7 V1 Reference Missing-Item / Refund Flow

1. Customer reports a missing or incorrect item in the DoorDash reference support domain.
2. Serviq retrieves only approved/permitted support knowledge from the explicit `doordash-stripe-allowlist-v1` manifest. It does not use unrestricted crawling or bypass source access controls.
3. `demo.get_delivery_order_status` reads the synthetic order and delivery state.
4. `demo.check_order_resolution_eligibility` evaluates the synthetic order/item/delivery/payment state and Serviq demo resolution rules.
5. If a refund is allowed, Serviq requests customer confirmation and human approval when the configured rule requires it.
6. `demo.create_refund` creates an idempotent synthetic refund record. The deterministic V1 demo does not move real money and does not modify DoorDash or Stripe production systems.
7. The result, policy decision, confirmation/approval, and idempotency reference are auditable and available to human support if escalation is needed.

## 8. Roles & Permissions

`yes` means allowed in V1, `no` means denied, `scoped` means limited to assigned queues/resources, and `policy` means an additional tenant policy must authorize the action.

| Action | Owner | Admin | Support Manager | Support Agent | Knowledge Manager | AI Manager | Analyst/Auditor | Platform Operator |
|---|---|---|---|---|---|---|---|---|
| Edit organization settings | yes | yes | no | no | no | no | no | platform-only |
| Invite/remove tenant members | yes | yes | no | no | no | no | no | platform-only |
| Assign tenant roles | yes | yes | no | no | no | no | no | platform-only |
| Manage provider credentials | yes | yes | no | no | no | yes | no | no secret value access |
| Manage knowledge sources | yes | yes | read | read | yes | read | read | incident-only scoped access |
| Configure/publish agents | yes | yes | read | no | no | yes | read | no |
| Configure tools/policies | yes | yes | read | no | no | yes | read | no |
| View tenant conversations | yes | yes | yes | scoped | read | read | read | incident-only scoped access |
| Resolve/reassign escalations | yes | yes | yes | scoped | no | no | no | incident-only |
| Approve protected actions | policy | policy | policy | policy | no | policy | no | no |
| View analytics | yes | yes | yes | scoped | scoped | yes | yes | platform aggregate only |
| View tenant audit events | yes | yes | scoped | own actions | scoped | scoped | yes | incident-only scoped access |
| Manage tenant API/webhook credentials | yes | yes | no | no | no | scoped | no | no secret value access |
| Manage global feature/rate controls | no | no | no | no | no | no | no | yes |
| View cross-tenant platform health | no | no | no | no | no | no | no | yes |

End-customer permissions are not workforce roles. Customer access is determined by tenant channel policy, verified identity context, ownership, and action policy.

## 9. Data Model (conceptual)

- **Tenant** has many memberships, agents, provider connections, knowledge sources, customers, conversations, tools, policies, support queues, usage records, and audit events.
- **User** is a workforce identity and may have memberships in multiple tenants.
- **Membership** connects a user to one tenant and one or more roles/capabilities.
- **Provider Connection** stores non-secret provider metadata and a reference to encrypted BYOK credentials.
- **Agent** has versioned immutable published **Agent Versions** and active deployments.
- **Knowledge Source** produces versioned **Knowledge Documents** and **Knowledge Chunks** with source provenance.
- **Customer** represents a tenant-scoped end customer and may have external identity references.
- **Conversation** has ordered **Messages**, participants, one or more **Agent Runs**, feedback, and optional escalation.
- **Agent Run** has ordered **Agent Steps**, retrieval runs, policy decisions, and tool executions.
- **Tool** is a versioned typed capability backed by an integration or demo adapter.
- **Policy** has immutable versions used to decide tool access and approval requirements.
- **Confirmation** records an end-customer confirmation request and outcome.
- **Approval** records a human approval task, expiry, decision, and actor.
- **Escalation** belongs to a support queue and tracks assignment, SLA state, handoff context, and resolution.
- **Audit Event** is append-oriented and records security-sensitive configuration and business actions.
- **Outbox Event** guarantees reliable publication of domain events committed with transactional state changes.

The V1 reference demo additionally uses synthetic entities defined by CCR-003: `demo_customers`, `demo_orders`, `demo_order_items`, `demo_deliveries`, `demo_order_events`, `demo_payments`, `demo_refund_rules`, `demo_refunds`, and `demo_support_cases`. These are reference/demo-domain records and are not DoorDash or Stripe private data.

Exact columns, constraints, indexes, retention, and deletion behavior are owned by `ARCHITECTURE.md` and migrations.

## 10. APIs (conceptual)

The backend must expose capabilities for:

- organization, membership, and role management;
- provider connection and model configuration;
- agent draft/version/publish/evaluation operations;
- knowledge source registration, sync, document inspection, and retrieval debugging;
- customer conversation create/read/message/stream/feedback/human-request operations;
- typed customer-context and business-tool execution through internal protected interfaces;
- confirmation and approval lifecycle;
- escalation queues, assignment, takeover, notes, and resolution;
- analytics and usage views;
- queryable audit events;
- platform health, provider health, queue health, failed jobs, feature flags, and platform controls;
- outbound webhooks and future connector callbacks.

Exact routes, request/response shapes, status codes, pagination, error envelopes, and event contracts are frozen in `ARCHITECTURE.md` and later ticket contracts.

## 11. Frontend Requirements

Every data-driven screen must implement loading, empty, error, permission-denied when relevant, and success states. Every mutation must prevent double submission and show success or failure feedback.

| Screen/Surface | Purpose | Required V1 behavior |
|---|---|---|
| Customer Support | Customer conversation | Stream responses, show citations, action/confirmation cards, retry, escalation status, human transition, feedback, mobile and keyboard accessibility. |
| Organization Onboarding | Configure a new tenant | Checklist with provider, knowledge, tool/policy, test, and publish progress. Failed steps remain resumable. |
| Overview | Business health snapshot | Show core volume, resolution, escalation, latency, provider/tool health, and setup warnings. Empty state guides first configuration. |
| Conversations | Search/review conversations | Paginated/filterable list with status and customer. Detail shows timeline and run metadata allowed by role. |
| Support Inbox | Human escalation workspace | Queues, filters, assignment, SLA, timeline, handoff summary, evidence, action history, approvals, notes, composer, resolve/reassign. |
| Knowledge Sources | Manage approved knowledge | Add supported source, view sync states, disable source, inspect documents/provenance, retry failed sync. |
| Retrieval Debugger | Validate grounding | Enter a test query, inspect ranked tenant-scoped results and provenance, and see no-result/error states. |
| AI Agents | Configure behavior | Draft/version list, provider/model selection, run budgets, retrieval/tool/policy references, sandbox test, publish, rollback. |
| Models & Providers | BYOK configuration | Add/test/delete provider connection, mask stored secrets, choose default/fallback model order, show provider health errors safely. |
| Tools & Policies | Govern actions | View typed tools, enable/disable by agent, configure allow/deny/confirmation/approval policy, test with sandbox context. |
| Analytics | Review operations | Date-filtered metrics with loading/empty/error states and clear distinction between measured values and estimates. |
| Audit Logs | Review sensitive activity | Paginated/filterable immutable event view with actor, action, resource, outcome, time, and correlation ID. |
| Team & Access | Manage workforce | Invite/remove member, assign roles, show pending invitations and permission errors. |
| Platform Console | Operate Serviq | Tenant lookup, health, providers, queues/jobs, failed/dead-letter items, feature flags, rate/abuse controls, usage, security events. |

## 12. Backend Requirements

- All externally visible APIs are versioned and validate body, path, query, headers, and upload metadata server-side.
- Every protected route declares authentication and authorization requirements explicitly.
- Tenant ownership is enforced at query/service boundaries rather than by client filtering.
- All external calls use explicit timeouts, typed failures, and bounded retries only when safe.
- Mutations that may be retried use idempotency keys and return the original result for duplicate successful execution where contractually defined.
- Background work that must survive process failure is durable and never relies only on an in-process task.
- Required jobs include knowledge sync, document parse/index, embedding/index build, webhook delivery, analytics aggregation, notification, provider/tool reconciliation, and dead-letter reprocessing.
- Public customer message endpoints, authentication-sensitive endpoints, provider-calling endpoints, uploads, exports, and webhooks are rate-limited. Exact defaults are frozen in `ARCHITECTURE.md`.
- Webhooks are signature-verified, duplicate-safe, and acknowledge quickly before durable asynchronous processing.
- Uploaded knowledge files are type/size validated, stored with generated object keys, and processed as untrusted content.
- Retrieved content, user messages, tool output, and model output are untrusted data. Model output must be schema-validated before it can influence a tool or policy decision.
- No production feature depends on a mandatory paid SaaS service for local deterministic/mock development.

## 13. Micro-Architecture Systems

- **MAS-1 Tenant & Workforce Access** — organizations, memberships, roles/capabilities, tenant switching, protected workforce sessions. Depends on: repository foundation only. Outbound dependencies: tenant/auth context contract used by every tenant-facing MAS.
- **MAS-2 AI Provider Gateway & BYOK** — provider credentials, model aliases, connectivity test, default/fallback configuration, normalized generation interface. Depends on: MAS-1. Outbound dependencies: normalized model contract consumed by MAS-6.
- **MAS-3 Knowledge Source Lifecycle** — source registration, supported file/URL ingestion requests, sync state, document provenance/version lifecycle. Depends on: MAS-1. Outbound dependencies: indexed knowledge contract consumed by MAS-4.
- **MAS-4 Retrieval & Grounding** — tenant-scoped lexical/vector retrieval, hybrid ranking, filters, citations, retrieval debugger contract. Depends on: MAS-3. Outbound dependencies: evidence contract consumed by MAS-6 and MAS-9.
- **MAS-5 Customer Conversation Experience** — customer session, conversation/message lifecycle, streaming, citations UI, retry, human request, feedback. Depends on: MAS-1 tenant resolution. Outbound dependencies: message/run request contract consumed by MAS-6 and escalation state from MAS-9.
- **MAS-6 Agent Runtime & Routing** — bounded state machine, request class, deterministic path, retrieval/model/tool planning, budgets, result verification, output guardrail, completion/escalation. Depends on: MAS-2, MAS-4, MAS-5. Outbound dependencies: tool proposal to MAS-7, policy request to MAS-8, escalation request to MAS-9.
- **MAS-7 Customer Context & Tool Execution** — tenant-scoped typed tool registry, synthetic DoorDash-reference order/delivery/support and Stripe-reference payment/refund adapter, the three CCR-003 tool contracts, input/output normalization, timeout, idempotency, and reconciliation. Depends on: MAS-1 plus the frozen OPE-251/CCR-003 product contract. Outbound dependencies: action proposal/execution contract with MAS-8 and result contract with MAS-6.
- **MAS-8 Policy, Confirmation & Approval** — deny-by-default action policy, customer confirmation, human approval, expiry, decision audit metadata. Depends on: MAS-1 and MAS-7 tool schemas. Outbound dependencies: decision contract to MAS-6/MAS-7 and approval task contract to MAS-9.
- **MAS-9 Human Support & Escalation** — escalation creation, queues, assignment, SLA, handoff package, takeover, notes, approval task handling, resolution/reopen. Depends on: MAS-5, MAS-6, MAS-8. Outbound dependencies: conversation ownership/state back to MAS-5 and outcomes to MAS-11.
- **MAS-10 Client Configuration Console** — onboarding, knowledge/provider/agent/tool/policy/team management surfaces. Depends on: MAS-1 through MAS-8 contracts. It may build against contract mocks before all backends are complete.
- **MAS-11 Analytics & Audit** — durable audit events, usage/outcome events, business analytics aggregates, tenant audit/analytics views. Depends on: event contracts from MAS-1 through MAS-10. Analytics writes must not block customer responses.
- **MAS-12 Platform Operations** — separate platform-operator trust boundary, tenant lookup, health, provider/queue/job visibility, feature/rate controls, incident support. Depends on: MAS-1 identity separation and MAS-11 operational events.
- **MAS-13 Production Quality Foundation** — CI, local orchestration, testkit, contract checks, security scanning, observability, load-test harness, migration and contract-change discipline. Depends on: none for foundation, then evolves with every MAS. No MAS may bypass its quality gates.

## 14. Success Metrics

1. **Reference-flow reliability:** 10/10 required public-demo scenarios pass the tagged end-to-end suite before a release is marked portfolio-ready.
2. **Tenant isolation:** 0 successful cross-tenant access attempts across the automated isolation suite.
3. **Sensitive-action governance:** 100% of protected mutation executions reference a policy decision, idempotency record, and audit event.
4. **Performance:** non-LLM API p95 <300 ms and error rate <0.5% under the documented baseline load profile. AI/provider latency is reported separately.
5. **Operability:** 100% of agent runs and protected tool executions have a correlation/trace identifier that can be followed through the supported observability stack.

## 15. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Scope becomes too large to finish | High | Keep V1 to the numbered scope above, use MAS boundaries, and move additions to V2+ unless they block an end-to-end V1 flow. |
| Public documentation terms or copyright limit the demo corpus | High | Store source manifests and provenance, avoid wholesale republishing, respect access controls and crawl limits, and disable or replace any selected source whose terms/access do not permit the planned ingestion. DoorDash remains the reference support domain, but that does not authorize unrestricted crawling. |
| Prompt injection from public/retrieved content | High | Treat retrieved content as data, isolate instructions, validate model outputs, restrict tool URLs/scopes, and require policy authorization before execution. |
| Cross-tenant data leakage | Critical | Tenant IDs in every relevant contract, query-scoped access, database defense in depth, isolation tests, audit, and premium review of auth/permission code. |
| Duplicate/ambiguous external mutations | Critical | Idempotency keys, reconciliation state, bounded retry policy, and no blind retry of non-idempotent actions. |
| Provider outages/quotas make the agent unavailable | High | Provider-neutral gateway, timeouts, circuit breakers, fallbacks, deterministic paths, and human escalation. |
| Local stack becomes too resource-heavy | Medium | Docker Compose profiles, deterministic/mock provider mode, start only required services, and defer distributed components until the MAS that needs them. |
| Premature scale claims damage credibility | High | Publish architecture targets separately from measured benchmark results and keep load-test configuration reproducible. |

## 16. Open Questions and Resolved Product Decisions

### Resolved by OPE-251 / CCR-003

- **Primary public support reference domain:** DoorDash customer-support/delivery domain. This is a reference domain, not a private integration.
- **Separate payment-provider reference domain:** Stripe payment/refund domain. The demo does **not** assert that DoorDash uses Stripe.
- **Public source-manifest policy:** `doordash-stripe-allowlist-v1`. Only explicitly approved/permitted sources may be ingested. Serviq does not use unrestricted crawling or bypass authentication, anti-bot controls, access restrictions, terms, or copyright constraints.
- **Synthetic private domain:** customers, orders, order items, deliveries, order events, payments, refund rules, refunds, and support cases are all Serviq-generated synthetic records.
- **Frozen tool keys:** `demo.get_delivery_order_status`, `demo.check_order_resolution_eligibility`, and `demo.create_refund`.
- **Protected mutation rule:** the Production V1 deterministic/reference mutation creates only a synthetic Serviq refund record. It does not move real money or modify DoorDash/Stripe production systems.
- **Public disclaimer:** Serviq is independent and not affiliated with, endorsed by, sponsored by, or connected with DoorDash, Inc. or Stripe, Inc.; referenced public documentation is used only to demonstrate Serviq support/payment workflow capabilities, subject to permitted access.

### Still open

- `Needs Product Decision: Should end-customer file/image attachments be enabled in Production V1, or should V1 accept knowledge-file uploads only from authenticated business users?`
