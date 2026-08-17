# ADR-011 — Official provider SDK baseline for V1.2 adapters

## Status

Accepted.

## Context

OPE-294 and OPE-295 require Serviq to use an already approved official provider SDK version. The LLM Gateway scaffold previously had no OpenAI or Anthropic SDK dependency, so both adapter tickets correctly stopped instead of inventing a dependency inside feature code.

The gateway runs on Python 3.14. Any approved SDK must support that runtime, remain provider-local behind Serviq's C-4 adapter boundary, and be pinned tightly enough that CI does not silently change adapter behavior between runs.

## Decision

Serviq V1.2 freezes these official Python SDK versions:

- OpenAI: `openai==2.53.0`
- Anthropic: `anthropic==0.121.0`

Both packages are official provider-maintained SDKs and publish Python 3.14-compatible package metadata.

The versions are exact pins in `services/llm-gateway/pyproject.toml` rather than open-ended ranges. A later upgrade must be intentional and reviewed as a dependency change.

## Adapter boundary rules

1. Provider SDK types may exist only inside provider adapter modules and their tests.
2. Public gateway request, response, stream, and error types remain Serviq-owned Contract C-4 models.
3. Provider API keys are passed through `AdapterContext` as server-resolved secret values. Provider modules must not read arbitrary tenant credentials from environment variables or request payloads.
4. Provider exceptions are translated into the five C-4 normalized error categories before leaving the adapter.
5. CI adapter tests mock the official SDK. They must not make paid or live provider calls.
6. Adding provider-specific fields to C-4 requires a separate contract decision and is not authorized by this ADR.

## Why this decision was made

The adapter tickets cannot be implemented safely until dependency behavior is reproducible. Exact pins make the provider boundary reviewable, keep CI deterministic, and turn the earlier `Needs Architect Decision` stop condition into a resolved architectural prerequisite without weakening either ticket.

## Scope

This ADR approves only the OpenAI and Anthropic SDK dependencies needed by OPE-294 and OPE-295. It does not approve model routing, model aliases, provider fallback, Gemini/OpenRouter dependencies, or any agent-runtime change.
