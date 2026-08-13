# Serviq Product Specification

**Status:** Product charter v1.2  
**Product:** Serviq  
**Category:** Multi-tenant AI customer operations platform  
**Development posture:** Local-first and zero-dollar-friendly, with an explicit cloud scale path  
**Primary product promise:** Connect approved company knowledge, customer context, controlled business tools, AI reasoning, and human support in one governed platform.

## 1. Document Purpose and Authority

This document defines the long-term Serviq product and the boundaries that should remain true as the implementation evolves.

The document hierarchy is:

1. `PRD.md` defines the exact Production V1 product scope and open product decisions.
2. `ARCHITECTURE.md` defines implementation architecture, database/API/event contracts, failure behavior, security boundaries, and build sequencing.
3. `TECH_STACK.md` freezes technology and dependency choices.
4. This Product Specification defines the durable product model, surfaces, workflows, quality principles, and future direction.

When documents conflict, builders stop and report `Needs Architect Decision` rather than choosing one.

## 2. Product Definition

Serviq is an AI customer operations platform that sits between a business and its customers. It is designed to do more than generate answers. Serviq combines:

- approved company knowledge;
- verified customer/account context;
- typed business tools and integrations;
- policy and approval controls;
- bounded AI reasoning;
- human support workflows;
- analytics, evaluation, observability, and audit history.

A customer should be able to ask a question, request account-specific information, or request an allowed business action. Serviq determines which evidence and tools are required, verifies the request against business policy, completes the action when authorized, and hands the case to a human when confidence, permissions, risk, or system health require it.

The business should be able to configure this behavior without editing Serviq source code.

## 3. Product Positioning

Serviq is not positioned as:

- a generic chatbot UI;
- a thin wrapper around one LLM provider;
- a RAG demo that only answers FAQs;
- a model with direct database access;
- an autonomous agent allowed to take unrestricted business actions;
- a single-company hard-coded application.

Serviq is positioned as the **AI operations layer between customers and businesses**.

The reusable product value is the governed platform. A client engagement should primarily configure and integrate Serviq for the client's data, systems, policies, channels, and brand rather than rebuilding the platform from scratch.

## 4. Core Product Surfaces

Serviq has three primary product surfaces and one support channel surface.

### 4.1 Customer Experience

Used by the business's end customer.

Core responsibilities:

- start/resume support conversations;
- receive streamed answers;
- view source citations when the tenant enables them;
- complete customer confirmations;
- see pending approval or escalation status;
- transition to a human support agent without repeating context;
- provide feedback;
- view relevant conversation history allowed by the channel policy.

The initial reference channel is web support. Additional channels are future adapters and must reuse the same conversation, policy, tool, and escalation contracts.

### 4.2 Client Operations Console

Used by the company deploying Serviq.

Core areas:

```text
Onboarding
Overview
Conversations
Support Inbox
Customers
Knowledge
AI Agents
Models & Providers
Tools & Integrations
Policies & Approvals
Analytics
Audit Logs
Team & Access
Developer / Webhooks
Settings
```

The console is not an administrative afterthought. It is the control plane that lets a company operate Serviq safely without code changes.

### 4.3 Human Support Workspace

The human support workspace lives inside the client console but is treated as its own workflow because its latency, information density, permissions, and reliability needs differ from configuration screens.

A human agent receives:

- customer identity/context permitted by role;
- full customer-visible conversation history;
- AI-generated handoff summary;
- retrieved evidence and provenance;
- prior tool execution history;
- policy decisions;
- failed attempts and system errors;
- pending approvals;
- escalation reason and priority;
- recommended next action.

The workspace supports assignment, reassign, takeover, internal notes, allowed tools, approvals, response composition, resolution, and reopen behavior.

### 4.4 Serviq Platform Console

Used only by Serviq platform operators.

Core areas:

```text
Tenants
System Health
Provider Health
Queues / Jobs
Dead Letters
Incidents
Feature Flags
Rate / Abuse Controls
Platform Usage
Security / Audit Events
Deployments
```

Tenant roles can never grant platform-operator permissions.

## 5. User and Client Workflow Model

Serviq intentionally separates the **client workflow** from the **end-customer workflow**.

### 5.1 Client Workflow

A business should be able to:

1. create or receive a Serviq organization;
2. invite workforce users and assign roles;
3. connect one or more supported LLM providers using BYOK;
4. register approved knowledge sources;
5. configure business tools/integrations;
6. configure action policies, confirmations, and approval rules;
7. create a draft agent configuration;
8. test draft behavior against sandbox/evaluation cases;
9. publish a version;
10. deploy the customer support channel;
11. operate escalations and approvals;
12. monitor quality, usage, latency, failures, and audit history;
13. roll back configuration when a new version performs poorly.

### 5.2 End-Customer Workflow

An end customer should be able to:

1. open support;
2. send a question or request;
3. receive a grounded response or status;
4. complete identity verification when protected data/action requires it;
5. confirm a sensitive action when required;
6. wait for or receive human approval when required;
7. see the result of an allowed action;
8. request a human at any time allowed by policy;
9. continue seamlessly when a human joins;
10. provide feedback.

### 5.3 Example Request Classes

Serviq classifies operational requests into product-level categories:

- **Deterministic:** known structured lookup or configured response.
- **Knowledge:** answer grounded in approved knowledge.
- **Transactional:** typed tool action against customer/business state.
- **Reasoning:** requires multiple evidence sources, state, and policies.
- **Escalation-first:** policy or risk prevents autonomous resolution.

The architecture may optimize these differently, but the customer sees one coherent support experience.

## 6. Roles

### 6.1 Tenant Roles

- Tenant Owner.
- Tenant Administrator.
- Support Manager.
- Support Agent.
- Knowledge Manager.
- AI Configuration Manager.
- Analyst/Auditor.

A user may belong to multiple tenants and may hold more than one role/capability where the tenant permission model allows it.

The detailed Production V1 action matrix is authoritative in `PRD.md`.

### 6.2 End Customer

End customers are not workforce roles. Their permissions are derived from:

- tenant/channel policy;
- customer identity assurance;
- ownership of the requested data;
- tool/action policy;
- confirmation/approval state.

### 6.3 Serviq Platform Operator

Platform operators use a separate trust boundary. Platform access is auditable and should be limited to the minimum tenant/customer detail required for an incident or support operation.

## 7. Knowledge Product Model

A tenant can connect approved knowledge without committing the source corpus into the Serviq repository.

Knowledge lifecycle:

```text
Source registered
-> fetch/upload accepted
-> parse/normalize
-> document version created
-> chunk/index
-> retrieval validation
-> ready
-> re-sync/version
-> deprecate/disable
```

Product requirements:

- preserve source provenance;
- show sync/index state;
- show failures and retry actions;
- support customer-visible vs internal access scope;
- keep versions so configuration/evaluation can identify which knowledge was used;
- never silently serve disabled or deprecated content;
- make retrieval quality inspectable by authorized users;
- treat all fetched/retrieved content as untrusted data for prompt-injection purposes.

## 8. AI Provider and Agent Product Model

### 8.1 BYOK

Serviq supports provider connections supplied by the tenant. Production V1 targets:

- OpenAI;
- Anthropic;
- Gemini;
- OpenRouter.

A stored key is server-side only, masked after creation, testable, auditable by lifecycle event, and replaceable without changing business code.

### 8.2 Provider Independence

Business workflows depend on model aliases and Serviq gateway contracts, not direct provider SDK types. A tenant may configure primary and fallback models subject to budget and safety policy.

### 8.3 Agent Versioning

Agent behavior is versioned configuration. A published version is immutable and records, directly or by reference:

- response/system behavior;
- model aliases/routing policy;
- run budgets;
- retrieval policy;
- allowed tools;
- policy references;
- citation behavior;
- escalation rules;
- evaluation gate settings.

Every conversation/agent run can be traced back to the version it used.

## 9. Tools, Policies, and Business Actions

### 9.1 Typed Tool Model

Tools are explicit named capabilities with versioned input/output schemas. The Production V1 reference configuration uses a DoorDash reference support/delivery domain together with a separate Stripe reference payment domain. This is an architectural demo composition only and does not assert that DoorDash uses Stripe internally.

The first frozen demo tool keys are:

```text
demo.get_delivery_order_status
demo.check_order_resolution_eligibility
demo.create_refund
```

`demo.get_delivery_order_status` is a read-only lookup over synthetic order/delivery state. `demo.check_order_resolution_eligibility` is a read-only eligibility/policy calculation over synthetic order/item/delivery/payment state plus Serviq rules. `demo.create_refund` is a protected idempotent mutation that changes only Serviq synthetic refund state in the deterministic V1 demo; it does not move real money or call DoorDash/Stripe production systems.

The model may propose a tool and arguments. It cannot directly mutate business data.

### 9.2 Policy Before Action

Every protected mutation follows:

```text
Tool proposal
-> schema validation
-> identity/ownership context
-> policy decision
-> optional customer confirmation
-> optional human approval
-> idempotent execution
-> result verification/reconciliation
-> audit
-> customer response
```

Policy outcomes are:

- allow;
- deny;
- require customer confirmation;
- require human approval.

Missing policy for a mutation is deny-by-default.

### 9.3 Human Control

A tenant can mark tools or risk classes as human-only. High-risk or ambiguous outcomes must not be retried blindly or hidden from support staff.

## 10. Human Escalation Product Model

Escalation is a first-class successful product path, not an AI failure afterthought.

Serviq may escalate because:

- the customer requests a human;
- protected identity cannot be established;
- evidence is insufficient or conflicting;
- tenant policy requires a human;
- a tool fails repeatedly within its bounded policy;
- a tool outcome is ambiguous and requires reconciliation;
- agent run budget is exhausted;
- a system/provider dependency cannot support a safe response.

The handoff package is persisted and visible to the support workspace. The customer should not need to repeat information already present in the conversation and verified context.

## 11. Analytics, Evaluation, and Audit

### 11.1 Operational Analytics

Serviq should measure, with clear definitions:

- conversation volume;
- AI containment/resolution;
- escalation;
- first response and total resolution latency;
- provider health/latency/error;
- tool outcomes;
- retrieval outcomes;
- cache effectiveness;
- customer feedback/CSAT;
- estimated model usage/cost;
- unresolved/reopened cases;
- ingestion failures/backlog.

Measured infrastructure capacity must be separated from LLM-provider latency and quotas.

### 11.2 AI Evaluation

Serviq uses versioned evaluation cases for grounding, citations, unsupported-answer behavior, tool selection, arguments, policy compliance, prompt-injection behavior, escalation, and model/config regressions.

A tenant should be able to test draft configuration before publishing.

### 11.3 Audit

Security-sensitive and customer-impacting actions produce queryable audit records. Audit covers at minimum:

- role/access changes;
- provider/integration secret lifecycle metadata;
- agent publish/rollback;
- policy changes;
- protected tool actions;
- confirmation/approval decisions;
- escalation assignment/resolution;
- platform-operator tenant access.

Audit records never contain raw secrets.

## 12. Multi-Tenancy and Isolation

Multi-tenancy is part of the product contract, not only a database detail.

Tenant context applies to:

- relational data;
- retrieval/search;
- cache keys;
- object storage;
- events/jobs;
- model/provider configuration;
- tool execution;
- analytics/audit;
- authorization;
- observability where tenant dimensions are safe.

Default product mode is logical multi-tenancy with strong application and database controls.

Future enterprise isolation may include:

- dedicated database/schema;
- dedicated encryption key;
- dedicated region;
- dedicated worker pools;
- dedicated deployment.

Those stronger isolation modes should not require rewriting business workflows.

## 13. Security and Trust Principles

1. **Server authorization is mandatory.** UI hiding is not access control.
2. **Least privilege.** Users, services, tools, and platform operators receive only required capabilities.
3. **Secrets stay server-side.** Provider keys and integration credentials never enter client bundles or logs.
4. **Untrusted input stays untrusted.** User text, public web content, retrieved chunks, files, tool output, and model output all require validation/containment.
5. **No arbitrary model execution.** LLM output never becomes shell, SQL, `eval`, unrestricted URL fetch, or unreviewed code execution.
6. **Policy before mutation.** Model reasoning is not authorization.
7. **Idempotency for retried side effects.** Duplicate messages/events cannot silently duplicate business actions.
8. **Fail closed for identity and permission errors.** Dependency failure never grants extra access.
9. **Sensitive actions are traceable.** Correlation, policy, tool, outcome, and actor context must be auditable.
10. **Public ingestion is bounded.** Crawlers must defend against SSRF, unsafe redirects, excessive responses, and access-control bypass.

## 14. Reliability and Failure Behavior

The product must expose understandable degraded states instead of looping or fabricating certainty.

- Provider failure may use a configured fallback within budget.
- Retrieval failure must not cause unsupported answers when grounding is required.
- Tool mutation failure must reconcile ambiguous state before retry.
- Queue/worker overload must apply backpressure and prioritize critical customer/action flows over analytics.
- Cache failure falls back to authoritative data with rate protection.
- Repeated or unsafe failures escalate to a human.

External dependency errors are translated into stable Serviq states and safe customer-facing messages.

## 15. Scale Model

Serviq distinguishes these capacity dimensions:

- registered users;
- monthly active users;
- concurrently connected clients;
- active conversations;
- API requests per second;
- agent runs per second;
- model calls per second;
- tool calls per second;
- event throughput;
- retrieval throughput.

The long-term architecture target includes a path toward **10 million concurrent customer connections**, but this is not a current verified capacity claim.

**10 million requests per second is a separate hyperscale research target.** It would require extensive edge caching, partitioned data systems, large infrastructure spend, and a workload where only a small fraction of requests invoke expensive AI inference.

Published scale claims must include:

- workload/scenario;
- infrastructure configuration;
- dataset size;
- connection count/RPS;
- p50/p95/p99 latency;
- error rate;
- test duration;
- version/commit;
- whether provider calls were mocked or real.

## 16. Local-First and Zero-Dollar Development

A contributor should be able to develop the core platform locally with free/open-source infrastructure.

Required properties:

- Docker Compose profiles;
- PostgreSQL/pgvector;
- Valkey-compatible cache;
- local object storage;
- local OIDC provider;
- deterministic/fake LLM mode;
- optional local broker profile;
- optional local observability profile;
- no paid API required for CI or deterministic core flows.

Real provider behavior uses the contributor's BYOK credential. AWS deployment is an evolution path, not a prerequisite for building Serviq.

## 17. Public Demo Strategy

The Production V1 portfolio reference is now frozen by OPE-251 / CCR-003 as a **combined, explicitly separated reference configuration**:

- **Primary customer-operations reference domain:** DoorDash public support/delivery concepts, where a source is explicitly permitted for the intended use.
- **Separate payment-provider reference domain:** Stripe public payment/refund concepts.
- **Synthetic private operational domain:** Serviq-generated customers, orders, order items, deliveries, order events, payments, refund rules, refunds, and support cases.
- **Public source policy:** `doordash-stripe-allowlist-v1`.
- **Frozen demo tools:** `demo.get_delivery_order_status`, `demo.check_order_resolution_eligibility`, `demo.create_refund`.

The composition demonstrates that Serviq can coordinate customer-support knowledge, private operational state, payments, policy, tools, and human support across more than one system boundary. It does **not** assert that DoorDash uses Stripe, and the deterministic V1 demo does not access DoorDash private systems or execute real Stripe transactions.

The demo approach is:

```text
Approved/permitted public support + payment documentation
+ source manifest/provenance
+ synthetic customers/orders/deliveries/payments/refunds/support cases
+ Serviq customer workflow
+ Serviq policy/tool workflow
+ Serviq client/support workflow
```

Repository and ingestion rules:

- do not commit a wholesale copy of a third-party help center or documentation corpus;
- preserve source provenance;
- use an explicit allowlist instead of unrestricted domain crawling;
- respect access controls, crawl limits, robots/anti-bot controls where applicable, terms, and copyright constraints;
- do not bypass authentication or access restrictions;
- if automated ingestion is not permitted for a selected source, disable that source and use only material that can be used through an allowed/manual/permitted path;
- do not scrape authenticated/private content;
- use synthetic customer, order, payment, refund, delivery, and support-case data;
- include a clear non-affiliation disclaimer anywhere DoorDash or Stripe is named publicly.

**Frozen public disclaimer:** Serviq is an independent portfolio project and is not affiliated with, endorsed by, sponsored by, or connected with DoorDash, Inc. or Stripe, Inc. DoorDash and Stripe names and publicly available documentation are referenced only to demonstrate Serviq customer-support and payment-workflow capabilities, subject to permitted access. All customers, orders, deliveries, payments, refunds, support cases, and operational records shown by Serviq are synthetic. The reference demo does not access DoorDash private systems and does not execute real DoorDash or Stripe transactions.

## 18. Product Quality Bar

Serviq features are built iteratively, but quality is not deferred to a later hardening phase.

A production feature is incomplete when an applicable item is missing:

- exact acceptance criteria;
- success/loading/empty/error/permission UX;
- server validation;
- authentication/authorization behavior;
- tenant isolation;
- API/schema/event contract;
- idempotency for retried side effects;
- failure/degraded behavior;
- audit behavior for sensitive actions;
- logs/metrics/traces;
- automated tests;
- migration/rollback plan for schema changes;
- security review requirements;
- performance impact;
- documentation.

The repository's premium-product-builder quality bar and domain rules are the implementation gate.

## 19. Release Model

Serviq is not treated as a throwaway MVP. Production V1 is the smallest end-to-end release that preserves the complete architecture and safety model.

Production V1 intentionally limits channels, integrations, and infrastructure complexity while still requiring:

- tenant/workforce access;
- BYOK provider gateway;
- approved knowledge ingestion and retrieval;
- customer support conversation;
- bounded agent runtime;
- typed tools with protected mutation;
- policy, confirmation, and human approval;
- human escalation/takeover;
- client operations console;
- analytics and audit;
- platform operations foundation;
- CI, tests, security, observability, and load-test evidence.

V2+ adds channels, integrations, multilingual capability, hosted SaaS/billing, advanced enterprise isolation, and multi-region scale without weakening the V1 contracts.

## 20. Product Principles

1. **Evidence before generation.** Prefer verified business state and approved knowledge over model memory.
2. **Policy before action.** The model proposes. Serviq authorizes and executes.
3. **Human control for uncertainty.** Escalation is a supported outcome.
4. **Tenant isolation everywhere.** Tenant context is a first-class boundary.
5. **Provider independence.** Business workflows do not depend on one model vendor.
6. **Observable by default.** Important flows can be traced from ingress to outcome.
7. **Explicit contracts over hidden coupling.** APIs, events, schemas, and shared types are architect-owned.
8. **Scale through measured bottlenecks.** Preserve horizontal seams, but add distributed complexity only when evidence requires it.
9. **No unverified scale claims.** Benchmarks and assumptions accompany every capacity statement.
10. **Production quality from the first feature.** Iteration controls scope, not engineering rigor.
