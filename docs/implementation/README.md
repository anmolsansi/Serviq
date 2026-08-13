# Serviq Ticket Documentation Standard — Explain It So a High-School Student Can Understand It

Every Serviq engineering ticket that changes the repository must have a detailed implementation document at:

```text
docs/implementation/<TICKET-ID>.md
```

Example:

```text
docs/implementation/OPE-252.md
```

This is not meant to be a short developer changelog.

The purpose of the document is to explain the work so clearly that a non-technical reader — for example a product manager, client, recruiter, business owner, or high-school student — can understand:

- what problem we were solving;
- what part of Serviq we changed;
- what code/files we created or modified;
- what those technical files actually mean in normal language;
- how the new logic works step by step;
- why we chose this approach instead of another approach;
- what becomes better because of the change;
- what we deliberately did not build yet;
- how we tested or verified the work;
- what remains before the ticket is completely finished.

The implementation document is part of the ticket's Definition of Done. It must be created during the ticket and finalized before the ticket is moved to Done.

---

## The core writing rule

A reader should **not** need to understand Git, Next.js, TypeScript, APIs, databases, queues, RAG, LLMs, Docker, or cloud infrastructure before opening the document.

When a technical term is necessary, the document must immediately explain it in plain English.

Bad example:

```text
Added pnpm workspace configuration and strict TS config.
```

A non-technical reader learns almost nothing from that sentence.

Better example:

```text
We created a workspace file that tells our JavaScript package manager which folders belong to the same Serviq codebase. Think of it like a school directory that lists which classrooms belong to the school. We also enabled strict TypeScript, which adds rules that catch many data mistakes before the application runs — similar to a form that refuses to accept a word in a field that is supposed to contain a number.
```

The second version explains both **what** changed and **why it matters**.

---

## Required structure for every ticket document

The exact headings may vary slightly when a ticket needs something special, but every implementation record must cover the following ideas.

### 1. What is this ticket about?

Explain the ticket in normal language before mentioning code.

Answer:

- What part of the product are we working on?
- Who will eventually use it?
- What problem existed before this ticket?

Use an analogy when it makes the idea easier to understand.

---

### 2. Where does this fit in the overall Serviq product?

Explain how this ticket connects to the larger system.

For example:

```text
Customer → Customer Web → Serviq API → Agent → Tools → Business systems
```

or:

```text
Root monorepo foundation
        ↓
Client Console
Customer Web
Platform Console
```

A non-technical reader should understand why this piece exists at all.

---

### 3. What did we create, modify, or remove?

List the important files, components, services, database tables, APIs, or configuration changes.

But do not stop at the file name.

For every important file, explain what it does.

Example:

```text
.gitignore
```

should be explained as something like:

> This file tells Git which local files must not be uploaded to GitHub. It protects the repository from generated files and helps prevent local secret files such as `.env` from being committed accidentally.

---

### 4. How does the new logic work?

Explain the flow step by step.

Prefer simple diagrams such as:

```text
User clicks Refund
      ↓
Serviq checks the order
      ↓
Serviq checks refund rules
      ↓
Customer confirms
      ↓
Human approves when required
      ↓
Refund tool runs
      ↓
Result is stored and audited
```

If the ticket is foundational and has no user flow, explain what happens when a developer or system uses the new foundation.

---

### 5. Why did we choose this design?

Explain the reasoning, not only the result.

For example:

- Why separate customer and employee applications?
- Why use a synthetic refund instead of real money?
- Why use one monorepo?
- Why use small commits?
- Why use a queue instead of performing a long task inside a web request?

If another obvious approach exists, briefly explain why we did not choose it.

---

### 6. What does this improve?

Translate the engineering work into outcomes.

Examples:

- safer customer data handling;
- fewer accidental duplicate refunds;
- faster development for later tickets;
- clearer separation of permissions;
- easier debugging;
- lower AI hallucination risk;
- lower cost;
- easier scaling;
- easier onboarding for new engineers;
- better user experience.

Do not write vague claims such as "improves architecture" without explaining how.

---

### 7. Technical details, translated into normal language

The document should still contain enough technical detail for an engineer to reconstruct what happened.

For important code/configuration, show small examples and explain them.

Example:

```json
{
  "strict": true
}
```

Then explain:

> This turns on stronger TypeScript safety checks. It helps catch mistakes before the application is running in front of a customer.

The document should serve both audiences: a beginner should understand the idea, while an engineer should still see the exact implementation decision.

---

### 8. Security and privacy impact

Explain whether the ticket touches:

- passwords or API keys;
- customer information;
- authentication;
- permissions;
- payment/refund actions;
- external network calls;
- cross-company/tenant data;
- file uploads;
- logs/audit information.

If none apply, say so clearly and explain why.

---

### 9. What we intentionally did NOT build

Every ticket has boundaries.

Explain what was deliberately left for later and why.

This helps non-technical readers understand that "not implemented" does not always mean "forgotten."

Often it means we intentionally separated work into safer, reviewable steps.

---

### 10. Micro-commit story

Do more than list commit SHAs.

Explain the development sequence.

For example:

```text
First we created the package definition.
Then we configured TypeScript.
Then we connected styling.
Finally we added the visible page.
```

Include important commit IDs when useful, but the reader should understand the story even if they do not know what a Git commit is.

Also explain that small commits make changes easier to review, debug, and reverse.

---

### 11. Testing and verification

State exactly what was actually tested.

For each check, explain what it means.

Example:

```text
pnpm --filter @serviq/client-console typecheck
```

should be accompanied by something like:

> This asks TypeScript to inspect the application for invalid data-type assumptions without running the product.

Never claim a test passed unless it was actually executed successfully.

If testing is still pending, say that clearly.

---

### 12. What would a user see?

If the ticket affects a screen or user flow, describe the before/after experience.

If it is backend/foundation work with no visible customer difference, say that too.

Example:

> A customer sees no difference yet. This ticket prepares the application shell that the future chat interface will use.

---

### 13. Known limitations and remaining work

Explain what is incomplete, blocked, intentionally deferred, or dependent on later tickets.

The reader should be able to distinguish:

```text
Ticket work completed
vs.
Ticket work coded but not yet tested
vs.
Future feature intentionally out of scope
```

---

### 14. Plain-English glossary

Every document containing meaningful technical language should end with a short glossary.

Examples:

- API
- database
- frontend
- backend
- package manager
- build
- RAG
- LLM
- queue
- event
- cache
- idempotency
- tenant
- authentication
- authorization

Only include terms actually relevant to that ticket.

---

### 15. Final completion record

Before moving the ticket to Done, update the document with:

- final validation results;
- fixes made during testing/review;
- pull request number/link;
- final branch/head commit;
- merge commit;
- final acceptance-criteria status;
- any follow-up tickets created.

The document should describe the ticket as it actually ended, not only how it started.

---

## Recommended writing style

Prefer:

- simple sentences;
- concrete examples;
- diagrams using arrows;
- analogies when useful;
- "before vs. after" explanations;
- explicit reasoning;
- examples of what a customer, employee, or developer would experience.

Avoid unexplained phrases such as:

```text
scaffolded app
wired PostCSS
added RLS
implemented event bus
normalized provider adapter
configured monorepo
```

Those phrases are acceptable only when immediately translated into plain English.

---

## The final quality test

Before a ticket is marked Done, read its `docs/implementation/<TICKET-ID>.md` and ask:

> Could a smart high-school student who has never built a web application explain back to me what we changed, how the main flow works, and why we chose this approach?

If the answer is no, the documentation is not finished.

This documentation standard applies to all Serviq engineering tickets going forward.