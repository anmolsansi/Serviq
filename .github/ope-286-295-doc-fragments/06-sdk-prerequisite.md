# Architectural prerequisite for OPE-294 and OPE-295 — Freeze official SDK versions

The OpenAI and Anthropic tickets both contained a stop condition: do not invent an SDK/version inside a feature ticket. The repository did not yet have either approved provider SDK.

Instead of ignoring that requirement, implementation stopped and the architecture decision was made separately.

ADR-011 freezes:

```text
openai==2.53.0
anthropic==0.121.0
```

in the LLM Gateway dependency baseline.

The ADR also freezes the rules that:

- SDK types stay inside provider adapter modules/tests;
- public gateway objects remain C-4 types;
- API keys enter through server-resolved `AdapterContext`;
- provider exceptions are normalized before leaving an adapter;
- CI uses mocked SDK calls rather than paid live calls;
- future SDK upgrades are explicit reviewed dependency changes.

This prerequisite was merged through PR #122 before either real provider adapter was implemented.

---
