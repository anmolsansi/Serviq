# ADR-010 — Deterministic fake LLM adapter identifiers and scenario seam

## Status

Accepted for OPE-293.

## Context

The technology baseline requires deterministic fake model responses for CI and a no-paid-key local/demo mode. Contract C-4 deliberately freezes provider values to `openai`, `anthropic`, `gemini`, and `openrouter`; it does not contain a public `fake` provider value.

OPE-293 also requires scenarios to be selected through a test seam rather than magic strings in normal user messages.

## Decision

1. The shared internal adapter call receives a server-resolved `AdapterContext` containing the normalized C-4 provider, upstream model identifier, and optional resolved API key.
2. The deterministic fake adapter requires no API key and never reads environment/provider credentials.
3. Fake tests/local fixtures use upstream model identifier `serviq-fake-v1`.
4. The normalized provider remains an existing C-4 provider value, normally `openai` in generic fake fixtures. Fake-ness is an implementation/scenario property, not a new public provider enum.
5. Scenario selection is constructor injection using `FakeScenario`; normal C-4 messages contain no hidden control strings.
6. The scenario registry is immutable and explicit. Each scenario maps to deterministic success output or one frozen normalized error category.

## Why this preserves C-4

Adding `provider='fake'` would alter a frozen public enum merely for tests. Keeping the provider normalized while clearly marking the upstream model as synthetic lets the fake adapter exercise the same response contract as real adapters without expanding that contract.

## Scope

This ADR does not define runtime routing, provider fallback, secret resolution, or model-alias lookup. Those layers may choose the fake adapter in test/local mode later, but OPE-293 only supplies the interface and implementation.
