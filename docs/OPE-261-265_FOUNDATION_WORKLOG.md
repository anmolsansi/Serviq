# Serviq OPE-261 to OPE-265 Foundation Worklog

This document explains the current engineering work for OPE-261 through OPE-265 in plain language. It records what was changed, how the change works, why the change exists, what it improves, what has actually been validated, and what still has to happen before each ticket can be called complete.

These tickets are foundation work. They create the service and local-infrastructure boundaries that later Serviq features will use. They do not pretend that AI routing, a production database, application caching, file uploads, or workforce login already work.

## OPE-261 — LLM gateway service scaffold

### What we are building

Serviq needs one service that sits between the rest of the platform and external large-language-model providers. That service is `services/llm-gateway`.

A simple analogy is a travel adapter. An appliance should not be rebuilt for every wall-socket standard. In the same way, the Serviq API, worker, and future agent runtime should not each contain separate knowledge of every AI provider. They should eventually communicate through one Serviq-owned gateway, while provider-specific translation remains behind that boundary.

### What changed

The branch `ope-261-llm-gateway-scaffold` now contains a Python 3.14 project definition, a minimal FastAPI application, and separate package boundaries for schemas, adapters, and routing. The application currently exposes only the service identity `Serviq LLM Gateway`. A smoke test verifies that the application object can be imported and has the expected title.

The commits were deliberately small: project tooling, application package, adapter boundary, routing boundary, schema boundary, FastAPI entry point, and smoke test were added separately. This lets a reviewer understand the construction sequence instead of reviewing one large unexplained change.

### Why we did it this way

The empty packages are intentional. Future provider request/response models belong under the Serviq-owned schema boundary. Provider-specific translations belong under adapters. Model selection and fallback belong under routing. Keeping those responsibilities separated now makes later changes easier to test and reduces the chance that provider SDK details spread through unrelated services.

### What this improves

Later OpenAI, Anthropic, Gemini, OpenRouter, or other provider work gets a known home without tying the whole product to one provider. It also gives us a service that can eventually be scaled, observed, rate-limited, and failed over independently from the main API.

### What is intentionally not implemented

There is no provider adapter, provider SDK, API-key loading, model routing, fallback policy, streaming, usage accounting, cost policy, retry policy, circuit breaker, or actual LLM request. Those are separate contracts and future tickets.

### Validation status

Static TOML parsing and Python syntax checks passed. The current execution environment does not provide the required Python 3.14 runtime/dependency environment, so dependency locking, Ruff, strict mypy, pytest, import validation, and Uvicorn startup validation are still pending. OPE-261 therefore remains In Progress and draft PR #37 remains unmerged.

## OPE-262 — Local PostgreSQL 18 with pgvector

### What we are building

PostgreSQL is the local authoritative relational database foundation for Serviq. “Authoritative” means that durable business facts will eventually live there rather than in a temporary cache. pgvector adds vector data types and similarity-search support inside PostgreSQL, which gives later knowledge-retrieval work a practical V1 vector-search path without immediately adding another database product.

### What changed

The branch `ope-262-postgres-pgvector-compose` creates the local Docker Compose foundation. It defines a pinned PostgreSQL 18-compatible pgvector image, binds the local database port to the developer machine, adds a named data volume, and adds a `pg_isready` healthcheck. A tiny initialization file enables the PostgreSQL `vector` extension on a new local database. A development environment template documents the local database variables and clearly separates local defaults from future production configuration.

### Why the vector extension is separate from Serviq tables

Enabling a database capability is not the same as designing the product database. This ticket does not create organizations, users, conversations, policies, orders, audit records, or any other Serviq table. Those tables need migrations, constraints, indexes, tenant isolation, and security review in their own tickets.

### What this improves

Future backend work receives one reproducible local database target. Later RAG and retrieval work can begin with PostgreSQL plus pgvector, keeping the V1 operational footprint smaller until measured scale proves that a separate vector/search product is necessary.

### What is intentionally not implemented

There are no Serviq tables, Alembic migrations, row-level-security rules, tenant queries, backups, replicas, cloud database settings, application database connections, or production credentials.

### Validation status

The Compose YAML parses successfully. Docker is not available in the current execution environment, so live PostgreSQL startup, health transition, vector-extension verification, and persistence tests are still pending. OPE-262 remains In Progress and draft PR #38 remains unmerged.

## OPE-263 — Local Valkey cache

### What we are building

Valkey is Serviq's local fast, temporary key/value store. The easiest way to understand the difference between PostgreSQL and Valkey is to imagine a filing cabinet and a whiteboard. PostgreSQL is the filing cabinet for records the business cannot afford to lose. Valkey is the whiteboard for information that is useful to access quickly but can be reconstructed if the whiteboard is erased.

Future examples may include short-lived rate counters, provider-health state, hot configuration, or cache metadata.

### What changed

The branch `ope-263-valkey-compose` is stacked on OPE-262 because both tickets extend the same Compose file. It adds a pinned Valkey 8.1 service, local port exposure, a readiness check based on the Valkey command-line client, and infrastructure documentation that explicitly describes the service as rebuildable cache rather than durable business storage.

The service does not receive a persistent data volume in this ticket. That choice reinforces the architecture rule that losing the cache must never lose a completed business mutation.

### Why no cache keys were invented

A cache key is a contract: it implies what data is cached, how long it lives, who can read it, and how it is invalidated. OPE-263 does not yet have the business features that should define those rules. Provisioning the infrastructure without speculative application behavior keeps later decisions reviewable.

### What this improves

Future tickets have a predictable low-latency local service instead of independently introducing caches. The explicit “rebuildable only” rule also prevents accidental use of Valkey as the sole record of a refund, policy update, or other durable event.

### What is intentionally not implemented

There is no session design, rate-limit middleware, semantic response cache, cache-key namespace, TTL policy, invalidation strategy, distributed lock, cluster mode, or production Valkey deployment.

### Validation status

The stacked Compose YAML parses successfully. The live service response and clean-start behavior cannot be tested in the current environment because Docker is unavailable. OPE-263 therefore remains In Progress and draft PR #39 remains unmerged.

## OPE-264 — Local S3-compatible object storage

### What we are building

Not every piece of data belongs in a relational database. Serviq will later store uploaded knowledge documents, normalized document artifacts, exports, and evaluation artifacts. Object storage is designed for those file-like objects.

The architecture requires an S3-compatible local boundary. This lets local development use a free service while future production code can target a cloud object store through the same broad storage contract.

### What changed

The branch `ope-264-object-storage-compose` is stacked on OPE-263. It adds a pinned SeaweedFS 4.41 service in its compact local mode, exposes the S3-compatible endpoint on the developer machine, persists object data in a named volume, configures a local authenticated S3 boundary through environment substitution, and sets the required local bucket target to `serviq-local-objects`.

The infrastructure README documents the Compose hostname, S3 port, bucket name, and the rule that local configuration must never be treated as production configuration.

### Why SeaweedFS is acceptable here

The Serviq architecture does not require application code to depend on a MinIO-specific API. It requires a frozen S3-compatible local implementation. Using an S3-compatible service keeps the important contract at the storage-protocol level. Later application code should talk to a Serviq object-storage adapter rather than importing vendor-specific behavior throughout the product.

### What this improves

Knowledge-ingestion and export tickets now have a defined local object-storage target. The files remain outside application source and public web roots, and a future production move to cloud S3-compatible storage does not require rewriting every feature around a local vendor.

### What is intentionally not implemented

There is no upload endpoint, presigned URL flow, MIME/type/size validation, malware scanning, generated object-key implementation, knowledge parsing, public bucket policy, cloud S3 deployment, or retention lifecycle.

### Validation status

The Compose YAML parses successfully. The current environment has no Docker, so startup, bucket creation, private-access behavior, restart persistence, and a temporary object write/read/delete round trip have not been executed. The branch also still needs its final accepted service-healthcheck implementation. OPE-264 therefore remains In Progress and draft PR #40 remains unmerged.

## OPE-265 — Local Keycloak OIDC service

### What we are building

Keycloak is the local identity-provider foundation for future Serviq workforce authentication. An identity provider is the system that participates in proving who a user is. OIDC, or OpenID Connect, is a standard protocol that applications can use to integrate with that identity provider.

This ticket does not make the Client Console or Platform Console log in. It creates the local identity-service process that later authentication tickets can configure deliberately.

### What changed

The branch `ope-265-keycloak-compose` is based on the OPE-262 Compose foundation. It adds a pinned Keycloak 26.7.1 development service, enables Keycloak health information, exposes the local application and management interfaces only on the developer machine, requires the local bootstrap administrator password to be supplied outside Git, adds a readiness check against Keycloak's management health endpoint, and adds `infra/docker/keycloak/README.md` explaining the boundary.

The changes were committed in small steps: the container, health enablement, management interface, administrator configuration, readiness behavior, and documentation each have their own history.

### Why no Serviq realm or OIDC client exists yet

Realms, client identifiers, redirect addresses, token settings, users, and role mappings are authentication contracts. They affect security and frontend/backend behavior. Creating them inside a container-scaffold ticket would mix infrastructure setup with application-authentication design. OPE-265 deliberately stops before that line.

### What this improves

Later workforce-authentication work gets a free local standards-based identity-provider target and a clear readiness boundary. At the same time, the repository does not falsely imply that authentication is complete simply because an identity service can start.

### What is intentionally not implemented

There is no Serviq realm, OIDC client, permanent user, tenant-role mapping, platform-operator role mapping, login/logout flow, token validation, refresh logic, application authorization guard, SSO federation, or production identity deployment.

### Validation status

The Compose YAML parses successfully. Docker is not available in the current execution environment, so Keycloak startup, readiness, and browser reachability have not been runtime-tested. OPE-265 remains In Progress. A draft PR creation attempt through the connected GitHub action was not accepted, so the implementation branch is currently the review location.

## Current tracking summary

- OPE-261: GitHub issue #32, branch `ope-261-llm-gateway-scaffold`, draft PR #37.
- OPE-262: GitHub issue #33, branch `ope-262-postgres-pgvector-compose`, draft PR #38.
- OPE-263: GitHub issue #34, branch `ope-263-valkey-compose`, draft PR #39.
- OPE-264: GitHub issue #35, branch `ope-264-object-storage-compose`, draft PR #40.
- OPE-265: GitHub issue #36, branch `ope-265-keycloak-compose`; PR creation still pending.

None of OPE-261 through OPE-265 is marked complete yet. Static configuration/source validation has been recorded honestly, while runtime checks that require Docker or the exact Python 3.14 environment remain open acceptance work.
