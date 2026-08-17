# OPE-298 — Provider connectivity-test architecture blockers

## Status

**Needs Architect Decision.** The connectivity endpoint was not implemented because required behavior is not fully frozen and two required provider adapters are still blocked.

## What OPE-298 is trying to build

The ticket defines a safe administrative health check for a stored BYOK provider connection:

```text
POST /api/v1/providers/{providerConnectionId}/test
```

The endpoint must not become a general model-completion proxy. It must create one fixed, minimal request on the server, use the saved tenant-scoped provider connection and secret, call the correct adapter with a short budget, update safe provider metadata, and return only normalized status/error information.

## What is already frozen

Architecture v1.3 defines the route and the default limits:

- `provider.test.user`: 10 requests per minute per tenant user;
- `provider.test.connection`: 30 requests per hour per provider connection.

The provider table also already freezes the available status values: `untested`, `active`, `invalid`, and `disabled`.

## Blocking decisions that are not frozen

### 1. Minimal model-selection strategy

The ticket requires an "architecture-approved minimal model-selection strategy." Repository and architecture searches found no rule naming which upstream model should be used for each provider, whether a saved model configuration must exist first, or how a connectivity test works before model CRUD has been configured.

Selecting a hard-coded provider model in feature code would create a fragile hidden contract, may stop working as providers retire models, and would bypass tenant/model configuration rules.

### 2. Transient-failure status semantics

The ticket says authentication failure sets the connection to `invalid`, but for rate limit, timeout, and unavailable failures it requires the architecture-approved status semantics. The Architecture defines the status vocabulary but does not define whether these transient failures preserve the existing status, reset to `untested`, or move to another state. Inventing this transition would affect UI behavior and provider routing later.

### 3. Required adapters are incomplete

OPE-296 Gemini and OPE-297 OpenRouter cannot currently be implemented because their SDK/transport choices are not approved. Shipping a connectivity endpoint that works only for OpenAI and Anthropic would not satisfy the four-provider MAS-2 scope and would create inconsistent connection behavior.

## Decision required to unblock OPE-298

An architect-approved change must freeze:

1. the provider-by-provider minimal model-selection rule for connectivity testing;
2. whether model configuration is required before a provider test, and if not, where safe test-model identifiers live;
3. exact status transitions for rate-limit, timeout, provider-unavailable, and other transient failures;
4. stable `last_error_code` values for those outcomes;
5. how the API service invokes the LLM Gateway/common adapter boundary without placing an external model call inside a database transaction;
6. the already-blocked Gemini and OpenRouter adapter prerequisites.

## Why stopping improves the product

A provider-test endpoint changes persisted trust metadata. Getting the state machine wrong can mark a working provider invalid because of a temporary outage, or mark an unverified provider active based on the wrong model. Stopping until the rules are explicit prevents misleading provider health, accidental paid/free-form completion behavior, and future routing bugs.

## What changed in this branch

Only this architecture-blocker record was added. No endpoint, external provider call, rate limiter, provider metadata transition, secret access, or gateway contract was changed.
