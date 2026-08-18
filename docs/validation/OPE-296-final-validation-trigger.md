# OPE-296 — final validation marker

This record explains the final validation sequence for OPE-296.

The implementation code, mocked Gemini contract tests, premium security review, plain-language implementation guide, and cumulative `SERVIQ_BUILD_GUIDE.md` update are all present on this branch.

## Why a normal validation commit was needed

The one-time build-guide finalizer committed the large cumulative-guide append as `github-actions[bot]`. GitHub classified the automatic pull-request workflows for that bot-authored commit as `action_required` without creating test jobs. That state was a workflow-trigger/actor condition rather than a code-test failure.

A normal repository-authored commit was therefore created so CI and Security evaluate the exact branch tree through the usual pull-request path.

## Additional security hardening found during final review

The final review found that the repository's explicit `pip-audit` workflow covered the API and worker Python environments but did **not** explicitly export and audit the LLM Gateway Python dependency set.

That gap matters for OPE-296 because the ticket introduces `google-genai==2.17.0` and directly declares `httpx==0.28.1` in the gateway.

The branch now also updates:

- `.github/workflows/security.yml` to export the LLM Gateway production dependency set, run `pip-audit` against it, upload the resulting `llm-gateway-pip-audit.json` report with the other dependency reports, and fail the Security workflow if that audit fails;
- `Makefile` so the local `make security` command runs the same LLM Gateway dependency audit in addition to the existing pnpm/API/worker audits.

The LLM Gateway currently has no committed `uv.lock`, so this audit resolves the gateway's declared production dependency graph during the security job rather than falsely using `--frozen`. The provider package itself remains exact-pinned by ADR-012 and `pyproject.toml`.

This change is intentionally part of OPE-296 because a production provider dependency should be included in the repository's explicit vulnerability-audit gate before the ticket is closed.

## Final evidence location

The final CI/Security results and merge SHA are recorded in GitHub PR #137 and the OPE-296 GitHub/Linear ticket comments. This file is not edited again after those results, because another commit would create a new unvalidated PR head.
