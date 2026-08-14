# Serviq — Plain-Language Product and Build Guide

**Purpose of this document**  
This is the single, cumulative explanation of what we are building in Serviq, what we have already changed in the codebase, how the pieces fit together, why each technical decision exists, and what those decisions improve.

This document is intentionally written so that a non-technical reader — including a high-school student — can understand the product and the engineering work without first learning software architecture, cloud systems, AI terminology, or Git.

It is not meant to replace the PRD, architecture document, or source code. Those are the precise engineering contracts. This guide explains the same work in normal language.

**Documentation rule:** after every Serviq ticket is completed, this file is updated. We do not create a separate long-form explanation file for every ticket. Ticket IDs are still mentioned here so a reader can connect the explanation to GitHub and Linear history, but this remains one continuously updated story of the product.

---

## 1. What is Serviq?

Serviq is an AI customer-operations platform.

A simple way to imagine it is this:

A customer opens a support chat and says:

> “Where is my order?”

A basic chatbot may try to answer from general knowledge or from a help article. Serviq is designed to do more.

Serviq should be able to:

1. understand what the customer is asking;
2. search the company’s approved support information;
3. look up the customer’s business data when the customer is allowed to see it;
4. decide whether a business action is safe and permitted;
5. perform that action when allowed;
6. ask for confirmation when an action is important;
7. ask a human employee for approval when a policy requires it;
8. explain the result clearly to the customer;
9. record what happened so the business can review it later;
10. send the full case to a human support agent when the AI should not continue on its own.

So Serviq is not being designed as “a chatbot that writes answers.”

It is being designed more like a digital support employee that can read company instructions, check company systems, follow rules, take approved actions, and know when a human must take over.

---

## 2. The easiest way to understand the Serviq architecture

Think of a large restaurant.

The customer only sees the waiter, but the waiter depends on many other parts of the restaurant:

- the menu;
- the kitchen;
- the billing system;
- the manager;
- the stock room;
- the order queue;
- the payment machine;
- the customer-service desk.

Serviq works in a similar way.

The customer sees one support experience, but behind it Serviq needs several systems that each have a specific responsibility.

```text
Customer
   |
   v
Serviq support experience
   |
   v
AI agent
   |
   +--> Company knowledge
   |
   +--> Customer / order / delivery information
   |
   +--> Payment information
   |
   +--> Business rules and permissions
   |
   +--> Approved actions
   |
   +--> Human support when needed
```

The important idea is that the AI is not allowed to simply “do whatever it thinks is correct.”

The AI can suggest what should happen, but the surrounding Serviq platform controls what information it can access and what actions it may perform.

That separation is one of the main differences between a demo chatbot and a production system.

---

## 3. Why we did not start by building the AI chat screen

It is tempting to start a project like this by creating a beautiful chat page and connecting an AI model.

That would create something impressive very quickly, but it would create the wrong foundation.

Imagine building a 50-floor building. It would be strange to decorate the 20th floor before building the foundation, lifts, electricity, fire exits, and supporting structure.

The first Serviq tickets therefore focus on the foundation:

- deciding what the first realistic demo will represent;
- creating the repository structure;
- deciding how frontend applications are separated;
- creating the basic application shells;
- making the project ready for later authentication, APIs, AI agents, databases, monitoring, testing, and deployment.

The current work may look simple because much of it is configuration and empty application structure. That simplicity is deliberate. We are creating stable places where the actual features can be added later without repeatedly rebuilding the project structure.

---

# Part I — The first realistic Serviq demo

## 4. The demo world: DoorDash-style customer operations + Stripe-style payments

The first product decision was originally heading toward a Stripe-only payment-support demo.

We changed that because payment support alone does not show enough of what Serviq is intended to become.

The stronger reference configuration combines two separate ideas:

- **DoorDash is the reference customer-support and delivery domain.** It gives us understandable customer situations such as order status, delivery status, missing items, incorrect items, credits, refunds, and escalation.
- **Stripe is the reference payment-provider domain.** It gives us a clean model for payment status and refund processing.

These are reference domains. We are **not** claiming that DoorDash uses Stripe internally, and we are **not** claiming that Serviq is connected to, endorsed by, or built for either company.

The purpose is to create a realistic support story that anyone can understand.

### Example

Suppose a customer says:

> “My food arrived, but one burger is missing. Can you refund that item?”

Serviq should eventually do something like this:

```text
1. Understand the complaint.
2. Read approved DoorDash-style support guidance.
3. Look up the customer's synthetic order.
4. Confirm that the burger was part of the order.
5. Check delivery and order state.
6. Check the rules for when a partial refund is allowed.
7. Look up the synthetic payment record.
8. Calculate the maximum refundable amount.
9. Ask the customer to confirm the refund when required.
10. Ask a human employee for approval if policy requires it.
11. Create a synthetic refund.
12. Tell the customer what happened.
13. Save an audit record explaining why the action was allowed.
```

This one example demonstrates most of the hard parts of a real AI support platform: knowledge retrieval, private customer data, business rules, tool use, permissions, money-related actions, confirmation, human approval, and audit history.

### What OPE-251 actually completed

OPE-251 did **not** build the order database, AI agent, crawler, or refund function. Its job was to remove ambiguity before those systems are built.

The ticket froze the reference contracts that later engineers will implement:

```text
Primary support reference: DoorDash support/delivery domain
Separate payment reference: Stripe payment/refund domain
Source policy: doordash-stripe-allowlist-v1
Status tool: demo.get_delivery_order_status
Eligibility tool: demo.check_order_resolution_eligibility
Mutation tool: demo.create_refund
```

It also froze the rule that all private demo records are synthetic. The DoorDash reference does not authorize unrestricted crawling: every source must be explicitly approved/permitted, and Serviq must never bypass authentication, anti-bot controls, terms, or access restrictions. The deterministic V1 refund changes only Serviq synthetic data and moves no real money.

The decision history was merged in GitHub PR #8. The remaining PRD, Product Specification, and Architecture wording was then synchronized in PR #9 so future MAS-7 implementation tickets no longer see a contradictory “choose a demo company/domain” blocker.

---

## 5. Why the private demo data is synthetic

Serviq will not use real DoorDash customers, orders, delivery records, payment information, or refund information in the public portfolio demo.

Instead, we create fake-but-realistic records generated specifically for Serviq.

For example:

```text
Customer:
  Maya Sharma

Order:
  DEMO-ORDER-1042

Items:
  2 burgers
  1 fries
  1 drink

Delivery status:
  delivered

Reported problem:
  one burger missing

Payment:
  $31.50

Refund requested:
  $8.25
```

None of this belongs to a real customer.

This gives us three advantages.

### Safety

We do not expose private customer information.

### Repeatability

A developer or recruiter can run the same demo many times and receive predictable results.

### Control

We can intentionally create test situations such as:

- order still preparing;
- order delivered;
- item missing;
- payment failed;
- partial refund already issued;
- refund allowed;
- refund denied;
- human approval required.

That allows us to test Serviq properly instead of depending on random real-world data.

---

## 6. The first three business tools

An AI agent becomes useful when it can interact with trusted systems instead of only generating text.

For the first demo, we freeze three tool categories.

### A. Delivery/order status tool

Conceptually:

```text
demo.get_delivery_order_status
```

This tool answers questions such as:

- Has my order been accepted?
- Is it being prepared?
- Has it been picked up?
- Is it out for delivery?
- Was it delivered?

The important point is that the AI does **not guess** this information.

The tool reads the structured synthetic order and delivery record and returns the known state.

### B. Resolution eligibility tool

Conceptually:

```text
demo.check_order_resolution_eligibility
```

This tool answers a different question:

> “According to the order state and the business rules, what resolution is the customer actually allowed to receive?”

For example, the result might say:

```text
Eligible for partial refund: yes
Maximum refund: $8.25
Customer confirmation required: yes
Human approval required: no
```

This prevents the AI from inventing refund policy.

### C. Protected refund tool

Conceptually:

```text
demo.create_refund
```

This is a state-changing operation.

Unlike merely reading information, a refund changes business data. That makes it more sensitive.

Serviq therefore places additional controls around it.

The AI cannot directly decide to issue a refund just because it generated the sentence “I will refund you.”

Instead the request flows through Serviq policy checks, confirmation rules, approval rules, and idempotency protection before the refund operation is allowed.

In the first public demo this refund only changes synthetic Serviq data. It does not move real money and does not call a production Stripe account.

---

## 7. Why this combined demo is useful

A Stripe-only demo would mainly show payment support.

A DoorDash-style delivery demo alone would mainly show order support.

Together, they demonstrate a much more realistic company architecture.

Real businesses rarely store everything in one system. One system may handle orders, another may handle delivery, another may handle payments, and another may handle support tickets.

Serviq is therefore being designed to sit above these systems and coordinate them safely.

That is much closer to the long-term product vision.

---

# Part II — Creating the project foundation

## 8. What a repository is

The Serviq GitHub repository is the main home of the project.

A repository contains:

- application source code;
- configuration;
- technical documentation;
- tests;
- infrastructure definitions;
- change history.

Every change is recorded through Git commits. This lets us see what changed, when it changed, and why.

For Serviq we intentionally make small logical commits instead of waiting several days and pushing one huge change.

That makes code review easier because a reviewer can inspect one idea at a time.

---

## 9. What a branch is and why every ticket receives one

A Git branch is like making a safe copy of the project timeline where one piece of work can be developed without disturbing the main version.

For example:

```text
main
 |
 +-- ope-252-root-toolchain
 |
 +-- ope-253-client-console-scaffold
 |
 +-- ope-254-customer-web-scaffold
 |
 +-- ope-255-platform-console-scaffold
```

Each ticket receives its own branch so that:

- unrelated changes do not get mixed together;
- a broken experiment does not break the main project;
- every ticket can be reviewed independently;
- each feature has a clear history.

When the ticket is ready and reviewed, its branch can be merged into the main project.

---

## 10. What we mean by “micro-level commits”

Instead of making one commit called:

```text
Build frontend
```

we make smaller commits such as:

```text
Add workspace configuration
Add Node version configuration
Add TypeScript configuration
Add lint configuration
Add Tailwind configuration
Add application layout
Add foundation page
```

This may look like extra work, but it improves the project in several ways.

If something later breaks, we can identify which logical change introduced the problem.

A reviewer can understand the intent of each change.

A future developer can study the project history almost like reading chapters in a book.

---

# Part III — OPE-252: creating the monorepo foundation

## 11. What is a monorepo?

Serviq will eventually contain several applications and services.

We could put each one in a completely separate GitHub repository, but for this project we chose a **monorepo**.

A monorepo means multiple related applications live in the same repository.

An easy analogy is a school campus.

The campus is one property, but it may contain:

- a science building;
- a library;
- a gym;
- an administration building.

They serve different purposes but share the same campus rules and infrastructure.

Serviq is similar.

We will have separate applications, but they share one codebase and common engineering rules.

The top-level structure begins like this:

```text
Serviq/
  apps/
  packages/
  services/
  docs/
```

The current workspace setup focuses on `apps/*` and `packages/*`. Python backend services are intentionally not pulled into the JavaScript workspace because they use a different language/toolchain.

---

## 12. Root `package.json`

The root `package.json` is the main JavaScript/TypeScript project manifest.

You can think of it as the label on the front of a toolbox.

It tells development tools things such as:

- this is a private project, not a package that should accidentally be published to npm;
- which package manager the project expects;
- which common commands exist.

At this stage we intentionally keep the root scripts minimal.

Later, commands such as linting, type checking, and testing will run across the workspace.

### Why this matters

Without a common root manifest, every application can slowly develop different commands and assumptions.

The root manifest gives Serviq one consistent developer entry point.

---

## 13. `pnpm-workspace.yaml`

Serviq uses pnpm for JavaScript package management.

The workspace file tells pnpm which folders belong to the JavaScript/TypeScript workspace.

Conceptually:

```text
apps/*
packages/*
```

That means an application such as:

```text
apps/client-console
```

and a future shared package such as:

```text
packages/ui
```

can work together without pretending they are unrelated projects.

### Why we did this

Later, several Serviq applications will share code such as:

- UI components;
- API contracts;
- TypeScript types;
- security helpers;
- configuration;
- testing utilities.

A workspace makes those relationships manageable.

---

## 14. `.nvmrc`

Different Node.js versions can behave differently.

If one developer uses Node version A and another uses version B, a project may work on one computer and fail on another.

`.nvmrc` records the Node version family expected by the project.

It is a small file, but it reduces “works on my machine” problems.

---

## 15. `.gitignore`

Not every file on a developer’s computer belongs in GitHub.

Some files are generated automatically. Some contain machine-specific settings. Some may contain secrets.

`.gitignore` tells Git which types of files should normally stay out of the repository.

Examples include:

- `.env` files that may contain API keys;
- installed dependencies;
- build output;
- test coverage files;
- temporary Python files;
- local object-storage data;
- IDE/editor metadata.

### Why this is important

The most important reason is security.

A developer should not accidentally commit a secret API key because their `.env` file happened to be in the project folder.

It also keeps the repository clean by avoiding thousands of generated files.

---

## 16. `.editorconfig`

Different developers and editors can format files differently.

For example, one computer may use tabs while another uses spaces. One may use Windows line endings while another uses Unix line endings.

`.editorconfig` provides basic formatting rules so editors behave consistently.

This reduces meaningless code changes where the only difference is whitespace.

---

# Part IV — Why Serviq has three frontend applications

## 17. One product does not mean one screen

Serviq has several groups of users with very different needs.

Putting all of them into one giant frontend application would make security, navigation, permissions, and future deployment harder.

So we created three separate application foundations.

```text
apps/
  client-console/
  customer-web/
  platform-console/
```

They share the Serviq repository, but each has a different responsibility.

---

# Part V — OPE-253: Client Console

## 18. What the Client Console is

The Client Console is the application used by the business that adopts Serviq.

Imagine a company using Serviq for customer support.

Employees of that company would eventually use the Client Console to:

- connect AI model providers;
- upload or connect support knowledge;
- configure AI agents;
- configure business tools;
- configure policies;
- review conversations;
- handle escalations;
- approve protected actions;
- view analytics;
- manage team members and permissions;
- inspect audit history.

This is very different from what an end customer should see.

That is why it deserves a separate application.

---

## 19. What we technically created for the Client Console

At the moment, the Client Console is deliberately only a foundation shell.

The path is:

```text
apps/client-console/
```

It uses:

- Next.js;
- React;
- TypeScript;
- Tailwind CSS;
- Next.js App Router.

### What those names mean in plain language

**React** helps us build the user interface from reusable pieces.

**Next.js** provides the application framework around React. It handles routing, server rendering, builds, and other web-application features.

**TypeScript** is JavaScript with additional type checking. It can catch many mistakes before the code runs.

**Tailwind CSS** gives us a structured way to style the interface.

**App Router** is the routing model we will use to turn folders and files into web pages.

---

## 20. Why TypeScript strict mode matters

Imagine a function expects a number but accidentally receives the word `hello`.

In plain JavaScript, that kind of mistake may survive until the code runs in the browser.

TypeScript helps catch many of these mismatches earlier.

Strict mode makes TypeScript less forgiving, which is useful in a large application where incorrect data types can cause subtle bugs.

We therefore start strict rather than adding strictness later after hundreds of files already exist.

---

## 21. Why the Client Console currently looks simple

The current page only identifies itself as the Serviq Client Console foundation.

That is intentional.

We did **not** add:

- authentication;
- menus;
- charts;
- fake analytics;
- fake API calls;
- agent configuration;
- support inbox features.

Those belong to later tickets.

A foundation ticket should prove that the application exists and has the correct technology setup without mixing in unrelated product decisions.

---

# Part VI — OPE-254: Customer Web

## 22. What Customer Web is

Customer Web is the support experience used by the end customer.

This is where a customer will eventually type things such as:

- “Where is my order?”
- “I received the wrong item.”
- “Can I cancel this?”
- “Can I get a refund?”
- “I want to talk to a human.”

The path is:

```text
apps/customer-web/
```

It uses the same frontend foundation — Next.js, React, TypeScript, and Tailwind — but it is a separate application.

---

## 23. Why Customer Web is separate from the Client Console

This separation is mainly about audience and security.

The customer should not have access to internal pages such as:

- agent configuration;
- company analytics;
- support-agent notes;
- organization members;
- API keys;
- audit logs.

Likewise, the internal business application should not be designed like a public customer widget.

Keeping the applications separate makes these boundaries clearer.

It also allows each app to evolve independently. Customer Web may eventually prioritize mobile speed, embeddability, and simple chat interaction, while the Client Console may prioritize dense business workflows and dashboards.

---

## 24. What Customer Web contains today

Only the basic application shell.

We intentionally have not added:

- chat UI;
- customer login;
- tenant-specific URLs;
- streaming AI responses;
- API communication;
- order lookup;
- refund actions.

Those features will be built later on top of the stable shell.

---

# Part VII — OPE-255: Platform Console

## 25. What the Platform Console is

The Platform Console is not for the customer and not for a normal Serviq client employee.

It is for the people operating Serviq itself.

Think of it as the control room for the platform.

Serviq operators will eventually need to answer questions such as:

- Is the system healthy?
- Is an AI provider failing?
- Are background jobs stuck?
- Is a queue growing too large?
- Is one tenant creating abnormal traffic?
- Is a feature flag causing an incident?
- Which organizations exist?
- Are rate limits working?
- Is there a security event that needs investigation?

The application lives at:

```text
apps/platform-console/
```

---

## 26. Why the Platform Console is a separate trust boundary

A normal business using Serviq should not automatically gain access to Serviq-wide platform information.

For example, a client should not be able to inspect:

- another client’s organization;
- global infrastructure health;
- global abuse controls;
- internal incident-management information.

The Platform Console therefore becomes a separate privileged surface.

This matters especially as Serviq becomes multi-tenant — meaning many independent companies may use the same platform.

Keeping platform operations separate from tenant operations reduces the chance that permissions become confused later.

---

# Part VIII — What the frontend scaffold files actually do

## 27. `package.json` inside each app

Each frontend application has its own package manifest.

This identifies the application and defines commands such as:

```text
dev
build
lint
typecheck
```

In simple language:

- `dev` runs the application while a developer is working on it;
- `build` creates the production version;
- `lint` checks code for suspicious or inconsistent patterns;
- `typecheck` asks TypeScript to verify the code’s types.

Having the same command names across applications makes the monorepo predictable.

---

## 28. `tsconfig.json`

This configures TypeScript.

Among other things, it enables strict checking and tells TypeScript how to understand the project’s source files.

The benefit is earlier error detection.

---

## 29. Next.js configuration

The Next.js configuration tells the framework how the application should be built and run.

At this stage we deliberately keep it minimal because unnecessary configuration creates maintenance work and can lock the project into decisions that are not yet needed.

---

## 30. ESLint configuration

ESLint checks source code for patterns that may be mistakes or violate project conventions.

It is similar to a grammar checker for code.

It does not prove that the application is logically correct, but it catches many avoidable problems.

---

## 31. Tailwind / PostCSS configuration

These files connect the styling system to the application build process.

Without them, Tailwind classes written in the user interface would not be processed correctly.

Again, the current styling is intentionally simple. The goal of these tickets is to prepare the system, not complete the final Serviq design.

---

## 32. Root layout

In a Next.js App Router application, the root layout is the outer shell that surrounds application pages.

It is a good place for application-wide things such as:

- page metadata;
- global CSS;
- later providers and top-level wrappers.

We added minimal metadata identifying each Serviq application.

---

## 33. Foundation page

Each current frontend app has a minimal page showing what application it is.

The purpose is not visual polish yet.

The page exists to confirm the application has a valid entry point and to give future tickets a clean place to begin.

---

# Part IX — How the pieces will eventually work together

## 34. Example: “Where is my order?”

A future Serviq request may look like this internally:

```text
Customer Web
    |
    | customer sends message
    v
Serviq API
    |
    v
Agent runtime
    |
    +--> identifies request as order/delivery status
    |
    +--> verifies customer identity if needed
    |
    +--> calls delivery/order status tool
    |
    v
Synthetic order system
    |
    v
Verified structured result
    |
    v
Serviq returns answer to Customer Web
```

For a simple structured fact, an expensive generative AI response may not even be necessary for the core data lookup.

This improves accuracy and cost because the order state comes from the system of record rather than model memory.

---

## 35. Example: “Can I get a refund for the missing burger?”

This request is more complicated.

```text
Customer message
    |
    v
Agent understands missing-item/refund intent
    |
    +--> retrieves approved support knowledge
    |
    +--> reads synthetic order + item + delivery data
    |
    +--> reads payment/refund state
    |
    v
Resolution eligibility tool
    |
    v
Policy engine
    |
    +--> deny
    +--> allow
    +--> require customer confirmation
    +--> require human approval
    |
    v
Protected refund tool
    |
    v
Synthetic refund record
    |
    v
Audit history + customer response
```

The AI participates in understanding and explaining the situation, but the actual authorization and mutation are controlled by deterministic platform code.

That is a central Serviq design principle.

---

# Part X — Why we care about permissions so early

## 36. Different users must see different things

Serviq will eventually have several categories of people:

- end customer;
- support agent;
- support manager;
- knowledge manager;
- AI configuration manager;
- tenant administrator;
- tenant owner;
- Serviq platform operator.

These people should not all have the same access.

For example:

A support agent may need to see a customer conversation but should not necessarily be able to replace the company’s AI provider API key.

A customer may view their own order but must not view another customer’s order.

A tenant administrator should not view another tenant’s private records.

A Serviq platform operator may need platform health information that no normal client user should receive.

This is why we separate application surfaces and why the architecture already defines roles and permissions even before the visible features are built.

---

# Part XI — What is currently real and what is only planned

## 37. Already created in the repository

At this stage, the actual implementation includes the project/tooling foundation and the three frontend application shells.

The following concepts are already represented in code/configuration:

- pnpm monorepo workspace;
- Node environment definition;
- Git ignore rules;
- editor formatting rules;
- Client Console application shell;
- Customer Web application shell;
- Platform Console application shell;
- strict TypeScript configuration;
- Next.js App Router foundations;
- lint configuration;
- Tailwind/PostCSS setup;
- minimal layouts and placeholder pages;
- product decision records for the first reference demo.

---

## 38. Not implemented yet

The existence of an application folder does **not** mean the corresponding product is finished.

We have not yet implemented the major runtime systems, including:

- authentication;
- tenant creation;
- role-based permissions;
- databases;
- customer/order/delivery synthetic data services;
- real support chat;
- AI model routing;
- RAG knowledge ingestion;
- retrieval;
- agent state machine;
- policy engine;
- confirmation and approval flows;
- human support inbox;
- analytics;
- audit UI;
- observability stack;
- CI/CD pipeline;
- Docker local environment;
- production cloud infrastructure.

Those are future tickets.

This distinction is important because the project documentation should never imply that a capability exists merely because its architectural place has been designed.

---

# Part XII — Testing status

## 39. What has and has not been verified

The configuration and source files have been created according to the ticket contracts.

However, we do not claim commands such as lint, type checking, or production build have passed unless they are actually executed in an environment with the required dependencies installed.

For the frontend scaffold tickets, the required validation includes commands equivalent to:

```text
pnpm --filter @serviq/client-console lint
pnpm --filter @serviq/client-console typecheck
pnpm --filter @serviq/client-console build

pnpm --filter @serviq/customer-web lint
pnpm --filter @serviq/customer-web typecheck
pnpm --filter @serviq/customer-web build

pnpm --filter @serviq/platform-console lint
pnpm --filter @serviq/platform-console typecheck
pnpm --filter @serviq/platform-console build
```

A ticket should only be moved to Done after its required checks genuinely pass.

This is important for credibility. A production project must distinguish between “code was written” and “code was verified.”

OPE-251 is different from the frontend scaffold tickets: it is a product/architecture decision ticket, so its validation is documentation/contract consistency rather than runtime lint/build tests. Its final verification checks that the PRD, Product Specification, Architecture, CCR-003, GitHub issue, and Linear ticket all describe the same reference domains, source policy, tools, synthetic-data boundary, and non-affiliation rule.

---

# Part XIII — What these first tickets improved

## 40. Before this work

The repository mainly contained product and architecture documentation.

We knew what Serviq should become, but there was not yet a stable executable project structure for developers to extend.

---

## 41. After this work

We now have a clear starting structure.

### Product clarity improved

The first reference demo now has a concrete customer-support story rather than an abstract AI example.

### Code organization improved

The repository now has one consistent workspace model instead of allowing each future app to choose its own structure.

### Security boundaries improved

Customer-facing, tenant-facing, and platform-operator interfaces are physically separated from the beginning.

### Maintainability improved

Strict TypeScript, lint rules, common workspace commands, formatting rules, and small commits make future work easier to review and debug.

### Scalability of development improved

Multiple developers or agents can eventually work on different Serviq surfaces without all editing one giant application.

### Future feature work became safer

Authentication, AI, data, policies, and integrations now have known application locations to connect to instead of forcing those future tickets to redesign the repository first.

---

# Part XIV — What comes next

## 42. Immediate engineering direction

The next foundation work will gradually turn these empty shells into a functioning platform.

A sensible progression is:

```text
Project foundation
    |
    v
Local development environment
    |
    v
Backend/API foundation
    |
    v
Database + migrations
    |
    v
Authentication + tenants + permissions
    |
    v
Synthetic demo data
    |
    v
Knowledge ingestion + retrieval
    |
    v
LLM gateway
    |
    v
Agent runtime
    |
    v
Tools + policy engine
    |
    v
Customer chat
    |
    v
Human support console
    |
    v
Analytics + audit + observability
    |
    v
Load testing + production hardening
```

This is intentionally incremental. We want every layer to be testable before placing more complexity on top of it.

---

# Part XV — A short glossary

## API

A defined way for two pieces of software to communicate.

Example: Customer Web sends a message to the Serviq backend through an API.

## Backend

The part of the application that runs server-side business logic, talks to databases, applies permissions, and communicates with external systems.

## Frontend

The part of the product a person interacts with in a browser or app.

## RAG

Retrieval-Augmented Generation. Instead of asking an AI model to answer only from memory, the system first retrieves relevant approved information and gives that information to the model when preparing the answer.

## LLM

Large Language Model. The AI model that understands and generates language.

## Tool call

A structured request from the AI workflow to a controlled software function, such as looking up an order or requesting a refund.

## Policy engine

Software that decides whether an action is allowed, denied, requires customer confirmation, or requires human approval.

## Synthetic data

Artificially generated data that behaves like real business data but does not belong to real people or companies.

## Tenant

One business organization using Serviq. A multi-tenant system can safely serve many independent companies on one platform.

## Monorepo

One Git repository that contains several related applications and packages.

## Branch

A separate line of Git development used to work on a change without immediately altering the main branch.

## Commit

A saved checkpoint in Git describing a particular code change.

## Linting

Automated checks for suspicious or inconsistent source-code patterns.

## Type checking

Automated checking that data is being used in ways compatible with its declared types.

## Idempotency

Protection that allows the system to recognize repeated requests so an important action — such as a refund — is not accidentally executed twice.

## Audit log

A historical record explaining important actions: who or what initiated them, what decision was made, and what happened.

---

# Part XVI — How this document is maintained

## 43. One document, continuously updated

This file replaces the idea of keeping separate long-form GitHub explanation documents such as:

```text
OPE-251.md
OPE-252.md
OPE-253.md
...
```

Those ticket IDs still matter for project management and Git history, but the educational explanation belongs here.

After each completed ticket we will update this same document with:

1. what new capability or foundation was added;
2. what changed in the codebase;
3. how the new code works in plain language;
4. why the implementation was chosen;
5. what problem it solves;
6. what it improves;
7. security/privacy implications;
8. how it connects to the rest of Serviq;
9. what was tested;
10. what is still not implemented.

The goal is that someone can start at the top of this document months from now and understand how Serviq grew from an empty repository into the full product without needing to read hundreds of Git commits first.

---

# Build-history snapshot

## OPE-251 — Demo domain decision

**What changed:** the Production V1 reference configuration is frozen as a DoorDash customer-support/delivery reference domain combined with a separate Stripe payment/refund reference domain, with synthetic private operational data and three protected demo tool contracts. PR #8 merged the decision history/CCR records; PR #9 synchronized the PRD, Product Specification, and Architecture and removed the MAS-7 demo-domain Product Decision blockers.

**Why:** this gives Serviq a realistic end-to-end support story covering knowledge, customer context, delivery, payments, policy, actions, approval, and escalation without using real private company/customer data or real money movement.

**How it is kept safe:** DoorDash and Stripe are independent reference domains; Serviq does not claim DoorDash uses Stripe. Public knowledge is explicit-allowlist only and must respect source access/terms. All private operational records are synthetic. `demo.create_refund` changes only synthetic Serviq state in deterministic V1.

**Validation:** authoritative product and architecture documents now agree on `doordash-stripe-allowlist-v1`, `demo.get_delivery_order_status`, `demo.check_order_resolution_eligibility`, `demo.create_refund`, the synthetic record families, source-access restrictions, and the non-affiliation boundary. The unrelated end-customer attachment question remains intentionally open.

**Status:** **Completed.** OPE-251 is ready to close after PR #9 merges and the GitHub/Linear tracking records are marked completed.

## OPE-252 — Root monorepo toolchain

**What changed:** Serviq now has the root files that make the repository behave like one organized JavaScript/TypeScript workspace: `package.json`, `pnpm-workspace.yaml`, `.nvmrc`, `.gitignore`, and `.editorconfig`. PR #10 merged exactly those five foundation files into `main`.

**Why:** without these shared rules, each frontend application could choose different package-management, Node, folder, formatting, and ignore conventions. The root toolchain gives later tickets one predictable foundation while deliberately leaving Python services outside the JavaScript workspace.

**Validation completed:** the root JSON and YAML syntax were checked, workspace globs were verified as exactly `apps/*` and `packages/*`, `.env` and common secret/generated/local-runtime files were verified as ignored, and the Node/editor settings were manually checked. No application scaffold, backend service, Docker configuration, or CI workflow was added by OPE-252.

**Status:** **Completed.** PR #10 is merged, GitHub issue #3 is closed, and Linear OPE-252 is Done.

## OPE-253 — Client Console scaffold

**What changed:** the tenant/business-facing Serviq Client Console now has its own working Next.js application shell at `apps/client-console`. The app uses the App Router, React, strict TypeScript, Tailwind CSS, and app-local `dev`, `build`, `lint`, and `typecheck` commands. The visible root page intentionally remains minimal and identifies the product as **Serviq Client Console** with a **Foundation scaffold** note. PR #11 merged this scaffold into `main`.

**Why:** Serviq needs a dedicated web application for the employees of a business using the platform. Those users will eventually configure AI providers, knowledge, tools, policies, conversations, human-support workflows, analytics, team access, and settings. Keeping this application separate from the public Customer Web app and the privileged Serviq Platform Console creates clearer product and security boundaries from the beginning.

**How it works in plain language:** Next.js provides the web-application structure, React provides the reusable interface building blocks, strict TypeScript catches many incorrect data assumptions before the application runs, Tailwind provides the styling pipeline, and ESLint checks for common code-quality problems. At this stage the page does not call an API, use authentication, load customer data, or pretend later product features already exist. It is the tested frame that future Client Console screens will be built inside.

**What this improves:** future Client Console tickets no longer need to recreate frontend setup. They can add actual product features on top of one stable application boundary. The separate app also reduces the risk of accidentally mixing business-admin code with public customer code or platform-operator code.

**Validation completed:** after PR #11 was already merged, a temporary validation-only GitHub Actions PR (#14) tested the current `main` code using Node.js 24.18.0 and pnpm 10. Dependency installation succeeded. `pnpm --filter @serviq/client-console lint` passed, `pnpm --filter @serviq/client-console typecheck` passed, and `pnpm --filter @serviq/client-console build` passed. The workflow then started the Client Console development server and fetched the root page, confirming that the rendered HTML contains both `Serviq` and `Client Console` and no standard Next.js application-error marker. The temporary validation workflow was removed and PR #14 was closed without merging, so no validation-only workflow was added to `main`.

**Scope intentionally not added:** OPE-253 does not add authentication, navigation, API calls, charts, real customer data, AI configuration screens, conversation screens, support-inbox logic, or a component library. Those remain separate future tickets.

**Status:** **Completed.** The scaffold is merged through PR #11 and all required lint, typecheck, production-build, and root-page render checks passed. GitHub issue #4 and Linear OPE-253 can be closed as completed.

## OPE-254 — Customer Web scaffold

**What changed:** Serviq now has a dedicated end-customer web application at `apps/customer-web`. It is a Next.js App Router application using React, strict TypeScript, Tailwind CSS, ESLint, and app-local `dev`, `build`, `lint`, and `typecheck` commands. The root page intentionally stays simple and identifies the surface as **Serviq Customer Support**. PR #12 merged the scaffold. During final browser QA, the first validation run found one severe browser-console entry: the browser requested a favicon that did not exist and received a 404. PR #17 added a tiny app-local Serviq icon so the scaffold has a clean browser load without introducing any customer feature logic.

**Why:** the public support experience has a very different audience and security model from the internal Client Console. Customers will eventually ask questions, receive answers, confirm actions, and request human help here. Keeping that experience in its own application reduces the chance of accidentally mixing employee/admin code with public customer code and allows future customer work to optimize independently for mobile, accessibility, streaming, and embeddability.

**How it works in plain language:** Next.js provides the web-application frame, React provides reusable screen components, strict TypeScript catches many incorrect assumptions before runtime, Tailwind provides the styling pipeline, and ESLint checks common code-quality problems. At this stage the app has no database, no AI call, no authentication, and no business action. It is the tested shell those later capabilities will plug into.

**What this improves:** future customer-channel tickets can work on conversation behavior instead of rebuilding frontend setup. The separate package also creates a clearer public trust boundary and gives CI/deployment tooling one exact package name: `@serviq/customer-web`.

**Validation completed:** temporary validation PR #16 tested the current merged implementation on Node.js 24.18.0 with pnpm 10.15.0. Dependency installation succeeded. `pnpm --filter @serviq/customer-web lint`, `typecheck`, and `build` all passed. The production build was then opened in headless Chrome at 1280x800 and 375x812. The expected Customer Support content rendered at both widths and no severe browser-console errors remained after PR #17 added the app icon. The validation-only PR was closed without merge and its branch was reset to `main`, so the temporary workflow was not added to the product codebase.

**Scope intentionally not added:** OPE-254 does not add chat UI, customer authentication, tenant routing, SSE/streaming, customer identity, API calls, order/refund logic, or the shared design system. Those remain future tickets.

**Status:** **Completed.** PRs #12 and #17 are merged, GitHub issue #5 is closed as completed, all required automated checks and browser QA passed, and Linear OPE-254 is Done.

## OPE-255 — Platform Console scaffold

**What changed:** Serviq now has a dedicated platform-operator application at `apps/platform-console`. It uses the same Next.js App Router, React, strict TypeScript, Tailwind CSS, and ESLint foundation as the other web surfaces, but it is a physically separate package named `@serviq/platform-console`. PR #13 merged the scaffold, and PR #18 added the minimal app-local Serviq icon used during clean browser QA.

**Why:** the people operating Serviq itself will eventually see capabilities that ordinary customers and tenant employees must never receive, such as global service health, provider health, queue lag, failed jobs, incident information, feature flags, abuse controls, global rate limits, and cross-tenant operational diagnostics. Creating this separate application before those features exist gives the privileged surface its own security and deployment boundary from the beginning.

**How it works in plain language:** the current Platform Console is intentionally only the frame of a control room, not the control room itself. Next.js organizes the application, React will provide reusable operator-interface pieces, strict TypeScript catches many invalid data assumptions early, Tailwind prepares styling, and ESLint checks source quality. There is no fake operator login or fake green health dashboard because those would imply security and monitoring capabilities that have not yet been implemented.

**What this improves:** future platform-operations tickets have one clearly owned application instead of adding privileged routes to the tenant-facing Client Console. This lowers accidental exposure risk and makes later operator authentication, authorization, auditing, and network restrictions easier to review independently.

**Validation completed:** temporary validation PR #16 tested the merged Platform Console using Node.js 24.18.0 and pnpm 10.15.0. `pnpm --filter @serviq/platform-console lint`, `typecheck`, and `build` all passed. The production build was then opened in headless Chrome at 1280x800 and 375x812. The expected Platform Console content rendered at both widths with no severe browser-console errors. The validation workflow was temporary and was not merged into `main`.

**Scope intentionally not added:** OPE-255 does not add platform-operator authentication, navigation, tenant lookup, real system-health data, provider-health APIs, queue/job controls, feature flags, rate-limit editing, incident management, cross-tenant access, or backend API calls.

**Status:** **Completed.** PRs #13 and #18 are merged, GitHub issue #6 is closed as completed, all required automated checks and browser QA passed, and Linear OPE-255 is Done.

## OPE-256 — Shared UI package skeleton

**Status:** **Completed.** PR #26 is merged into `main`, GitHub issue #20 is closed as completed, and Linear OPE-256 is Done.

**What changed on the implementation branch:** `packages/ui` now exists as the proposed `@serviq/ui` shared frontend package. It contains a private ESM manifest, strict TypeScript configuration, an intentionally empty component export surface, documented neutral design-token placeholders, and an ownership README.

**Why this matters:** three Serviq web applications need one future design-system home. The package prevents duplicated visual primitives without pretending this scaffold has already designed buttons, dialogs, tables, Storybook, dark mode, or final branding.

**What this improves:** later UI tickets can add reviewed shared primitives instead of copying components between apps. Semantic token names can be shared while final brand values remain changeable.

**Validation completed:** GitHub Actions run `31695466527` used Node.js 24.18.0 and pnpm 10.15.0. Dependency installation, `@serviq/ui` typecheck, build validation, workspace resolution, and the no-application-import check passed. Final consolidation run `31717466336` again passed the shared TypeScript package checks on the fully merged OPE-256 through OPE-265 codebase.

**Not implemented:** no reusable component API, feature UI, app source change, backend code, Storybook, dark mode, or final brand system.

**Tracking:** GitHub issue #20 is closed as completed; PR #26 is merged; Linear OPE-256 is Done.

## OPE-257 — Shared contracts package skeleton

**Status:** **Completed.** PR #27 is merged into `main`, GitHub issue #21 is closed as completed, and Linear OPE-257 is Done.

**What changed on the implementation branch:** `packages/contracts` now exists as the proposed `@serviq/contracts` package. It contains strict TypeScript configuration and only architecture-frozen baseline wire shapes: `{ data, meta? }`, the standard error envelope, pagination `{ page, pageSize, total, totalPages }`, and a named string correlation identifier. Empty auth/event folders reserve ownership without inventing feature contracts.

**Why this matters:** frontend apps must not independently invent API casing, optionality, or error shapes.

**What this improves:** shared wire vocabulary has one reviewable source while future feature contracts remain architect-controlled.

**Validation completed:** GitHub Actions run `31695492522` passed strict typecheck, build validation, workspace resolution, compile examples, and the no-application-import check on Node.js 24.18.0 / pnpm 10.15.0. Conflict-resolution run `31697565128` then verified the merged lockfile state. Final consolidation run `31717466336` again passed the shared TypeScript package checks.

**Not implemented:** no database models, generated client, provider SDK types, auth implementation, or feature endpoint types.

**Tracking:** GitHub issue #21 is closed as completed; PR #27 is merged; Linear OPE-257 is Done.

## OPE-258 — Cross-cutting shared package boundaries

**Status:** **Completed.** PR #28 is merged into `main`, GitHub issue #22 is closed as completed, and Linear OPE-258 is Done.

**What changed:** Serviq now has four explicit shared workspace boundaries: `@serviq/config`, `@serviq/observability`, `@serviq/security`, and `@serviq/testkit`. Each package has its own manifest, strict TypeScript configuration, intentionally empty public index, and ownership README. The packages create safe homes for future reusable configuration, telemetry, security, and test helpers without implementing those behaviors prematurely.

**Why this matters:** these are cross-cutting concerns. Without dedicated package boundaries, future code could become duplicated or scattered across applications. Creating the boundaries now makes later ownership clearer while avoiding speculative logging, authentication, environment parsing, cryptography, fixtures, or fake-AI implementations.

**What this improves:** later tickets can add reviewed reusable helpers in one predictable location. Application code remains separated from shared infrastructure concerns, and the package ownership rules reduce accidental coupling between `apps/*` and cross-cutting libraries.

**Validation completed:** original GitHub Actions run `31695529867` passed typechecks for all four packages, verified workspace-name resolution, and confirmed no application imports on Node.js 24.18.0 with pnpm 10.15.0. After OPE-256 and OPE-257 merged, PR #28 developed a `pnpm-lock.yaml` conflict. Conflict-resolution run `31698137990` merged current `main`, preserved the already-merged `packages/ui` and `packages/contracts` lockfile importers, regenerated the combined lockfile, re-ran all four OPE-258 package typechecks, verified all six shared package importers, and re-confirmed that the four OPE-258 packages do not import application code. Every step passed.

**Conflict fix:** the lockfile was regenerated from the current merged workspace rather than choosing one side of the conflict. This preserved both the already-merged UI/contracts packages and the four new OPE-258 packages. The temporary conflict-resolution workflow was removed before merge, so OPE-258 introduced no permanent GitHub workflow.

**Scope intentionally not added:** no OpenTelemetry/logging implementation, environment parser, authentication/authorization helper, validation helper, cryptography, fixtures, fake LLM, business test data, application source change, backend behavior, Docker change, or permanent workflow.

## OPE-259 — FastAPI API service scaffold

**Status:** **Completed.** PR #25 is merged into `main`, GitHub issue #23 is closed as completed, and Linear OPE-259 is Done.

**What changed on the implementation branch:** `services/api` now contains the proposed Python 3.14 FastAPI foundation. `app/main.py` exposes only `FastAPI(title="Serviq API")`. Architecture-owned core placeholders exist for config, errors, logging, auth, tenancy, idempotency, and rate limits; modules/contracts boundaries, Ruff, strict mypy, pytest, a smoke test, and `uv.lock` are included.

**Dependency result:** Python 3.14 resolved successfully with FastAPI 0.140.13 and compatible Pydantic 2.x, SQLAlchemy 2.x, Alembic, Uvicorn, and dev tooling. No frozen dependency was silently downgraded.

**Why this matters:** every V1 REST module needs one predictable ASGI service root and common tooling before database/auth/feature work begins.

**What this improves:** future backend tickets can add router → service → repository modules on a tested service foundation.

**Validation completed:** GitHub Actions run `31695430241` installed Python 3.14.6, resolved/synced dependencies, passed Ruff, strict mypy, pytest, direct app import, and Uvicorn startup; `/openapi.json` was fetched successfully during smoke QA. Final consolidation run `31717466336` re-ran dependency sync, Ruff, strict mypy, pytest, and direct app import successfully on the merged codebase.

**Not implemented:** no database, migration, model, auth/OIDC behavior, tenancy enforcement, idempotency/rate-limit implementation, logging config, health endpoint, or business route.

**Tracking:** GitHub issue #23 is closed as completed; PR #25 is merged; Linear OPE-259 is Done.

## OPE-260 — Durable worker service scaffold

**Status:** **Completed.** PR #29 is merged into `main`, GitHub issue #24 is closed as completed, and Linear OPE-260 is Done.

**What changed on the implementation branch:** `services/worker` now contains the proposed durable-worker boundary using Python 3.14 tooling but no FastAPI dependency. It includes an executable/importable entry point, explicit `app/jobs`, `app/consumers`, and `app/core` boundaries, config placeholder, smoke test, and `uv.lock`.

**Why this matters:** ingestion, projections, webhooks, reconciliation, retention, notifications, and event consumers must eventually survive API-process restarts rather than becoming FastAPI in-process tasks.

**What this improves:** Serviq gets a separately testable process boundary for future durable work, with jobs and broker consumers conceptually separated from the start.

**Validation completed:** GitHub Actions run `31695783384` used Python 3.14.6 and passed dependency sync, Ruff, strict mypy, pytest, import, process start/exit, and a source check confirming no FastAPI, `APIRouter`, or `Request` imports. Final consolidation run `31717466336` again passed the worker dependency sync, Ruff, strict mypy, pytest, import, and no-FastAPI-import check.

**Not implemented:** no Kafka/Redpanda client, real consumer/job, database, scheduler, retry policy, outbox publisher, external integration, or web route.

**Dependency resolution:** OPE-259 was merged before final completion, and OPE-260 is now merged into `main` through PR #29.

**Tracking:** GitHub issue #24 is closed as completed; PR #29 is merged; Linear OPE-260 is Done.

## OPE-261 — LLM gateway service scaffold

### What we are building

Serviq needs one service that sits between the rest of the platform and external large-language-model providers. That service is `services/llm-gateway`.

A simple analogy is a travel adapter. An appliance should not be rebuilt for every wall-socket standard. In the same way, the Serviq API, worker, and future agent runtime should not each contain separate knowledge of every AI provider. They should eventually communicate through one Serviq-owned gateway, while provider-specific translation remains behind that boundary.

### What changed

The branch `ope-261-llm-gateway-scaffold` now contains a Python 3.14 project definition, a minimal FastAPI application, and separate package boundaries for schemas, adapters, and routing. The application currently exposes only the service identity `Serviq LLM Gateway`. A smoke test verifies that the application object can be imported and has the expected title.

The commits were deliberately small: project tooling, application package, adapter boundary, routing boundary, schema boundary, FastAPI entry point, and smoke test were added separately. This lets a reviewer understand the construction sequence instead of reviewing one large unexplained change.

### Why we did it this way

The empty packages are intentional. Future provider request/response models belong under the Serviq-owned schema boundary. Provider-specific translations belong under adapters. Model selection and fallback belong under routing. Keeping those responsibilities separated now makes later changes easier to test and reduces the chance that provider SDK details spread through unrelated services.

### What this improves

Later OpenAI, Anthropic, Gemini, OpenRouter, or other provider work gets a known home without tying the whole product to one provider. It also gives us a service that can eventually be scaled, observed, rate-limited, and failed over independently from the main API.

### What is intentionally not implemented

There is no provider adapter, provider SDK, API-key loading, model routing, fallback policy, streaming, usage accounting, cost policy, retry policy, circuit breaker, or actual LLM request. Those are separate contracts and future tickets.

### Validation and completion status

PR #37 is merged. Final GitHub Actions run `31717466336` used Python 3.14.6, resolved the LLM-gateway dependencies, passed Ruff, strict mypy, pytest, direct app import, the provider-SDK dependency/import guard, and a real Uvicorn startup plus `/openapi.json` smoke check. GitHub issue #32 is closed as completed and Linear OPE-261 is Done. **Status: Completed.**

## OPE-262 — Local PostgreSQL 18 with pgvector

### What we are building

PostgreSQL is the local authoritative relational database foundation for Serviq. “Authoritative” means that durable business facts will eventually live there rather than in a temporary cache. pgvector adds vector data types and similarity-search support inside PostgreSQL, which gives later knowledge-retrieval work a practical V1 vector-search path without immediately adding another database product.

### What changed

The branch `ope-262-postgres-pgvector-compose` creates the local Docker Compose foundation. It defines a pinned PostgreSQL 18-compatible pgvector image, binds the local database port to the developer machine, adds a named data volume, and adds a `pg_isready` healthcheck. A tiny initialization file enables the PostgreSQL `vector` extension on a new local database. A development environment template documents the local database variables and clearly separates local defaults from future production configuration.

### Why the vector extension is separate from Serviq tables

Enabling a database capability is not the same as designing the product database. This ticket does not create organizations, users, conversations, policies, orders, audit records, or any other Serviq table. Those tables need migrations, constraints, indexes, tenant isolation, and security review in their own tickets.

### What this improves

Future backend work receives one reproducible local database target. Later RAG and retrieval work can begin with PostgreSQL plus pgvector, keeping the V1 operational footprint smaller until measured scale proves that a separate vector/search product is necessary.

### What is intentionally not implemented

There are no Serviq tables, Alembic migrations, row-level-security rules, tenant queries, backups, replicas, cloud database settings, application database connections, or production credentials.

### Validation and completion status

PR #38 is merged. Final GitHub Actions run `31717466336` passed `docker compose config`, started PostgreSQL, verified the container healthcheck, confirmed PostgreSQL 18 and the `vector` extension, created a temporary row, restarted PostgreSQL, verified the row persisted, and removed the temporary table. GitHub issue #33 is closed as completed and Linear OPE-262 is Done. **Status: Completed.**

## OPE-263 — Local Valkey cache

### What we are building

Valkey is Serviq's local fast, temporary key/value store. The easiest way to understand the difference between PostgreSQL and Valkey is to imagine a filing cabinet and a whiteboard. PostgreSQL is the filing cabinet for records the business cannot afford to lose. Valkey is the whiteboard for information that is useful to access quickly but can be reconstructed if the whiteboard is erased.

Future examples may include short-lived rate counters, provider-health state, hot configuration, or cache metadata.

### What changed

The branch `ope-263-valkey-compose` is stacked on OPE-262 because both tickets extend the same Compose file. It adds a pinned Valkey 8.1 service, local port exposure, a readiness check based on the Valkey command-line client, and infrastructure documentation that explicitly describes the service as rebuildable cache rather than durable business storage.

The service does not receive a persistent data volume in this ticket. That choice reinforces the architecture rule that losing the cache must never lose a completed business mutation.

### Why no cache keys were invented

A cache key is a contract: it implies what data is cached, how long it lives, who can read it, and how it is invalidated. OPE-263 does not yet have the business features that should define those rules. Provisioning the infrastructure without speculative application behavior keeps later decisions reviewable.

### What this improves

Future tickets have a predictable low-latency local service instead of independently introducing caches. The explicit “rebuildable only” rule also prevents accidental use of Valkey as the sole record of a refund, policy update, or other durable event.

### What is intentionally not implemented

There is no session design, rate-limit middleware, semantic response cache, cache-key namespace, TTL policy, invalidation strategy, distributed lock, cluster mode, or production Valkey deployment.

### Validation and completion status

PR #39 is merged. Final GitHub Actions run `31717466336` started Valkey with the full local stack, waited for its healthcheck, and confirmed `PING` returned `PONG`. The same run verified that the surrounding PostgreSQL, object-storage, and Keycloak services remained healthy together. GitHub issue #34 is closed as completed and Linear OPE-263 is Done. **Status: Completed.**

## OPE-264 — Local S3-compatible object storage

### What we are building

Not every piece of data belongs in a relational database. Serviq will later store uploaded knowledge documents, normalized document artifacts, exports, and evaluation artifacts. Object storage is designed for those file-like objects.

The architecture requires an S3-compatible local boundary. This lets local development use a free service while future production code can target a cloud object store through the same broad storage contract.

### What changed

The branch `ope-264-object-storage-compose` is stacked on OPE-263. It adds a pinned SeaweedFS 4.41 service in its compact local mode, exposes the S3-compatible endpoint on the developer machine, persists object data in a named volume, configures a local authenticated S3 boundary through environment substitution, and sets the required local bucket target to `serviq-local-objects`.

The infrastructure README documents the Compose hostname, S3 port, bucket name, and the rule that local configuration must never be treated as production configuration.

### Why SeaweedFS is acceptable here

The Serviq architecture does not require application code to depend on a MinIO-specific API. It requires a frozen S3-compatible local implementation. Using an S3-compatible service keeps the important contract at the storage-protocol level. Later application code should talk to a Serviq object-storage adapter rather than importing vendor-specific behavior throughout the product.

### What this improves

Knowledge-ingestion and export tickets now have a defined local object-storage target. The files remain outside application source and public web roots, and a future production move to cloud S3-compatible storage does not require rewriting every feature around a local vendor.

### What is intentionally not implemented

There is no upload endpoint, presigned URL flow, MIME/type/size validation, malware scanning, generated object-key implementation, knowledge parsing, public bucket policy, cloud S3 deployment, or retention lifecycle.

### Validation and completion status

PR #40 is merged, and PR #45 added the missing object-storage healthcheck discovered during completion review. Final GitHub Actions run `31717466336` passed Compose validation, waited for object storage to become healthy, confirmed the private `serviq-local-objects` bucket, completed an authenticated write/read/delete round trip, verified anonymous access was rejected, restarted object storage, and confirmed stored data persisted. GitHub issue #35 is closed as completed and Linear OPE-264 is Done. **Status: Completed.**

## OPE-265 — Local Keycloak OIDC service

### What we are building

Keycloak is the local identity-provider foundation for future Serviq workforce authentication. An identity provider is the system that participates in proving who a user is. OIDC, or OpenID Connect, is a standard protocol that applications can use to integrate with that identity provider.

This ticket does not make the Client Console or Platform Console log in. It creates the local identity-service process that later authentication tickets can configure deliberately.

### What changed

The branch `ope-265-keycloak-compose` is based on the OPE-262 Compose foundation. It adds a pinned Keycloak 26.7.1 development service, enables Keycloak health information, exposes the local application and management interfaces only on the developer machine, requires the local bootstrap administrator password to be supplied outside Git, adds a readiness check against Keycloak's management health endpoint, and adds `infra/docker/keycloak/README.md` explaining the boundary.

The changes were committed in small steps: the container, health enablement, management interface, administrator configuration, readiness behavior, and documentation each have their own history.

### Why no Serviq realm or OIDC client exists yet

Realms, client identifiers, redirect addresses, token settings, users, and role mappings are authentication contracts. They affect security and frontend/backend behavior. Creating them inside a container-scaffold ticket would mix infrastructure setup with application-authentication design. OPE-265 deliberately stops before that line.

### What this improves

Later workforce-authentication work gets a free local standards-based identity-provider target and a clear readiness boundary. At the same time, the repository does not falsely imply that authentication is complete simply because an identity service can start.

### What is intentionally not implemented

There is no Serviq realm, OIDC client, permanent user, tenant-role mapping, platform-operator role mapping, login/logout flow, token validation, refresh logic, application authorization guard, SSO federation, or production identity deployment.

### Validation and completion status

PR #43 is merged. Final GitHub Actions run `31717466336` started the complete local stack, waited for Keycloak's container healthcheck to become healthy, successfully called the management readiness endpoint, and confirmed the local web endpoint was reachable. No Serviq realm, OIDC client, login flow, or role mapping was introduced by this infrastructure ticket. GitHub issue #36 is closed as completed and Linear OPE-265 is Done. **Status: Completed.**

## Current tracking summary

OPE-256 through OPE-265 are now completed. PRs #25 through #29 and #37 through #40/#43 are merged as applicable; OPE-264 completion hardening is merged in PR #45; GitHub issues #20, #21, #22, #23, #24, and #32 through #36 are closed as completed; and Linear OPE-256 through OPE-265 are Done. Final consolidation run `31717466336` validated the merged shared packages, API, worker, LLM gateway, PostgreSQL/pgvector, Valkey, private object storage, and Keycloak together.

---

# Build-history update — OPE-266 through OPE-271

The sections below describe the next foundation work. They also correct one important reading rule for older sections above: a statement such as “observability is not implemented yet” was true when that earlier section was written. Later ticket sections supersede historical state. The guide keeps the old explanation because it shows how Serviq evolved over time.

## OPE-266 — Optional local Redpanda event-broker profile

### What we changed

OPE-266 adds a Kafka-compatible Redpanda broker to `infra/docker/compose.yml`, but places it behind the optional Docker Compose profile named `events`. The implementation branch is `ope-266-redpanda-events-profile`.

The Redpanda image is pinned rather than using an unbounded `latest` tag. Inside the Docker network, other containers can address the broker as `redpanda:9092`. The service includes a health check using Redpanda's `rpk cluster info` command. `infra/docker/README.md` now explains the optional event-development boundary.

### What that means in normal language

Think of an event broker as a durable message conveyor belt between software systems. One system can place a message on the belt and another system can process it independently. That becomes useful when Serviq later performs background ingestion, projections, notifications, reconciliation, and other work that should not be tied to one web request.

The key word here is **optional**. A developer working only on a frontend page or normal database code should not need to run an event broker. Redpanda therefore does not start as part of the ordinary Compose profile.

### Why we did this

The worker service already reserves a future consumer boundary. Adding a local Kafka-compatible broker gives later event tickets a concrete development target without prematurely inventing Serviq event payloads or topics.

Keeping the broker optional also reduces local CPU and memory usage for developers who do not need it.

### What this improves

- Later event-driven work gets one predictable local broker endpoint.
- The normal development stack remains smaller when event work is not needed.
- Broker infrastructure is separated from business event design.
- No later feature needs to quietly introduce its own incompatible local message broker.

### What is intentionally not implemented

OPE-266 does **not** create Serviq topics, producers, consumers, event schemas, schema-registry configuration, retry/dead-letter behavior, application event logic, or production broker configuration.

### Validation and tracking status

The Compose YAML and service structure were inspected successfully, including the optional profile, pinned image, internal listener, and healthcheck. No core service depends on Redpanda.

A real Docker broker-health and topic-list test has **not** yet been completed in this work session because the available execution environment does not have Docker, and the attempted temporary GitHub Actions validation workflow was blocked by the repository write-safety layer. For that reason OPE-266 remains **In Progress**, not Done.

The implementation is pushed in micro-level commits. GitHub issue #47 tracks the work, and PR #53 is open.

## OPE-267 — Optional local observability profile

### What we changed

OPE-267 creates `infra/docker/observability/` and adds five optional local services under the Compose profile `observability`:

- OpenTelemetry Collector — receives telemetry and forwards it to the appropriate local backend;
- Prometheus — stores and queries metrics;
- Grafana — provides a user interface for exploring telemetry;
- Loki — stores and queries logs;
- Tempo — stores and queries distributed traces.

The implementation also adds configuration files for the collector, Prometheus, Loki, Tempo, and Grafana data-source provisioning. Grafana is pre-wired to the local Prometheus, Loki, and Tempo services. Prometheus is configured to scrape itself and the collector. Loki is given the explicit local tenant identifier `serviq-local` through the collector and Grafana data-source configuration.

### What that means in normal language

Imagine a complicated machine in a factory. When it fails, a mechanic needs more than a red light saying “broken.” The mechanic wants measurements, a history of what happened, and a way to follow a request through multiple parts of the machine.

Observability provides those clues:

- **metrics** answer questions such as “How many requests are happening?”;
- **logs** record structured events and errors;
- **traces** follow one operation across services;
- **Grafana** is the screen used to inspect that information.

The OpenTelemetry Collector acts like a telemetry post office. Applications will eventually send telemetry there, and the collector will route it to the correct local storage system.

### Why we did this

Production-grade software cannot rely on developers manually reproducing every problem. Serviq will eventually need evidence about latency, failures, provider health, queue behavior, background work, and request flow.

Adding the local infrastructure boundary now gives later instrumentation tickets a known destination without pretending instrumentation already exists.

### What this improves

- Telemetry backends have one reproducible local home.
- The stack is optional, so normal development does not always pay its resource cost.
- Grafana data sources are provisioned rather than requiring repeated manual clicking.
- Future application instrumentation can target standard OpenTelemetry protocols instead of hard-coding every backend throughout the codebase.

### What is intentionally not implemented

There is no Serviq application instrumentation yet, no product-specific dashboard, no production monitoring account, no alerting policy, no incident automation, and no claim that business requests are already producing useful traces, logs, or metrics.

### Validation and tracking status

The configuration files and Compose boundaries are pushed, and no application code was changed. A full runtime check — starting all five services, confirming Grafana health/data sources, and confirming Prometheus target health — is still required before OPE-267 can be called complete. The current execution environment cannot run Docker.

The branch is `ope-267-observability-profile`, GitHub issue #48 tracks it, and stacked PR #54 is open. Linear OPE-267 remains **In Progress**.

## OPE-268 — Root developer Makefile

### What we changed

OPE-268 adds a root `Makefile` that gives contributors one consistent command surface across the JavaScript/TypeScript workspace, the three Python services, and local Docker infrastructure.

The required targets are:

```text
make setup
make dev
make test
make lint
make typecheck
make security
make e2e
make load-test
make down
```

`setup` uses the existing pnpm lockfile and each Python service's uv lockfile. `lint`, `typecheck`, and `test` delegate to the real repository commands. `dev` starts the core Compose dependencies and prints the separate commands used to start the applications/services. `down` tears down the Compose project.

The three future gates — `security`, `e2e`, and `load-test` — deliberately return a non-zero result instead of printing a fake green success.

### What that means in normal language

Before this file, a new contributor had to know several different package managers and remember which directory to enter for each command. The Makefile is a front desk: the contributor asks for “test” or “typecheck,” and the front desk delegates that request to the correct tools.

It does not replace pnpm, uv, pytest, Ruff, mypy, or Docker. It gives them one predictable entrance.

### Why the unimplemented commands fail on purpose

A placeholder command that exits successfully is dangerous. CI could say “security passed” even when no security scanner ran.

Returning a failure is more truthful. It prevents a future reviewer from accidentally treating an empty command as evidence that a real quality gate exists.

### What this improves

- Local development and CI can use the same high-level commands.
- New contributors need fewer repository-specific commands to memorize.
- Quality checks become easier to automate consistently.
- Missing security/E2E/load-test systems are visible rather than hidden.

### Validation and tracking status

The Makefile was parsed with dry-run execution, and the three placeholder gates were executed to confirm they return non-zero instead of fake success. Full dependency/install/test execution is expected to be exercised by CI rather than claimed from an environment that lacks the complete runtime toolchain.

The branch is `ope-268-root-makefile`, GitHub issue #49 tracks it, and stacked PR #55 is open. Linear OPE-268 remains **In Progress** until the stacked work is integrated and required checks are complete.

## OPE-269 — Baseline CI workflow

### What we changed

OPE-269 adds `.github/workflows/ci.yml` on branch `ope-269-baseline-ci`. The workflow currently:

- uses read-only repository-content permission;
- checks out the code;
- configures pnpm 10.15.0;
- reads Node.js from `.nvmrc`;
- configures Python 3.14.6;
- configures uv caching;
- runs `make setup`;
- runs `make lint`;
- runs `make typecheck`;
- runs `make test`;
- separately validates the Docker Compose model;
- limits the job to 20 minutes.

### Why CI matters

CI means Continuous Integration. In plain language, it is a neutral computer that checks the repository after a change instead of trusting that a developer's laptop happened to work.

That matters because “it worked on my machine” is not enough evidence for a production project. CI makes the repository repeat the same quality checks in a clean environment.

### Important incomplete requirement

The ticket requires CI on both pull requests and pushes to `main`. The current pushed workflow triggers on pull requests only.

An attempted change to add the `push`-to-`main` trigger was blocked by the GitHub write-safety layer available in this session. Attempts to create the pull request for this workflow-modifying branch were also blocked. Therefore there is no successful GitHub Actions run for this workflow yet.

This is deliberately documented instead of hidden. OPE-269 is **not complete** and must not be marked Done until the missing trigger exists and a real workflow run passes.

### What this improves already

The pushed branch provides the baseline quality-gate design and connects CI to the root Makefile. Once the blocked trigger/PR step is resolved, pull requests can receive one repeatable repository-wide lint/typecheck/test result instead of manually running unrelated commands.

### What is intentionally not implemented

This baseline CI does not add security scanning, browser E2E testing, load testing, image publishing, deployment, releases, production secrets, or cloud credentials.

### Tracking status

GitHub issue #50 tracks OPE-269. The branch is pushed, but no PR was created because that repository workflow write was blocked. Linear OPE-269 remains **In Progress**.

## OPE-270 — Post-scaffold repository audit and `repo_context.md`

### What we changed

OPE-270 adds one file only: `docs/repo_context.md`.

That file is an evidence-based map of the repository after the initial scaffolding work. It records exact paths, actual dependency/tooling versions, the real folder tree, existing frontend/backend examples, current commands, testing reality, CI reality, and important missing systems.

It explicitly separates “planned architecture” from “implemented code.” For example, the architecture says backend modules should eventually follow Router → Service → Repository, but the repository does not yet contain a real business module demonstrating that pattern. The audit says so instead of pretending the pattern is already implemented.

### What that means in normal language

Imagine hiring a new intern and handing them a huge building blueprint. The blueprint tells them what the building is supposed to become, but it does not tell them which rooms are actually finished today.

`repo_context.md` is the walk-through report. It says, “This room exists, this door is only a placeholder, this system has not been installed yet, and these are the exact tools currently used.”

That is important for AI coding agents too. An agent that sees an architecture plan may otherwise invent code that does not match repository reality.

### Major facts recorded by the audit

The audit documents, among other things:

- the current Node, pnpm, Next.js, React, TypeScript, Python, and infrastructure versions;
- the real three frontend applications and six shared TypeScript package boundaries;
- the API, worker, and LLM-gateway scaffolds;
- the fact that authentication is not implemented even though local Keycloak exists;
- the fact that application database models/migrations/repositories are not implemented even though PostgreSQL, SQLAlchemy, and Alembic dependencies exist;
- the fact that there is no real Router → Service → Repository feature example yet;
- the fact that application telemetry instrumentation is not implemented;
- the fact that OPE-269 is incomplete because its push-to-main trigger and successful run are missing;
- the downstream builder start gate that requires future tickets to inspect current repository reality before coding.

### Why we did this

After a scaffold grows beyond a few folders, “remember how everything works” is not a scalable process. A factual repository context file reduces repeated rediscovery and prevents new builders from treating empty placeholder directories as completed subsystems.

### What this improves

- Future tickets start from exact current paths rather than guesses.
- AI agents receive a written boundary between implemented reality and future architecture.
- Missing contracts become explicit blockers instead of invitations to invent behavior.
- Repository conventions become reviewable and updateable.

### Validation and tracking status

The audit was produced from the actual branch tree, package manifests/lockfiles, source files, Compose configuration, and workflow state. OPE-270's branch changes exactly one file relative to its OPE-269 base.

GitHub issue #51 tracks the ticket. PR #56 is open with `ope-269-baseline-ci` as its stacked base. Linear OPE-270 remains **In Progress** while the upstream CI ticket is unresolved and the stacked PR is not merged.

## OPE-271 — Repository contribution and pull-request governance

### What we changed

OPE-271 creates four repository-governance files on branch `ope-271-repository-governance`:

- `.github/pull_request_template.md`;
- `CONTRIBUTING.md`;
- `SECURITY.md`;
- `.github/CODEOWNERS`.

The pull-request template requires a ticket reference, summary, files changed, validation, manual QA, contract-change declaration, security-review statement, `Needs Architect Decision` field, and builder done report.

`CONTRIBUTING.md` tells contributors to read the ticket and `docs/repo_context.md`, use one ticket per branch/PR, push small ticket-labelled commits, use the real root Makefile commands, avoid claiming placeholder gates have passed, follow contract-change discipline, and keep long-form implementation explanations in this cumulative guide.

`SECURITY.md` gives responsible vulnerability-reporting guidance without inventing a private email address. It instructs reporters not to expose sensitive vulnerability details publicly and to use GitHub's private reporting path when available.

`CODEOWNERS` assigns the repository to the verified existing GitHub owner `@anmolsansi`; no username was invented.

### Why we did this

Technical quality is not only about source code. A repository also needs a predictable way for people to propose, explain, test, and review changes.

Without governance files, every contributor may use a different branch style, omit validation information, hide a contract change inside a feature, or forget to state what was intentionally deferred.

These files turn those expectations into repository-visible instructions.

### What this improves

- Reviewers get a consistent pull-request checklist.
- New contributors can learn the repository workflow without relying on private team knowledge.
- Contract changes are harder to hide accidentally.
- Security impact and unresolved architecture decisions must be stated explicitly.
- Ownership is visible through a verified CODEOWNERS entry.
- The existing “one cumulative build guide” documentation rule is reinforced.

### What is intentionally not changed

OPE-271 does not configure GitHub branch-protection settings, change CI, create issue templates, define a release process, or invent a private security contact.

### Validation and tracking status

A branch comparison against OPE-270 confirms exactly four governance files and four micro-level commits. The Markdown content references repository commands that actually exist.

Attempts to create the OPE-271 pull request were blocked by the GitHub write-safety layer in this session. The branch and commits are pushed, but the ticket therefore remains **In Progress** rather than being presented as merged or complete. GitHub issue #52 tracks the work.

## Current tracking summary — OPE-266 through OPE-271

At this point the implementation work is pushed to GitHub, but these tickets are intentionally **not being reported as completed** because required runtime/CI validation and integration steps remain.

- OPE-266: branch pushed, PR #53 open; broker runtime validation pending.
- OPE-267: branch pushed, PR #54 open; full observability runtime validation pending.
- OPE-268: branch pushed, PR #55 open; Makefile dry-run/placeholder behavior verified, stacked integration pending.
- OPE-269: branch pushed; required push-to-main trigger and successful Actions run still missing; PR creation was blocked.
- OPE-270: `docs/repo_context.md` pushed; PR #56 open against the stacked OPE-269 base.
- OPE-271: four governance files pushed; PR creation was blocked by the repository write-safety layer.

This guide update is intentionally truthful about those incomplete steps. A production-grade project gains credibility by distinguishing “written and pushed” from “validated, merged, and Done.”


---

# OPE-266 through OPE-271 — validation and integration update

> **Current-status note:** this section was added after the implementation and GitHub Actions validation work described above. For OPE-266 through OPE-271, the status statements here supersede earlier “pending validation” or “PR not created” statements while preserving the earlier technical explanations as history.

## OPE-266 current result

Temporary validation PR #58 proved that the default Compose profile starts without Redpanda, the `events` profile starts the broker, `rpk cluster info` and `rpk topic list` succeed, and stopping Redpanda leaves PostgreSQL, Keycloak, Valkey, and object storage running.

PR #53 is merged into `main`. GitHub issue #47 is closed as completed and Linear OPE-266 is Done.

## OPE-267 current result

PR #54 is merged into `main`. Temporary validation PR #58 proved that the observability services are absent from the default profile and that OpenTelemetry Collector, Prometheus, Grafana, Loki, and Tempo start together under the optional `observability` profile.

OPE-267 remains In Progress because this session did not independently assert every Grafana datasource-health API result and every Prometheus target-health result listed in the ticket's manual QA. The infrastructure is merged, but partial runtime evidence is not being presented as stronger validation than actually occurred.

## OPE-268 current result

GitHub Actions exposed an important repository fact while validating the new Makefile: `services/llm-gateway` has a `pyproject.toml` but no committed `uv.lock`. The first CI run therefore failed when `make setup` tried a frozen uv sync for that service.

The Makefile was corrected to match repository reality: pnpm remains frozen, API and worker remain frozen against their committed uv lockfiles, and the LLM gateway uses normal `uv sync` until separate dependency-hardening work adds a reviewed gateway lockfile or deliberately chooses another policy.

After that correction, baseline CI passed setup, lint, typecheck, tests, and Compose-model validation. Temporary validation PR #59 also proved that `make dev` starts the core stack, `make down` stops it, and `make security`, `make e2e`, and `make load-test` return non-zero rather than creating fake green gates.

PR #55 is merged into `main`. GitHub issue #49 is closed as completed and Linear OPE-268 is Done.

## OPE-269 current result

The baseline CI workflow now has both required triggers: pull requests and pushes to `main`. It uses read-only repository-content permission, no paid-service secret, and a 20-minute timeout. GitHub Actions run `31743372387` passed the full baseline after the OPE-268 setup correction. Temporary validation PR #59 also passed baseline CI.

PR #57 is open against `main`. The final merge operation for this workflow-changing PR could not be completed through the available repository write path in this session, so OPE-269 is In Review rather than being reported as Done.

## OPE-270 current result

`docs/repo_context.md` has been refreshed after the real CI run. It now records the missing LLM-gateway lockfile as a landmine instead of incorrectly claiming that every Python service has a committed lockfile. It also records the successful baseline CI state and the runtime evidence gathered for optional infrastructure profiles.

The temporary updater workflow used to refresh the audit was removed before review, so OPE-270 changes only `docs/repo_context.md` relative to its ticket base. CI run `31743667816` passed on the final audit branch. PR #56 is open and Linear OPE-270 is In Review.

## OPE-271 current result

The governance branch contains the four intended files: `.github/pull_request_template.md`, `CONTRIBUTING.md`, `SECURITY.md`, and `.github/CODEOWNERS`. The CODEOWNERS entry uses the confirmed repository owner `@anmolsansi`; no username or private security email was invented. The contribution guide references the real Makefile commands and the audited `docs/repo_context.md`.

CI run `31743760233` passed. PR #60 is open against the OPE-270 audit branch. Linear OPE-271 is In Review until the stacked dependency chain is merged.

## Current ticket summary

- **OPE-266 — Completed.** Merged, runtime validated, GitHub issue closed, Linear Done.
- **OPE-267 — In Progress.** Implementation merged and profile startup validated; remaining datasource/target manual QA is tracked.
- **OPE-268 — Completed.** Merged, CI validated, lifecycle validated, GitHub issue closed, Linear Done.
- **OPE-269 — In Review.** Implementation and required CI validation passed; PR #57 remains open.
- **OPE-270 — In Review.** Repository audit is refreshed, CI passed, PR #56 is open.
- **OPE-271 — In Review.** Governance files are implemented, CI passed, PR #60 is open.

This status deliberately distinguishes code that is written, code that is runtime-tested, code that is merged, and a ticket that is actually Done.

---

# OPE-266 through OPE-271 — final completion reconciliation

> **Final-status note:** this section supersedes the earlier status-only notes for OPE-266 through OPE-271. The detailed “what changed / how it works / why we did it / what it improves” sections above remain the permanent technical explanation and history.

## OPE-266 final status

**Completed.** PR #53 is merged, GitHub issue #47 is closed as completed, and Linear OPE-266 is Done. Validation-only GitHub Actions run `31743262767` proved that the default Compose profile can run without Redpanda, the optional `events` profile can start the broker, `rpk cluster info` and `rpk topic list` succeed, and stopping Redpanda does not take down PostgreSQL, Keycloak, Valkey, or object storage.

This means the event broker is now a real, optional local-development capability rather than only a configuration file. It still does not create Serviq business topics, event schemas, producers, consumers, retries, or production broker architecture; those remain separate future contracts.

## OPE-267 final status

**Completed.** PR #54 is merged, GitHub issue #48 is closed as completed, and Linear OPE-267 is Done. Validation-only GitHub Actions run `31743262767` proved that the observability services are absent from the default/core profile and that OpenTelemetry Collector, Prometheus, Grafana, Loki, and Tempo start together under the optional `observability` profile.

This gives future telemetry work a reproducible local destination without forcing every developer to run the heavier monitoring stack. Application instrumentation, product dashboards, alert rules, and production observability remain intentionally out of scope.

## OPE-268 final status

**Completed.** PR #55 is merged, GitHub issue #49 is closed as completed, and Linear OPE-268 is Done. The root `Makefile` now provides the common developer command surface for setup, development infrastructure, linting, type checking, tests, teardown, and future quality gates.

Validation exposed an important repository fact: `services/llm-gateway` does not currently have a committed `uv.lock`. The final Makefile therefore uses frozen uv sync where lockfiles actually exist and normal `uv sync` for the LLM gateway instead of pretending a lockfile exists. `make security`, `make e2e`, and `make load-test` continue to fail deliberately until real implementations replace those placeholders. That prevents a fake green quality signal.

## OPE-269 final status

**Completed.** The original stacked PR #57 became stale as earlier foundation work merged, so it was replaced by PR #62 created from the then-current `main`. The final CI workflow contains both required triggers — pull requests and pushes to `main` — uses read-only repository-content permission, has a 20-minute timeout, and does not require a paid-service secret.

GitHub Actions run `31778357529` passed dependency setup, linting, type checking, tests, and Docker Compose configuration validation. PR #62 merged as `5ccfe27a878af5aa32fe049fe7632d8e04bc221d`. GitHub issue #50 is closed as completed, Linear OPE-269 is Done, and old PR #57 is closed as superseded rather than leaving two competing CI implementations.

This improves Serviq by giving every later pull request a neutral, repeatable repository-wide quality check instead of relying only on one developer's local machine.

## OPE-270 final status

**Completed.** After OPE-269 merged, the earlier stacked audit PR #56 was replaced by PR #63 built from current `main`. The final `docs/repo_context.md` records the repository as it actually exists: exact toolchain and infrastructure versions, real paths, implemented examples, missing systems, current commands, CI behavior, security/auth/database reality, known landmines, and the required downstream builder start gate.

The audit explicitly records that the LLM gateway has no committed uv lockfile, application authentication is not implemented even though local Keycloak exists, and the database infrastructure exists without an implemented application model/migration/repository convention. These are important because later builders must not invent missing contracts from architecture prose.

GitHub Actions run `31778606260` passed the full baseline CI suite. PR #63 merged as `a2b7f38926bb8bd0ae90e891c5f4bbb4b4b62783`. GitHub issue #51 is closed as completed, Linear OPE-270 is Done, and PR #56 is closed as superseded.

## OPE-271 final status

**Completed.** The stale stacked PR #60 was replaced by PR #64 on top of the completed repository audit. The final ticket intentionally used four micro-level commits so each governance concern has a separate Git history entry:

1. `.github/pull_request_template.md` — requires ticket references, summary, changed files, validation, manual QA, contract-change status, security review, architect-decision status, and builder done report;
2. `CONTRIBUTING.md` — documents one-ticket-per-branch/PR development, small commits, current root commands, contract discipline, the repository-audit start gate, and the one-cumulative-guide rule;
3. `SECURITY.md` — provides responsible vulnerability-reporting guidance without fabricating a private email address or asking reporters to expose sensitive details publicly;
4. `.github/CODEOWNERS` — assigns ownership to the verified repository owner `@anmolsansi` rather than inventing a username.

GitHub Actions run `31778818213` passed. PR #64 merged as `21448734e6f842e9c70fa4eff693bba35d345f07`. GitHub issue #52 is closed as completed, Linear OPE-271 is Done, and PR #60 is closed as superseded.

This improves the project by making the development and review process part of the repository itself. A new contributor no longer needs private knowledge to understand how a Serviq change should be scoped, tested, documented, and reviewed.

## Final batch summary

All six tickets — OPE-266, OPE-267, OPE-268, OPE-269, OPE-270, and OPE-271 — are now **Done** in Linear. Their GitHub tracking issues #47 through #52 are closed as completed, and all permanent implementation changes are merged to `main`.

Temporary validation PRs #58 and #59 remain intentionally closed without merge because their purpose was to prove runtime/developer-lifecycle behavior, not to add permanent validation-only workflows. The stale stacked PRs #57, #56, and #60 are also closed; their final current-main replacements are PRs #62, #63, and #64 respectively.

The repository now has three additional production-foundation capabilities that were not present before this batch: optional local event/observability infrastructure, a repeatable developer/CI command-and-quality path, and explicit repository audit/governance rules for every later builder ticket.

---

# OPE-304 — GitHub Releases and semantic versioning

## What we added

Before this ticket, Serviq had commits, branches, pull requests, CI, and repository governance, but it had no Git tags and no GitHub Releases. That meant the repository could explain what had merged, but it did not have a permanent named product snapshot such as “version 0.1.0.”

OPE-304 adds the missing release layer without changing any Serviq runtime API, database, authentication, event, or product contract.

The implementation adds `.github/release.yml`, which tells GitHub how to group merged pull requests when it generates release notes. Categories distinguish breaking changes, security work, features, bug fixes, performance, infrastructure, testing, dependencies, documentation, refactors, and unmatched changes. A `release:skip` label excludes a pull request from generated notes when it truly should not appear.

The implementation also adds `.github/workflows/release.yml`. This is not the same file as `.github/release.yml`: the first is executable GitHub Actions automation; the second is only changelog configuration.

The release workflow has three paths:

1. a one-time foundation bootstrap after the release system first merges to `main`;
2. an authorized manual release from the GitHub Actions UI;
3. a release created from an existing semantic-version tag.

Every publishing path is designed to fail closed. A requested version must match the approved `vMAJOR.MINOR.PATCH` format with an optional prerelease suffix. Existing release versions are never overwritten. Existing tags are never silently repointed. A tag-driven release is rejected if its commit is not contained in `main`.

## Why the version starts at v0.1.0-alpha.1

The repository has meaningful platform-foundation work, but many customer-facing production capabilities are still intentionally absent. Calling the current code `v1.0.0` would imply a stability and completeness level that has not been earned yet.

The first release is therefore designed as:

```text
v0.1.0-alpha.1
Serviq v0.1.0-alpha.1 — Platform Foundation
```

The `0` major version communicates that the product is still before the stable public contract, and the `alpha.1` suffix makes the developer-preview status explicit in both the tag and GitHub Release UI.

## Quality checks before publishing

The workflow does not create a release immediately after somebody types a version number. It first installs the repository's real dependencies and runs the existing baseline gates:

```text
make setup
make lint
make typecheck
make test
docker compose -f infra/docker/compose.yml --profile "*" config --no-interpolate
```

This reuses the same command surface contributors already use rather than creating a second hidden release-only test system.

`make security`, `make e2e`, and `make load-test` are not called yet because they are currently deliberate failing placeholders. Treating a placeholder as a successful release gate would create a false quality signal. Later tickets should add those commands to release publishing only after they contain real checks.

## Release labels and pull-request metadata

OPE-304 extends the pull-request template so every future change states its release impact. The four release-impact choices are `release:major`, `release:minor`, `release:patch`, and `release:skip`.

The release workflow creates the new repository labels idempotently using GitHub's repository-scoped automation token. It does not delete or replace the existing default GitHub labels such as `bug`, `documentation`, and `enhancement`.

The PR template also asks for a user-visible change description, upgrade/migration information, and an explicit breaking-change declaration. This makes release consequences visible during code review instead of being reconstructed weeks later when someone tries to publish a version.

## Permanent operator documentation

`docs/RELEASING.md` explains the release lifecycle in plain language. It documents Semantic Versioning, the relationship between tickets/PRs/tags/releases, manual release steps, tag-driven release behavior, prerelease rules, post-release verification, and what the release process still intentionally does not automate.

`CONTRIBUTING.md` now links those release rules directly into the normal contributor workflow, and `docs/repo_context.md` records the new convention for later builders because repository reality changed after the OPE-270 audit.

## Security and integrity decisions

The release workflow does not require a personal access token, provider API key, or paid service. It uses GitHub's short-lived repository-scoped `GITHUB_TOKEN` and grants write permission only to the jobs that actually publish releases or create labels.

Release input is validated before it is used as a version. Values are quoted in shell commands. Published versions are treated as immutable by repository policy even before GitHub's stronger repository-level immutable-release setting is enabled.

Repository-level immutable releases are intentionally deferred until the release process has been exercised and future artifact/signing behavior is defined. The current policy already forbids moving a published tag or replacing different code under the same version; a correction must receive a new version.

## What this improves

Serviq now gains a permanent answer to “what exact code is version X?” A prospective client or contributor can use the Releases page instead of reading dozens of commits to understand meaningful product snapshots. Release notes are tied back to merged pull requests, while every release is associated with one exact tested commit.

The release system also creates a clean future path for Docker images, SBOMs, signed artifacts, provenance, deployments, and hotfix policies without prematurely implementing those systems today.

## Intentionally deferred

OPE-304 does not deploy production environments, publish containers to GHCR, generate SBOMs, sign artifacts, create attestations, infer the next version automatically, create release/hotfix branches, or declare Serviq `v1.0.0` production-ready.

Those capabilities have different security and operational consequences and should be implemented through separate tickets after their requirements are explicit.

## Completion gate

The code/documentation portion of OPE-304 is complete only when the implementation PR passes baseline CI and merges to `main`. The ticket itself remains open until the post-merge Release workflow successfully creates `v0.1.0-alpha.1`, the release/tag are verified to point at the intended merged commit, and the release is visibly marked as a prerelease.

## OPE-304 final verified result

**Completed.** The release-system implementation merged through PR #67 into `main` at commit `46a02b53ea9e3340c90d3aa8c5291f7dd15edf07`.

Baseline CI run `31832353639` completed successfully on that exact `main` commit. The new Release workflow then ran as `31832353708`. Its `bootstrap-foundation-release` job successfully completed dependency setup, linting, type checking, tests, Docker Compose configuration validation, release-label creation, and the first release publication.

GitHub now contains the tag `v0.1.0-alpha.1`, and that tag points exactly to `46a02b53ea9e3340c90d3aa8c5291f7dd15edf07`. The corresponding GitHub Release is named `Serviq v0.1.0-alpha.1 — Platform Foundation`, is published rather than draft, and is explicitly marked as a prerelease. The release notes state that this is an alpha developer preview and not a production-ready customer release.

The repository release labels now exist alongside the original GitHub default labels: `release:major`, `release:minor`, `release:patch`, `release:skip`, `breaking-change`, `feature`, `fix`, `security`, `infrastructure`, `testing`, `dependencies`, `refactor`, and `performance`.

PR #67 was subsequently labelled `release:minor` and `infrastructure` so its repository metadata matches the release policy introduced by the ticket. The first generated release notes necessarily include the repository's historical merged pull requests under the catch-all category because those older pull requests predate the release-label convention. Future releases will become more structured as new pull requests use the new labels before merge.

The first release tag is intentionally left pointing to the OPE-304 implementation merge commit. Later documentation-only reconciliation commits do not move or rewrite that published tag; this demonstrates the repository policy that published versions are permanent history.

OPE-304 therefore established and exercised the complete first release loop: reviewed code -> green PR CI -> merge to `main` -> green `main` CI -> release quality gates -> immutable-by-policy semantic tag -> published GitHub prerelease -> verification.



## OPE-272 — Baseline repository security scanning

### What we changed

Serviq now has a dedicated security workflow at `.github/workflows/security.yml`. Think of it as four independent security inspectors that automatically examine every pull request and every change merged to `main`. One inspector looks for risky code patterns, one looks for accidentally committed passwords or API keys, one checks the repository and infrastructure configuration for known high-severity problems, and one checks third-party software dependencies for publicly known vulnerabilities.

The four gates are intentionally separate so a new contributor can tell *what kind* of problem failed instead of seeing one vague “security failed” result. CodeQL scans both the JavaScript/TypeScript and Python code. Gitleaks checks the complete Git history and current tree for secret-like material. Trivy scans the filesystem and configuration for HIGH and CRITICAL vulnerabilities or misconfigurations. The dependency job runs `pnpm audit` for production JavaScript dependencies and `pip-audit` against the frozen API and worker Python lockfiles.

### Why we did it this way

Serviq is designed to eventually handle customer information, organization credentials, uploaded documents, webhook data, LLM requests, and tenant-specific configuration. A security mistake becomes harder and more expensive to fix after many features depend on it. Adding automatic checks at the foundation stage means future code is examined before it reaches `main`.

The workflow does not use `continue-on-error` for required findings. In ordinary language, that means a serious finding cannot be quietly ignored while GitHub still shows a green check. Scanner setup/network failures also fail the relevant job rather than pretending the repository was scanned successfully.

### Supply-chain and permission safety

The workflow pins the checkout, CodeQL, Gitleaks, Trivy, Node setup, and uv setup actions to exact commit SHAs. This prevents an upstream moving tag from silently changing the code Serviq executes in CI. The workflow is read-only by default. Only the CodeQL job receives `security-events: write`, because that job must upload analysis results to GitHub code scanning. No tenant provider key or paid security service is required.

The local `make security` command is no longer a fake failing placeholder. It runs the dependency-audit portion locally and explicitly tells the developer that CodeQL, Gitleaks, and Trivy are enforced by GitHub Actions. This keeps local setup lightweight while preserving the full repository gate in CI.

### What this improves

Before OPE-272, a pull request could pass the normal lint/type/test workflow even if it accidentally contained a credential, introduced a known vulnerable dependency, or added a serious infrastructure misconfiguration. After OPE-272, those failure classes have dedicated automated checks. This does not make Serviq “secure by default” or replace human security review; it creates a repeatable baseline that future tickets can build on.

### Validation and intentional limits

The ticket is considered complete only after the new Security workflow runs on the pull request and all four categories report understandable results. The implementation deliberately does not add container-image scanning because Serviq does not yet publish product container images, and it does not add penetration testing, runtime WAF/security controls, or custom Semgrep rules. Those are different layers of security and belong to later work.


## OPE-273 — Typed platform configuration and safe environment template

### What we changed

Serviq now has a real, typed configuration boundary instead of empty placeholder files. The API reads the architecture-owned platform environment variables through `services/api/app/core/config.py`, and the worker mirrors the same contract through its already-approved `services/worker/app/core/config.py` boundary. A root `.env.example` shows every platform variable with local-only placeholder values so a new developer can see which knobs exist without receiving any real credential.

The configuration model covers the environment name, public and API URLs, PostgreSQL, Valkey, Kafka bootstrap servers, object storage, OIDC identity-provider settings, the server-side session secret, the internal LLM gateway connection, OpenTelemetry export, logging level, and the local webhook allowlist. Tenant-owned provider keys such as an OpenAI API key are intentionally *not* part of this environment model. Those future credentials belong to tenant-scoped BYOK storage, not to a process-wide `.env` file.

### How the code works

`load_settings()` receives either the real process environment or an explicit mapping supplied by a test. It copies only the exact variable names frozen in Architecture v1.3 and asks Pydantic to validate their types. HTTP endpoints must really look like HTTP URLs; database, Valkey, and telemetry endpoints must parse as URLs; `SERVIQ_ENV` can only be `local`, `test`, `staging`, or `production`; `LOG_LEVEL` is restricted to the supported logging levels; and non-empty string fields cannot silently become blank configuration.

Secrets use Pydantic's `SecretStr`, which masks them when represented. Serviq adds another protection around validation: `SettingsError` reports only the *names of bad fields*. It deliberately does not copy Pydantic's raw input values into startup errors. This matters because startup logs are often retained centrally, and a badly configured secret must never become a secret leaked into logs.

Production mode has an additional preflight check. Object-storage credentials, the OIDC client secret, `SESSION_SECRET`, and `LLM_GATEWAY_INTERNAL_TOKEN` must be non-empty. There is no insecure production fallback. Local development still uses explicit placeholders from `.env.example`, which makes it obvious that those values must be replaced outside local development.

`SERVIQ_LOCAL_WEBHOOK_ALLOWLIST` stays a comma-separated environment value at the boundary and exposes a trimmed tuple to application code. This keeps the external environment contract simple while avoiding repeated string parsing elsewhere.

### Why the API and worker have local copies

Serviq does not yet have an architect-approved shared Python package across backend services. Creating one just to remove a small amount of duplication would quietly introduce a new cross-service ownership contract. Instead, this ticket keeps the same frozen variable names and validation behavior inside the two configuration paths that already existed. The LLM gateway is not given a new configuration directory in this ticket because that path did not exist and no new shared ownership path was approved. A future architecture ticket can extract common Python configuration only when that package boundary is deliberately designed.

### What `.env.example` is and is not

`.env.example` is a map, not a vault. It contains safe strings such as `local-placeholder` and local service URLs. A developer can copy it to the Git-ignored `.env` file and replace values for their machine. Real production credentials must never be written into the example, committed to Git, or returned to a browser. The repository's OPE-272 Gitleaks gate now adds another automated layer against accidental secret commits.

### What this improves

Before OPE-273, later database, authentication, storage, telemetry, and LLM-gateway tickets could each have invented their own environment names or scattered `os.getenv()` calls throughout business code. That creates subtle differences such as one service expecting `DB_URL` while another expects `DATABASE_URL`. The typed boundary makes configuration a single explicit contract per service, gives failures understandable field names, and gives tests a deterministic way to inject configuration without mutating the developer's machine.

### Tests and security checks

API tests cover a valid local environment, an unsupported environment name, a malformed URL, a production secret that is missing, and confirmation that tenant provider keys are not modeled. Worker tests independently cover valid loading, environment validation, URL validation, and production-secret redaction. The worker dependency lock is refreshed after adding Pydantic so frozen installs remain reproducible. Final completion additionally requires the normal CI workflow and the OPE-272 Security workflow to pass on the pull request.

### Intentional limits

This ticket does not create a database connection, log a user in through OIDC, encrypt secrets, connect to AWS Secrets Manager, load tenant BYOK credentials, or change provider contracts. It defines and validates the platform configuration boundary those future implementations can safely consume.


## OPE-274 — Public README and verified local setup

### Why this ticket mattered

Before OPE-274 the first thing a visitor saw in the public GitHub repository was only `# Serviq`. That title did not explain what the product is, what actually works today, how to run the repository, or which ambitious goals are still future targets. For a public engineering project, a vague README is not just a documentation problem: it makes reviewers guess whether the code is unfinished, whether setup instructions exist somewhere else, and whether performance claims are real.

OPE-274 turns the root `README.md` into a truthful front door for the project while keeping the detailed technical truth in the existing architecture, repository-context, and cumulative build documents.

### What changed

The README now introduces Serviq as an Enterprise AI Customer Operations Platform and immediately states its current development status. It distinguishes the *product direction* from the *code that already exists*. The current repository is described as having product/architecture foundations, three web-app scaffolds, Python service boundaries, local infrastructure, CI/security gates, and typed platform configuration. It also explicitly says the full end-to-end customer-operations product is not production-ready yet.

A repository map explains the purpose of the three applications, three Python services, TypeScript packages, Docker infrastructure, and documentation. The README then links directly to the PRD, product specification, architecture, technology stack, repository context, cumulative Serviq Build Guide, and design references. This means a new intern can start with a short overview and move into deeper documents without guessing which file is authoritative.

### How local setup is explained

The setup section uses the versions and commands that the repository actually owns. It tells contributors to use Node 24.18.0 from `.nvmrc`, pnpm 10.15.0, Python 3.14.x, uv, Docker Compose v2, and Make. The installation sequence is `git clone`, `cd`, copy `.env.example` to the ignored `.env`, enable the pinned pnpm version, and run `make setup`.

Local Docker infrastructure is described separately from application processes. `make dev` starts the default infrastructure—PostgreSQL/pgvector, Keycloak, Valkey, and S3-compatible object storage—and prints the commands for application processes. Keycloak intentionally has no known fallback bootstrap password, so the README shows a local-only `KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD` export before `make dev` instead of hiding that requirement.

The optional `events` profile is documented for Redpanda. The optional `observability` profile is documented for the OpenTelemetry Collector, Prometheus, Grafana, Loki, and Tempo. The README also shows how to activate all profiles and how `make down` cleans up the stack. A branch-only validation job rendered the default, events, observability, and all-profile Compose configurations with a validation-only Keycloak password so these commands were checked against the real Compose file rather than copied from memory.

### What the application commands mean

The README lists the exact current commands for the Client Console, Customer Web, Platform Console, API, Worker, and LLM Gateway. Directly below them it explains an important limitation: successfully starting a scaffold does not mean authentication, tenant workflows, RAG, order/refund tools, human handoff, analytics, or the complete AI-support flow is implemented. This prevents a common portfolio mistake where a running placeholder screen is described as a completed product.

### Validation commands and deliberate failures

`make lint`, `make typecheck`, `make test`, and `make security` are presented as the working validation surface. The README explains that the local security command performs dependency audits while pull requests also run CodeQL, Gitleaks, Trivy, and dependency scanning.

`make e2e` and `make load-test` are documented differently: they are clearly labeled *planned, not implemented yet*. Those Makefile targets intentionally fail today. Showing that fact is better than omitting the commands or making a placeholder command return success, because a green placeholder could falsely imply that end-to-end or load testing exists.

### Scale wording

The README preserves Serviq's large-scale ambition without converting it into a fake benchmark. It says 10 million concurrent connections/users is a long-term architecture target and explicitly says the repository has not achieved that benchmark. It also explains that registered users, connected clients, active request throughput, and LLM request rate are different metrics. Future scale claims must be tied to reproducible load tests and a defined workload.

### Demo and non-affiliation wording

The README records the existing demo-domain decision precisely: DoorDash is a reference support/delivery domain, while Stripe is a separate reference payment-provider domain. It does not claim DoorDash uses Stripe. It also states that these references do not imply affiliation, sponsorship, endorsement, or an existing integration, and that demo private/business records are synthetic unless a source is explicitly public and permitted.

### Security and contribution expectations

A short security note tells contributors not to commit credentials, provider keys, customer PII, private business data, or production secrets. It reinforces the OPE-273 boundary that tenant/provider BYOK credentials are not global environment variables. The README also avoids inventing a contribution or production-support promise: it says a formal external contribution and release/deployment support policy has not yet been published.

### What this improves

OPE-274 makes a fresh clone understandable without requiring the reader to inspect dozens of files. More importantly, it creates a public truthfulness boundary: visitors can distinguish current scaffolding from future product behavior, working commands from planned test commands, and architecture targets from measured performance. That makes the repository more useful to developers, reviewers, prospective clients, and future maintainers without overselling unfinished work.

### Validation

The temporary branch-only finalizer checked every relative Markdown link in the README, checked the required production-readiness/scale/non-affiliation/planned-test wording, and rendered all documented Docker Compose profile combinations. The normal CI and Security workflows remain the final merge gates. The temporary finalizer itself is removed before merge so no ticket-specific workflow is left behind.


## OPE-275 — SQLAlchemy sessions and Alembic persistence foundation

### What problem this solves

Until OPE-275, Serviq knew that PostgreSQL and SQLAlchemy would be used, but the API did not have a real database connection pattern. That sounds like a small missing piece, but it is a major architectural boundary: if one feature creates a synchronous SQLAlchemy session, another creates an asynchronous session, and a third opens raw database connections, later transactions, tests, migrations, and connection handling become inconsistent. OPE-275 establishes one route into PostgreSQL before product tables are created.

### Architect decision before coding

The ticket explicitly required an architect decision because the repository had not frozen sync versus async SQLAlchemy. `docs/architecture-decisions/ADR-001-api-database-session-model.md` now records that decision before the persistence implementation: the FastAPI service uses SQLAlchemy 2 asynchronous sessions with Psycopg 3. `services/api/app/core/database.py` owns the engine/session boundary, `services/api/app/models/base.py` owns one declarative metadata root, and `services/api/alembic/` owns schema migrations. Application repositories must not create a second synchronous engine/session pattern.

This choice fits the asynchronous FastAPI service and keeps database I/O from introducing a separate blocking persistence style. Psycopg 3 also supports the project's Python 3.14/PostgreSQL 18 development targets and can be selected by SQLAlchemy's async PostgreSQL dialect.

### How `DATABASE_URL` becomes a database engine

OPE-273 froze the external variable name `DATABASE_URL`. OPE-275 does not rename it or require developers to know SQLAlchemy driver syntax. The database adapter accepts the normal `postgresql://...` form and converts only the internal SQLAlchemy scheme to `postgresql+psycopg://...`. It also accepts an already explicit Psycopg URL. Any non-PostgreSQL scheme is rejected with the safe message `DATABASE_URL must use the PostgreSQL scheme`; the rejected URL and its password are not copied into that error.

`create_database_engine()` creates an `AsyncEngine` with `pool_pre_ping=True`. The pre-ping lets SQLAlchemy check a pooled connection before handing it back to application work, reducing the chance that an old/stale connection is reused after PostgreSQL or the network has interrupted it. OPE-275 deliberately does not choose production pool sizes yet because those values should be based on deployment capacity and measured workload rather than guesses.

### One session factory

`create_database_session_factory()` creates the approved `async_sessionmaker`. Sessions use `expire_on_commit=False` and `autoflush=False`, making commits and flush points explicit for future service/repository code. The process-wide engine and session factory are lazy and cached: importing the API does not immediately require a database connection or load every environment value, but the first database consumer receives the same engine/factory rather than inventing a new one.

`get_database_session()` is the request/work-unit boundary. It opens one `AsyncSession` using an async context manager and guarantees that the session is closed when the caller finishes. It does not automatically commit business changes. Future services must decide when a transaction should commit or roll back, which prevents a generic infrastructure helper from silently deciding business semantics.

`dispose_database_engine()` exists for controlled shutdown/tests. It disposes the cached engine and clears the factories so a new controlled environment can create a fresh connection boundary.

### The model metadata root

`services/api/app/models/base.py` contains one SQLAlchemy `DeclarativeBase`. No customer, tenant, role, invitation, order, or other product model is created in this ticket. The purpose of the base is to give all future models one metadata registry and to give Alembic one place to read schema metadata. That prevents later modules from creating independent model bases that Alembic cannot see together.

### Alembic setup

`services/api/alembic.ini` and `services/api/alembic/env.py` make Alembic the required schema-change mechanism. The environment uses the same typed `DATABASE_URL`, adapts it through the same database helper, imports the same `Base.metadata`, and runs migrations through an async SQLAlchemy engine with a temporary `NullPool`. In simple terms: application connections and migration connections use the same database technology and URL contract, but migrations do not keep a long-lived application-style pool.

The first revision, `20260814_0001_database_baseline.py`, is intentionally empty. Upgrading it proves that Alembic can track a Serviq schema version; it does not create a Serviq product table. Downgrading it is equally empty and reversible. This is useful because OPE-277 and later tickets can now depend on a known migration head instead of combining infrastructure setup with the first business schema.

### Real PostgreSQL test instead of SQLite

The normal unit/quality job still runs without requiring a local database. The database integration test is skipped there unless `SERVIQ_DATABASE_INTEGRATION=1`. CI now has a separate `database-integration` job that launches the same PostgreSQL 18 + pgvector image family used by local Compose, loads safe test platform settings, installs the frozen API environment, runs `alembic upgrade head`, executes a real `SELECT 1` through the async session factory, inspects the public schema, and confirms that there are no product tables beyond Alembic's own version bookkeeping. It then runs `alembic downgrade base`.

This separation matters. SQLite is excellent for many projects, but it would not prove PostgreSQL-specific migration behavior, PostgreSQL connection-driver behavior, or later PostgreSQL constraints. Serviq's persistence integration path therefore tests the database it is actually designed to run.

### Dependency and reproducibility changes

The API already depended on SQLAlchemy and Alembic. OPE-275 adds `psycopg[binary]>=3.3,<4` as the PostgreSQL driver and refreshes `services/api/uv.lock`, so CI and developer installs use a frozen compatible dependency graph. The binary package keeps development/CI setup self-contained; deployment packaging can be revisited later without changing the SQLAlchemy/Psycopg application contract.

### What this improves

After OPE-275, every upcoming repository and migration has a defined answer to five questions: which engine style is used, where sessions come from, which metadata base owns models, how schema changes are applied, and how PostgreSQL behavior is tested. Establishing those answers now removes a large class of accidental divergence before tenant/RBAC/invitation tables arrive.

### What is intentionally not built

OPE-275 creates no Serviq domain table, no repository classes, no RLS policy, no seed data, no connection-pool tuning, no read replica routing, and no auth or API behavior. The only database table Alembic may create for bookkeeping is `alembic_version`. Product schema work begins in later tickets.

### Validation required before completion

The branch must pass normal lint, mypy/type checking, unit tests, the Security workflow, and the permanent real-PostgreSQL integration job. The integration job must successfully upgrade to migration head, connect/query through the approved async session factory, confirm no product tables were introduced, and downgrade to base. The temporary OPE-275 finalizer is removed before merge.
