# Serviq Per-Ticket Implementation Documentation Standard

Every Serviq engineering ticket that changes the repository must have a detailed implementation record under:

```text
docs/implementation/<TICKET-ID>.md
```

Example:

```text
docs/implementation/OPE-252.md
```

The implementation record is part of the ticket's Definition of Done. It must be created during the ticket and finalized before the ticket is moved to Done.

## Required content

Each ticket document must explain, in enough detail for a future engineer to understand the change without reconstructing the entire Git history:

1. **Ticket metadata** — ticket ID/title, GitHub issue, branch, dependency, and current/final status.
2. **Goal and problem** — what problem the ticket solves and why it exists.
3. **Changes performed** — files/components/services/contracts created, modified, or removed.
4. **Why each meaningful change was made** — architectural/product/security/UX reasoning, not only a file list.
5. **What the change improves** — reliability, security, maintainability, performance, usability, scalability, developer experience, or downstream capability.
6. **Architecture and contract impact** — which existing boundaries are preserved or changed.
7. **Security/privacy impact** — secrets, auth, permissions, PII, network boundaries, side effects, or an explicit statement when none apply.
8. **Micro-commit summary** — important commits and the purpose of each logical group of commits.
9. **What was intentionally not changed** — scope protection and deferred work.
10. **Testing and validation** — exact checks run and their outcome. Never claim a command passed unless it was actually executed.
11. **Manual QA** — applicable user-visible or operational verification.
12. **Known limitations / remaining work** — unresolved items, follow-up tickets, or conditions required before Done.
13. **Acceptance-criteria result** — final checklist against the ticket.
14. **PR/merge information** — PR link/number, final head/merge commit, and release impact when available.

## Quality rule

A one-line changelog is not sufficient. The document should explain both **what changed** and **why the implementation is better because of it**.

## Accuracy rule

The implementation record is an engineering record, not marketing copy.

- Unrun tests must be labeled unrun.
- Architectural targets must not be reported as measured capacity.
- Synthetic/mock behavior must not be described as a real external integration.
- Known failures or incomplete acceptance criteria must remain visible until fixed.

## Contract authority

These implementation records do not override the authoritative product and architecture documents.

When there is a conflict, authority remains:

1. `docs/PRD.md` — Production V1 product scope;
2. `docs/ARCHITECTURE.md` — system/API/database/event/security contracts;
3. `docs/TECH_STACK.md` — approved technology/dependency choices;
4. architect-owned ADR/CCR records;
5. ticket implementation records.

A ticket document describes how a ticket implemented the frozen contracts. Contract changes still require the formal ADR/CCR process.

## Completion workflow

Before moving a ticket to Done:

```text
Implementation complete
  -> tests/validation complete
  -> manual QA complete where applicable
  -> docs/implementation/<TICKET-ID>.md finalized
  -> GitHub issue/PR updated
  -> acceptance criteria verified
  -> ticket moved to review/done according to workflow
```

This convention applies to OPE-251 onward and should be used for future Serviq implementation tickets unless explicitly superseded by a later project-process decision.
