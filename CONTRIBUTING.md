# Contributing to Serviq

Read the Linear ticket, linked GitHub issue, and `docs/repo_context.md` before coding. Inspect the exact files named by the ticket and do not treat architecture plans as proof that code already exists.

Use one ticket per branch and pull request. A typical branch name is `ope-271-repository-governance`. Do not develop directly on `main`. Push small commits with the ticket identifier and a short explanation.

Use `make setup` to install dependencies. Before review, run `make lint`, `make typecheck`, and `make test`. The `make security`, `make e2e`, and `make load-test` targets are intentional non-zero placeholders until their dedicated implementation tickets land, so do not report them as passing while they are placeholders. Use `make dev` for core local infrastructure and `make down` to stop it.

Do not silently invent or change architecture-owned API, database, event, authentication, authorization, or shared contracts. If a required contract is missing, record `Needs Architect Decision: ...`. If an approved contract changes, reference its Contract Change Record under `docs/contract-changes/`.

Use `.github/pull_request_template.md` to report the ticket, summary, important files, validation, manual QA, contract-change status, security impact, unresolved architect decisions, completed scope, deferred work, and follow-up work. A pushed branch or open pull request is not the same as a completed ticket.

Long-form implementation explanations belong in the cumulative `docs/SERVIQ_BUILD_GUIDE.md`. Explain what changed, how it works, why it was done, what it improves, how it was validated, and what is intentionally still missing. Do not create a separate long-form worklog for each ticket unless the repository convention is explicitly changed.
