# ADR-002 — API health module boundary

**Status:** Accepted  
**Scope:** Serviq API liveness/readiness endpoints  
**Decision owner:** Architecture  
**Applies from:** OPE-276

## Context

Architecture freezes `GET /health/live` and `GET /health/ready`, but the audited API scaffold has no implemented health router or existing feature module that can own them. OPE-276 requires database-backed readiness while also forbidding a builder from inventing a conflicting router pattern. A small architecture decision is therefore required before route code is added.

## Decision

Health endpoints are an infrastructure module, not a product-domain module.

The ownership boundary is:

- `services/api/app/modules/health/router.py` owns `/health/live` and `/health/ready` HTTP behavior.
- `services/api/app/modules/health/service.py` owns readiness dependency orchestration and the two-second database budget.
- `services/api/app/core/database.py` owns the low-level PostgreSQL ping because database access remains inside the database core boundary established by ADR-001.
- `services/api/app/main.py` only composes the health router into FastAPI.

The health router is mounted without `/api/v1` because `/health/*` is an infrastructure contract frozen separately from product REST endpoints.

`/health/live` is process-only and must never call PostgreSQL or any other dependency.

`/health/ready` currently depends only on PostgreSQL. It returns the exact frozen bodies from OPE-276 and must normalize database exceptions/timeouts so raw driver/SQLAlchemy details are not exposed.

## Failure logging

The repository's structured telemetry implementation is still intentionally deferred. OPE-276 may use Python's named logger at the health service boundary, but it may log only a stable event code such as `database_readiness_failed` or `database_readiness_timeout`. It must not attach the caught exception object, connection URL, SQL text, hostname, credentials, or traceback. A later observability ticket may replace/configure the logging backend without changing this safety rule or the health API contract.

## Why this decision

Health checks are cross-cutting infrastructure behavior and do not belong to customer, tenant, order, or other future product modules. Separating the HTTP router from dependency orchestration makes the exact public response easy to test while keeping SQL execution inside the single database ownership boundary.

## Non-decisions

This ADR does not add Redis/Valkey, broker, object-storage, LLM-provider, or downstream integration checks to readiness. It does not define Kubernetes manifests, probe intervals, startup probes, structured logging format, correlation middleware, or production alerting.
