# OPE-297 — OpenRouter adapter architecture blocker

## Status

**Needs Architect Decision.** No OpenRouter adapter code was added because the ticket's explicit stop condition is currently true.

## What OPE-297 is trying to build

OPE-297 is intended to make OpenRouter interchangeable with the other providers behind Serviq's Contract C-4. The adapter must accept only a server-resolved BYOK credential and validated upstream model, use a Serviq-controlled endpoint, normalize generation and streaming results, and prevent caller-controlled base URLs or provider-only response details from escaping into shared contracts.

## What was inspected before coding

The builder inspected the OPE-297 ticket, current Architecture and Tech Stack, Contract C-4, the provider adapter interface, the current gateway dependency manifest, ADR-011, and the OpenAI/Anthropic implementation patterns.

## Blocking fact

The repository has no frozen OpenRouter transport/client choice.

ADR-011 approves only the official OpenAI and Anthropic SDK dependencies and explicitly states that it does **not** approve OpenRouter dependencies. The LLM Gateway manifest contains no OpenRouter-specific client dependency or architectural rule saying that OpenRouter must use the OpenAI-compatible SDK path, direct HTTP, or another transport.

OPE-297 says to stop with `Needs Architect Decision` when the OpenRouter transport/client choice is not frozen. That condition is currently true.

## Why the branch did not simply reuse the OpenAI SDK

OpenRouter exposes an OpenAI-compatible API surface, but compatibility does not itself authorize Serviq to choose that implementation strategy. Reusing the OpenAI SDK with an OpenRouter base URL would decide several architecture/security questions at once:

- who owns the fixed base URL;
- whether the OpenAI SDK is the approved OpenRouter transport;
- whether OpenAI-specific retry/error assumptions safely map to OpenRouter;
- which provider-specific headers are permitted;
- how request IDs and usage metadata are normalized;
- how future SDK upgrades affect two providers at once.

A builder must not make those decisions implicitly, especially because OPE-297 expressly requires the choice to be frozen before coding.

## Decision required to unblock OPE-297

An architect-approved change must freeze:

1. the OpenRouter transport strategy;
2. the exact client/dependency and version if a package is used;
3. the Serviq-owned immutable OpenRouter base URL and prohibition on request-controlled overrides;
4. timeout/retry ownership;
5. provider-specific header policy;
6. Python 3.14 compatibility and dependency-locking expectations.

Once merged, OPE-297 can implement the adapter, mocked tests, error normalization, and premium security review without changing C-4.

## Product impact

This stop prevents a subtle SSRF/configuration-control risk and avoids coupling shared gateway behavior to an unreviewed transport. It preserves the rule that users choose credentials and validated models, not arbitrary upstream endpoints.

## What changed in this branch

Only this architecture-blocker record was added. No production code, OpenRouter endpoint, dependency, provider route, C-4 field, secret behavior, or agent runtime behavior was changed.
