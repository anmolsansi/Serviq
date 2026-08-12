# Serviq Production Architecture

**Status:** Architecture baseline v1.0  
**Scope:** Production-grade multi-tenant AI customer operations platform  
**Development mode:** Local-first, zero-dollar friendly  
**Production target:** Horizontally scalable, cloud-ready, AWS-compatible  

## 1. Architecture Objectives

Serviq must support four distinct surfaces over one governed platform:

1. customer-facing support experience;
2. business/client operations console;
3. human-support workspace;
4. Serviq platform-operator console.

The architecture must support multi-tenancy, BYOK model providers, knowledge retrieval, deterministic workflows, AI reasoning, tool execution, approvals, human escalation, observability, security, and progressive scale-out.

The system is designed toward millions of concurrent users. A target such as 10 million concurrent sessions is an architectural capacity goal, not a verified claim until load tests demonstrate it. Ten million requests per second is treated as a separate hyperscale research target and must never be conflated with concurrent connected users.

## 2. Architectural Principles

- Stateless request-serving tiers wherever possible.
- Tenant context carried explicitly through every request, event, cache key, storage object, trace, and authorization check.
- Synchronous paths kept short. Heavy work moves to queues/workers.
- At-least-once event delivery with idempotent consumers.
- Transactional outbox for reliable domain-event publication.
- Model calls isolated behind a provider gateway.
- Business mutations isolated behind policy-enforced tools.
- No LLM receives unrestricted database or infrastructure access.
- Data-plane failures degrade to deterministic responses, retries, or human escalation instead of uncontrolled loops.
- All sensitive actions are auditable and replay-safe.
- Production behavior is measurable through traces, metrics, logs, and evaluation results.

## 3. High-Level System Context

```text
                         Customers
                            |
              Web / Mobile / Embedded Widget
                            |
                    CDN / WAF / Edge
                            |
                     API Gateway
                            |
                Auth + Tenant Resolution
                            |
                 Conversation API Layer
                            |
            +---------------+---------------+
            |               |               |
     Deterministic      Agent Runtime    Human Support
       Handlers             |               |
            |          +----+----+          |
            |          |         |          |
            |      Retrieval   Tools        |
            |          |         |          |
            |      Knowledge  Policy        |
            |          |         |          |
            +----------+----+----+----------+
                           |
                      LLM Gateway
                           |
            +--------------+--------------+
            |              |              |
         OpenAI         Anthropic       Gemini /
                                          OpenRouter

 Business users --> Client Console --> Management APIs
 Support staff --> Agent Console --> Human Support APIs
 Serviq ops    --> Platform Console --> Platform Admin APIs
```

## 4. Logical Services

The initial codebase should preserve service boundaries even if some components are deployed together locally. This avoids premature microservice complexity while keeping extraction paths clear.

### 4.1 Edge / API Gateway

Responsibilities:

- TLS termination in production;
- request routing;
- request IDs/correlation IDs;
- global and tenant-aware rate limiting;
- request size limits;
- abuse controls;
- authentication handoff;
- WebSocket/SSE routing;
- API version routing.

### 4.2 Identity and Access Service

Responsibilities:

- workforce authentication for tenant users;
- Serviq operator authentication;
- customer identity federation/verification hooks;
- service-to-service identities;
- JWT/OIDC validation;
- organization membership;
- role/capability resolution;
- session management.

Internal workforce identity and end-customer identity are separate trust domains.

### 4.3 Tenant Service

Responsibilities:

- organization lifecycle;
- tenant configuration;
- feature flags;
- environment settings;
- tenant quotas;
- tenant-level encryption/config metadata;
- region/data-residency metadata when introduced.

### 4.4 Conversation Service

Responsibilities:

- conversations and messages;
- channel/session state;
- message ordering;
- streaming response coordination;
- attachments metadata;
- conversation status;
- ownership/assignment state;
- persistence of customer-visible and internal messages.

The Conversation Service does not directly execute business tools or model providers.

### 4.5 Agent Orchestrator

Responsibilities:

- intent/routing decisions;
- agent state machine;
- context assembly;
- deterministic path selection;
- retrieval requests;
- tool proposals;
- model invocation through LLM Gateway;
- run budgets;
- step limits;
- confidence/evaluation gates;
- escalation decisions;
- final response assembly.

Agent execution must be modeled as explicit state transitions rather than an unconstrained infinite loop.

### 4.6 Retrieval Service

Responsibilities:

- tenant-scoped lexical search;
- vector similarity search;
- hybrid ranking;
- metadata filtering;
- access-scope filtering;
- reranking;
- source/citation assembly;
- retrieval diagnostics.

### 4.7 Knowledge Ingestion Service

Responsibilities:

- source registration;
- crawling/fetching allowed sources;
- file parsing;
- normalization;
- chunking;
- metadata extraction;
- embedding generation;
- indexing;
- versioning;
- synchronization;
- deprecation;
- ingestion failure recovery.

Ingestion is asynchronous and event-driven.

### 4.8 Tool Execution Service

Responsibilities:

- tool registry;
- input schema validation;
- tenant integration lookup;
- execution timeout;
- idempotency;
- retries when safe;
- output normalization;
- sensitive-data filtering;
- audit event generation.

Tools are typed, allow-listed capabilities. Arbitrary model-generated code execution is prohibited in the standard runtime.

### 4.9 Policy and Approval Service

Responsibilities:

- role/capability checks;
- customer authorization checks;
- action risk classification;
- amount/value thresholds;
- customer confirmation requirements;
- human approval requirements;
- deny rules;
- policy versioning;
- policy-decision audit records.

### 4.10 Human Support Service

Responsibilities:

- escalation creation;
- queues;
- assignment;
- SLA tracking;
- internal notes;
- human messages;
- approval tasks;
- resolution state;
- handoff package generation;
- reopen logic.

### 4.11 LLM Gateway

Responsibilities:

- provider abstraction;
- BYOK credential resolution;
- model aliases;
- routing;
- fallback providers;
- timeout budgets;
- retry policy;
- rate-limit awareness;
- usage accounting;
- prompt/model metadata;
- provider-health tracking;
- response normalization;
- streaming proxying;
- optional semantic/prompt caching.

Initial provider support target:

- OpenAI;
- Anthropic;
- Gemini;
- OpenRouter.

The application must depend on an internal provider-neutral contract, not provider SDK types.

### 4.12 Analytics and Usage Service

Responsibilities:

- usage events;
- tenant metrics;
- conversation outcomes;
- model token/cost estimates;
- latency metrics;
- tool metrics;
- resolution/escalation analytics;
- evaluation outcomes;
- reporting aggregates.

Analytics writes are asynchronous and must not block customer responses.

### 4.13 Audit Service

Responsibilities:

- immutable append-oriented audit events;
- actor/action/resource metadata;
- policy decisions;
- tool mutations;
- configuration changes;
- provider-key lifecycle metadata without secret values;
- export/query support.

### 4.14 Notification Service

Responsibilities:

- human escalation alerts;
- approval requests;
- operational notifications;
- future email/SMS/chat connectors.

### 4.15 Platform Operations Service

Responsibilities:

- tenant support tooling;
- feature flags;
- global provider status;
- queue and job health;
- incident controls;
- abuse/rate-limit overrides;
- global operational dashboards.

## 5. API Architecture

### 5.1 External API Style

- Versioned REST APIs under `/api/v1`.
- OpenAPI-generated contracts.
- Server-Sent Events or WebSockets for response streaming where needed.
- Webhooks for outbound integration events.
- Idempotency keys required for externally retried mutations.
- Cursor pagination for unbounded collections.
- Consistent structured error envelope.

### 5.2 Representative Customer APIs

```text
POST   /api/v1/customer/conversations
GET    /api/v1/customer/conversations/{conversation_id}
POST   /api/v1/customer/conversations/{conversation_id}/messages
GET    /api/v1/customer/conversations/{conversation_id}/stream
POST   /api/v1/customer/actions/{action_id}/confirm
POST   /api/v1/customer/conversations/{conversation_id}/request-human
POST   /api/v1/customer/conversations/{conversation_id}/feedback
```

### 5.3 Representative Client APIs

```text
GET    /api/v1/organizations/{org_id}
PATCH  /api/v1/organizations/{org_id}
GET    /api/v1/conversations
GET    /api/v1/conversations/{id}
GET    /api/v1/escalations
POST   /api/v1/escalations/{id}/assign
POST   /api/v1/escalations/{id}/resolve
POST   /api/v1/approvals/{id}/approve
POST   /api/v1/approvals/{id}/reject

GET    /api/v1/knowledge/sources
POST   /api/v1/knowledge/sources
POST   /api/v1/knowledge/sources/{id}/sync
GET    /api/v1/knowledge/documents
GET    /api/v1/knowledge/search/debug

GET    /api/v1/agents
POST   /api/v1/agents
POST   /api/v1/agents/{id}/versions
POST   /api/v1/agents/{id}/publish
POST   /api/v1/agents/{id}/evaluate

GET    /api/v1/providers
POST   /api/v1/providers
PATCH  /api/v1/providers/{id}
DELETE /api/v1/providers/{id}

GET    /api/v1/integrations
POST   /api/v1/integrations
GET    /api/v1/tools
POST   /api/v1/tools/{id}/test

GET    /api/v1/analytics/overview
GET    /api/v1/audit-events
GET    /api/v1/team/members
POST   /api/v1/team/invitations
```

### 5.4 Internal Service Contracts

Internal contracts may use HTTP/gRPC depending on deployment phase, but domain contracts must be transport-neutral in code. Events are preferred for non-blocking fan-out.

## 6. Event Architecture

### 6.1 Delivery Semantics

- At-least-once delivery.
- Idempotent event consumers.
- Event IDs are globally unique.
- Tenant ID is mandatory in tenant-scoped events.
- Schema version is mandatory.
- Correlation and causation IDs are preserved.
- Transactional outbox publishes domain events from transactional services.
- Failed events move to retry queues, then dead-letter queues.

### 6.2 Core Events

```text
conversation.created
conversation.message.received
conversation.message.persisted
agent.run.requested
agent.run.started
agent.run.completed
agent.run.failed
retrieval.requested
retrieval.completed
retrieval.failed
tool.execution.requested
tool.execution.completed
tool.execution.failed
policy.decision.recorded
approval.requested
approval.approved
approval.rejected
escalation.created
escalation.assigned
escalation.resolved
knowledge.source.sync.requested
knowledge.document.parsed
knowledge.document.indexed
knowledge.sync.failed
provider.request.completed
provider.request.failed
usage.recorded
audit.event.recorded
feedback.received
```

### 6.3 Event Envelope

```json
{
  "event_id": "evt_...",
  "event_type": "tool.execution.completed",
  "schema_version": 1,
  "tenant_id": "ten_...",
  "occurred_at": "ISO-8601",
  "correlation_id": "corr_...",
  "causation_id": "evt_...",
  "actor": {
    "type": "customer|tenant_user|service|platform_operator",
    "id": "..."
  },
  "payload": {}
}
```

## 7. Agent Architecture

### 7.1 Agent State Machine

```text
RECEIVE
  -> AUTH_CONTEXT
  -> REQUEST_CLASSIFICATION
  -> FAST_PATH_CHECK
  -> CONTEXT_PLANNING
  -> RETRIEVAL / TOOL_REQUEST / MODEL_REASONING
  -> POLICY_CHECK
  -> ACTION_CONFIRMATION_OR_APPROVAL (when required)
  -> TOOL_EXECUTION (when required)
  -> RESULT_VERIFICATION
  -> RESPONSE_GENERATION
  -> OUTPUT_GUARDRAIL
  -> RESPOND
  -> COMPLETE

Any state may transition to ESCALATE or FAIL_SAFE.
```

### 7.2 Request Classes

1. **Deterministic:** known operation with structured data and templated response.
2. **Knowledge:** retrieval-backed answer from approved sources.
3. **Transactional:** tool-backed customer/business action.
4. **Reasoning:** multiple evidence sources, policies, and context required.
5. **Escalation-first:** tenant policy forbids autonomous resolution.

### 7.3 Agent Budgets

Each run has configurable limits:

- maximum steps;
- maximum model calls;
- maximum tool calls;
- maximum wall-clock duration;
- maximum input/output tokens;
- estimated-cost budget;
- retrieval limits;
- retry limits.

Budget exhaustion transitions to deterministic fallback or human escalation.

### 7.4 Model Routing

Routing policy may consider:

- request class;
- tenant configuration;
- model capabilities;
- cost budget;
- provider health;
- latency target;
- context size;
- safety/risk classification.

The router must support primary and fallback paths without changing higher-level agent code.

### 7.5 Confidence and Verification

Serviq must not use one raw model confidence number as a sole decision mechanism. Decision quality may combine:

- retrieval evidence strength;
- source agreement;
- deterministic validation;
- tool result status;
- policy certainty;
- structured evaluator checks;
- model self-check only as a secondary signal;
- historical evaluation thresholds.

## 8. Data Architecture

### 8.1 Core Relational Entities

```text
tenants
users
memberships
roles
role_permissions
service_accounts
tenant_settings
feature_flags
provider_connections
model_configurations
agents
agent_versions
agent_deployments
policies
policy_versions
integrations
tools
tool_versions
customers
customer_identities
customer_external_refs
conversations
conversation_participants
messages
message_attachments
agent_runs
agent_steps
retrieval_runs
retrieval_results
tool_executions
action_confirmations
approvals
escalations
support_queues
support_assignments
internal_notes
knowledge_sources
knowledge_documents
knowledge_document_versions
knowledge_chunks
knowledge_sync_runs
feedback
usage_events
cost_events
audit_events
webhook_endpoints
webhook_deliveries
idempotency_keys
outbox_events
```

### 8.2 Data Stores

**PostgreSQL**

- source of truth for tenant/configuration/conversation/workflow metadata;
- relational consistency;
- row-level tenant protections;
- transactional outbox;
- initial full-text/vector capabilities where appropriate.

**Vector search**

- initial implementation may use PostgreSQL + pgvector;
- service contract allows migration to a dedicated vector engine at higher scale.

**Redis-compatible cache**

- short-lived sessions;
- rate-limit counters;
- distributed locks where unavoidable;
- hot configuration cache;
- response/semantic cache;
- temporary streaming/session state.

**Object storage**

- uploaded documents;
- attachments;
- normalized artifacts;
- large exports;
- ingestion intermediate files.

Local: S3-compatible storage. Production: S3 or equivalent.

**Search index**

- dedicated lexical/hybrid search can be introduced when PostgreSQL search becomes a bottleneck;
- Retrieval Service hides index implementation from the agent.

**Event log / broker**

- Kafka-compatible broker for durable domain events and high-throughput workers at scale;
- local development may run a single-node compatible broker through Docker.

## 9. Multi-Tenancy Model

### 9.1 Isolation Rules

Every tenant-owned record includes `tenant_id` unless physically isolated by design.

Tenant identity is enforced in:

- database queries;
- row-level security where supported;
- object storage prefixes/buckets;
- cache keys;
- vector namespaces/filters;
- search filters;
- event envelopes;
- metrics dimensions with cardinality controls;
- audit records;
- service authorization context.

### 9.2 Isolation Levels

Default: logical multi-tenancy with strong application and database controls.

Future enterprise options:

- dedicated database/schema;
- dedicated encryption keys;
- dedicated region;
- dedicated worker pools;
- dedicated deployment.

The application domain model must not require redesign to enable stronger isolation later.

## 10. Security Model

### 10.1 Authentication

- OIDC-compatible workforce authentication.
- Separate platform-operator realm/trust boundary.
- Customer identity may be delegated to the client application via signed, short-lived identity assertions or configured OIDC integration.
- Service-to-service authentication uses workload/service identities.

### 10.2 Authorization

- capability-based RBAC;
- tenant scoping;
- object-level authorization for queues/conversations/resources;
- policy checks on every tool mutation;
- deny-by-default behavior.

### 10.3 Secrets

- provider keys and integration credentials are server-side only;
- never returned in plaintext after creation;
- encrypted at rest;
- logs/traces redact known secret fields;
- local development uses ignored environment/secret files;
- cloud production uses a managed secret store.

### 10.4 Data Protection

- TLS in transit;
- encryption at rest in production;
- PII classification and minimization;
- configurable retention;
- deletion/export workflows;
- attachment validation and malware scanning before processing;
- content-type and size controls;
- audit logs for sensitive reads and mutations where appropriate.

### 10.5 Application Security

- input/schema validation;
- output encoding;
- CSRF protection for browser sessions where applicable;
- SSRF protection in crawlers/connectors;
- URL allow/deny rules;
- prompt-injection defenses around untrusted retrieved/tool content;
- least-privilege tool scopes;
- dependency and container scanning;
- secret scanning;
- SAST and CodeQL on public repository CI;
- SBOM generation for release artifacts;
- signed/reproducible release path as the project matures.

## 11. Observability

OpenTelemetry is the cross-service instrumentation standard.

### 11.1 Traces

A single correlation trace should connect:

```text
edge request
-> authentication
-> conversation persistence
-> agent run
-> retrieval
-> provider calls
-> policy decision
-> tool execution
-> response streaming
-> analytics/audit publication
```

Sensitive prompt/content capture must be tenant-configurable and redacted by default where appropriate.

### 11.2 Metrics

Core metrics include:

- requests/sec;
- concurrent connections;
- p50/p95/p99 latency;
- error rate;
- queue lag;
- worker saturation;
- DB pool utilization;
- cache hit ratio;
- retrieval latency;
- provider latency/error/rate-limit frequency;
- token usage;
- estimated AI cost;
- agent steps/run;
- tool success/failure;
- escalation rate;
- AI resolution rate;
- customer feedback;
- ingestion backlog;
- dead-letter count.

### 11.3 Logs

- structured JSON logs;
- trace/span IDs;
- request IDs;
- tenant IDs where safe;
- no raw secrets;
- configurable PII redaction;
- stable event/error codes.

### 11.4 SLO Baseline Targets

Initial production targets, to be validated by benchmark:

- non-LLM API availability: 99.95% target;
- non-LLM API p95 latency: < 300 ms under defined reference load;
- streaming first-token latency: measured separately because provider latency dominates;
- zero cross-tenant data leakage tolerance;
- durable action mutation semantics with idempotent retry;
- all sensitive actions produce audit records.

## 12. Failure Handling

### 12.1 General Rules

- explicit timeout budget per dependency;
- bounded retries with exponential backoff and jitter;
- retry only safe/idempotent operations automatically;
- circuit breakers for unstable providers/integrations;
- bulkheads to prevent one tenant/provider from exhausting all workers;
- dead-letter queues for poison events;
- backpressure before overload;
- human escalation rather than unbounded AI retries.

### 12.2 Provider Failure

1. timeout/circuit-break failed provider;
2. use configured fallback if policy allows;
3. fall back to deterministic/knowledge-only response when possible;
4. otherwise create an escalation and return a transparent temporary-failure response.

### 12.3 Retrieval Failure

- retry infrastructure failure within budget;
- do not invent an answer from model memory when grounding is required;
- answer only deterministic portions supported by verified context;
- escalate when the requested answer depends on unavailable evidence.

### 12.4 Tool Failure

- mutation uses idempotency key;
- ambiguous execution state is reconciled before retry;
- never blindly repeat non-idempotent actions;
- surface pending/failed state to the agent;
- escalate if consistency cannot be established.

### 12.5 Queue Failure / Lag

- publish via outbox;
- workers consume idempotently;
- monitor consumer lag;
- degrade asynchronous analytics/notifications before interactive support;
- preserve critical tool/audit workflows under prioritized queues.

### 12.6 Cache Failure

Cache is an optimization, not the sole source of truth. Services fall back to authoritative stores with rate protection.

## 13. Scalability Assumptions

### 13.1 Capacity Definitions

Serviq will report separately:

- registered users;
- monthly active users;
- concurrently connected clients;
- active conversations;
- requests per second;
- agent runs per second;
- provider calls per second;
- tool calls per second;
- event throughput.

No one number is used as a substitute for all scale dimensions.

### 13.2 Target Architecture

The architecture should permit:

- 10M concurrent customer connections as a long-term target through global edge termination and horizontally sharded connection/session handling;
- independent scaling of APIs, agent workers, ingestion workers, retrieval workers, and tool workers;
- tenant-aware partitioning;
- read replicas and later data sharding;
- event partitioning by tenant/conversation key;
- caches that reduce repeated retrieval/model work;
- model/provider quotas isolated by tenant and provider;
- multi-region active-active serving when required.

### 13.3 10M RPS Statement

Ten million requests per second is not an initial acceptance criterion. Reaching that level would require hyperscale edge capacity, extensive caching, partitioned data systems, major infrastructure spend, and a workload where only a small fraction of requests invoke expensive AI inference. It remains a stretch architecture research goal, not a marketing claim.

### 13.4 Scaling Phases

**Phase A: Local / Single-node**

- Docker Compose;
- one API deployment per logical app/service group;
- PostgreSQL;
- Redis-compatible cache;
- local object storage;
- local event broker;
- local observability.

**Phase B: Horizontally Scaled Single Region**

- multiple stateless API replicas;
- separate worker pools;
- managed/clustered database and cache;
- durable broker;
- autoscaling;
- load balancer;
- object storage;
- production observability.

**Phase C: Partitioned Single Region**

- tenant/data partitioning;
- database read/write scaling;
- dedicated search/vector clusters;
- partitioned event streams;
- workload isolation;
- priority queues.

**Phase D: Multi-Region**

- global traffic routing;
- region-aware tenant placement;
- replicated configuration;
- regional data planes;
- disaster recovery;
- regional provider routing;
- cross-region failover policy.

## 14. Performance Strategy

- deterministic paths before generative paths;
- exact cache before semantic cache;
- request coalescing for duplicate in-flight work;
- retrieval result caching with knowledge-version invalidation;
- prompt/context compaction;
- small model routing for classification/simple tasks;
- bounded streaming buffers;
- asynchronous analytics and audit fan-out where durability permits;
- database connection pooling;
- batched embeddings and ingestion;
- backpressure under provider/worker saturation.

## 15. Repository / Deployment Architecture

Recommended initial monorepo shape:

```text
apps/
  web-client/          # client/admin/support frontend
  customer-web/        # standalone customer support frontend
  platform-console/    # Serviq operator frontend
services/
  api/
  agent/
  knowledge/
  worker/
packages/
  contracts/
  ui/
  config/
  observability/
  security/
  testkit/
infra/
  docker/
  kubernetes/
  terraform/
docs/
  adr/
  runbooks/
  architecture/
scripts/
```

The first implementation may deploy multiple Python domain modules within fewer processes. Service boundaries above remain the architectural contract and extraction map.

## 16. Architecture Acceptance Criteria

The architecture baseline is considered implemented when:

- all tenant-facing data access is tenant-scoped and tested;
- model providers are accessed only through the gateway abstraction;
- tool mutations are policy-checked and idempotent;
- every agent run has bounded execution;
- human escalation works end-to-end;
- all core flows emit traces/metrics/logs;
- sensitive configuration changes and actions are audited;
- local environment runs without paid infrastructure;
- CI validates unit/integration/e2e/security contracts;
- baseline load tests are repeatable;
- cloud deployment can scale stateless tiers without application redesign.
