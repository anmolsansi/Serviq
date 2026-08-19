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

**Status:** **Completed.** PR #10 is merged, GitHub issue #3 is closed as completed, and Linear OPE-252 is Done.

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


## OPE-272 — Baseline repository security scanning

### What problem this ticket solves

Before OPE-272, Serviq's root `make security` command was intentionally a failing placeholder. That was better than a fake green result, but it meant the repository still had no permanent automated check for common security mistakes. A developer could accidentally commit a secret, introduce a known-vulnerable dependency, or add a dangerous configuration pattern without a dedicated repository security workflow noticing it.

OPE-272 turns that placeholder into a real baseline. It is not a guarantee that the product is secure; no automated scanner can provide that guarantee. It creates repeatable guardrails so several common classes of mistake are checked on every pull request and on `main`.

### What is scanned

The permanent workflow is `.github/workflows/security.yml`. It has separate jobs so one tool failing does not hide the results of the others.

**CodeQL** analyzes the JavaScript/TypeScript and Python source trees. Its job is to identify source-code patterns associated with known vulnerability classes. It checks code, not business logic, so it complements rather than replaces normal review and tests.

**Gitleaks** scans the repository history and current tree for values that look like credentials, tokens, or private keys. This matters because adding a secret and then deleting it in a later commit does not erase it from Git history. The configuration keeps a deliberately small allowlist for fixture hashes and local placeholder secrets that are clearly marked as non-production values.

**Trivy** scans the repository filesystem for vulnerable dependencies and risky configuration. The workflow uses its filesystem scan for HIGH and CRITICAL vulnerability/configuration findings.

**Dependency audits** run against the actual package managers used by the repository. The JavaScript workspace uses `pnpm audit --prod --audit-level=high`. Each Python service is exported from uv using its locked/resolved dependency graph and pip-audit checks the resulting requirement list. That gives the API, worker, and LLM gateway independent Python dependency checks instead of auditing only one service.

### `make security` is now real

The Makefile no longer fails unconditionally. `make security` now runs the local dependency-audit surface: the pnpm production audit plus pip-audit for the three Python services. The heavier source/secret/configuration scanners stay in GitHub Actions, where they run in one neutral environment and produce repository Security results.

This split is intentional. Developers get a useful local command without requiring every scanner binary to be installed manually, while pull requests still receive the stronger automated workflow.

### Security tooling and false positives

Security scanners sometimes identify test fixtures, example hashes, or development-only placeholders as if they were real secrets. The answer is not to disable scanning. OPE-272 added `.gitleaks.toml` with a minimal allowlist for values that are known fake fixtures and local-only placeholders. The allowlist is deliberately narrow so a future real credential does not get hidden behind a broad exemption.

### Workflow permissions and secrets

The Security workflow uses `contents: read` and `security-events: write`, which is the minimum useful permission pattern for source checkout plus CodeQL reporting. It does not receive cloud credentials, provider API keys, OIDC client secrets, database passwords, or any paid-service key. All tests/scans must work without a production secret.

### What this improves

Before this ticket, security depended mainly on careful human behavior and whatever quality checks happened to run locally. After this ticket, source code, Git history, configuration, and dependency vulnerability checks are explicit repository gates. That makes accidental secret commits and several common vulnerable-dependency/source patterns easier to catch before merge.

It also gives future security tickets a known baseline to extend. Later work can add specialized policies for containers, IaC, DAST, SAST tuning, SBOMs, signatures, or deployment security without rebuilding the fundamental repository security workflow first.

### Validation completed

The implementation was validated through real GitHub Actions rather than being marked complete from configuration inspection alone. The final branch passed CodeQL for JavaScript/TypeScript and Python, Gitleaks, Trivy, pnpm audit, and pip-audit for the API, worker, and LLM gateway. `make security` was also wired to the real dependency-audit commands.

### What is intentionally not added

OPE-272 does not add production runtime security controls, secrets-manager configuration, WAF rules, DAST against a deployed environment, container signing, SBOM publishing, branch-protection administration, compliance controls, penetration testing, or incident response automation. It establishes the repository scanning baseline only.


## OPE-273 — Typed platform configuration and safe environment example

### What problem this ticket solves

Serviq already had a mix of configuration placeholders: API and worker config files were empty shells, Docker Compose contained some local defaults, and the repository did not have one safe `.env.example` showing every platform-level variable. That can become dangerous as a project grows. If code reads environment variables directly in many places, names drift, startup errors become confusing, secret values can leak into logs, and production may silently use unsafe defaults.

OPE-273 creates one typed configuration boundary in each existing Python service that needs it today: the API and worker. It also creates the repository-root `.env.example` required by the architecture. Provider/BYOK credentials are deliberately excluded because those are tenant-owned secrets and must use the later encrypted tenant secret-store path instead of global environment variables.

### What changed in the API and worker

Both services now depend on Pydantic Settings. Each service exposes a typed `Settings` object and a cached `load_settings()` function. Code that needs configuration should receive/use that object instead of scattering `os.getenv(...)` across business modules.

The required platform variables are represented as typed fields: environment name, public/API URLs, PostgreSQL, Valkey, Kafka, object storage endpoint/bucket/access credentials, OIDC issuer/client configuration, session secret, LLM Gateway URL/internal token, OTLP endpoint, log level, and the local webhook allowlist.

URL-shaped values use Pydantic URL validation. Empty strings are not accepted. Unknown environment values are rejected. Optional local/staging variables remain optional only where the architecture allows them.

### Safe error behavior

Configuration errors can accidentally expose credentials if the program prints the entire invalid input. The new config layer uses a custom Pydantic error renderer that includes the failing field name and validation reason while intentionally hiding `input_value` and `input_type` details. Tests place fake secrets inside invalid settings and assert those secret strings never appear in the returned error text or object representation.

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


## OPE-276 — Database-backed API readiness health check

### What this ticket adds

OPE-276 gives Serviq two infrastructure health endpoints with deliberately different meanings. `GET /health/live` answers only “is this API process alive?” while `GET /health/ready` answers “is this API process currently able to reach PostgreSQL and therefore safe to receive work that depends on the database?” Those questions must stay separate. A process can still be running even when PostgreSQL is stopped, overloaded, restarting, or unreachable.

The readiness contract is intentionally tiny. When PostgreSQL answers, the API returns HTTP 200 with exactly `{"status":"ready"}`. When PostgreSQL cannot be reached, raises an error, or takes too long, the API returns HTTP 503 with exactly `{"status":"not_ready","dependency":"database"}`. The public response never contains a database URL, hostname, username, password, SQL text, driver exception, or stack trace.

### Architect decision before adding the route

The repository had architecture text for `/health/live` and `/health/ready`, but there was no implemented health router or completed feature-module pattern. Rather than silently inventing a location, OPE-276 records `ADR-002-api-health-module-boundary.md`. The decision puts HTTP behavior in `services/api/app/modules/health/router.py`, dependency orchestration in `services/api/app/modules/health/service.py`, the low-level SQL ping in the existing `services/api/app/core/database.py` boundary, and leaves `services/api/app/main.py` responsible only for composing the router into FastAPI.

Health routes deliberately live at `/health/*`, not `/api/v1/*`, because they are infrastructure probes rather than customer/business REST resources. The ADR also freezes an important rule: liveness can never gain a database dependency by accident.

### What happens during readiness

`ping_database()` reuses the single asynchronous SQLAlchemy engine established in OPE-275. It opens a connection and executes only `SELECT 1`. This query does not inspect a Serviq table, read customer data, run a migration, or mutate anything. Its purpose is simply to prove that the API can connect to PostgreSQL and receive a valid response.

`database_is_ready()` wraps that ping in Python's async timeout mechanism with a frozen budget of 2.0 seconds. If the ping finishes normally, it returns `True`. If the timeout expires, it returns `False`. If database/config/driver code raises any dependency failure, it also returns `False`. The service intentionally normalizes those failures instead of allowing a raw SQLAlchemy or Psycopg exception to cross into the HTTP layer.

The route then translates only that boolean into the frozen 200 or 503 response. This separation is useful because the public API contract never needs to know what kind of internal database exception occurred. Operators get a stable signal, and implementation details remain private.

### Why the broad dependency failure catch is deliberate

A readiness endpoint has a different job from a business endpoint. Its job is not to diagnose a PostgreSQL exception for an end user; its job is to say whether this process should receive traffic. A configuration error, unavailable host, refused connection, driver error, or unexpected database-layer exception all mean the same thing to readiness: this instance is not ready. For that reason, the health service catches the dependency failure boundary broadly and emits only the stable event `database_readiness_failed`. Timeouts emit `database_readiness_timeout`.

The caught exception object is not attached to these warning logs. That is a security choice. Database exceptions can include server names, ports, SQL, or connection details. The repository's full structured-observability implementation is still future work, so ADR-002 allows a named Python logger now but freezes the rule that raw database details must not be logged from readiness.

### Liveness stays independent

`GET /health/live` does not call `database_is_ready()` or `ping_database()`. It returns HTTP 200 with `{"status":"live"}` based on the process being capable of serving the route. This matters for container/orchestrator behavior: if PostgreSQL is temporarily down, Serviq should be marked not-ready for traffic, but an orchestrator should not necessarily conclude that the API process itself is dead and continuously restart it.

### Tests added

`services/api/tests/test_health.py` covers the exact public contracts and the failure safety boundary. It proves that healthy readiness returns exactly the 200 body, an unavailable dependency returns exactly the 503 body, timeout logic cancels a deliberately slow ping, the production timeout constant remains exactly two seconds, fake connection credentials/host/SQL embedded in an exception never appear in captured health logs, and liveness does not call database readiness at all.

HTTP contract tests use FastAPI's test client, so OPE-276 adds `httpx` only to the API development dependency group and refreshes the frozen `services/api/uv.lock`. It is not a production runtime dependency.

The existing permanent PostgreSQL CI job is also widened from one individual integration-test file to the whole `tests/integration` directory. A new real-database test calls `/health/ready` against the PostgreSQL 18 + pgvector service used in CI and requires the real 200 readiness contract. This means the endpoint is not considered complete merely because a mock says the database is healthy.

### What this improves

Before OPE-276, infrastructure could know only that a FastAPI process existed. It could not distinguish “the API is alive and can use PostgreSQL” from “the API process is alive but its critical database is unavailable.” After OPE-276, future Docker/Kubernetes/load-balancer configuration can use liveness and readiness for their correct separate purposes. The endpoint also gives developers a very small diagnostic surface when starting the local stack.

### What is intentionally not part of readiness yet

Only PostgreSQL is checked. Valkey, Kafka/Redpanda, object storage, OIDC, the LLM gateway, model providers, webhooks, and other downstream integrations are not added to readiness by this ticket. Adding every dependency to one probe can make a service unnecessarily unavailable, so each future dependency should be considered deliberately. OPE-276 also does not alter migrations, connection-pool sizing, authentication, tenant behavior, product tables, Kubernetes manifests, probe intervals, or alerting.

### Validation required before completion

The final pull request must pass normal repository lint, mypy/type checks, unit tests, Compose validation, the real PostgreSQL integration job, and the OPE-272 Security workflow. The branch-specific finalizer exists only to refresh the API lock and append this cumulative documentation; it is removed before merge.


## OPE-277 — Tenant, workforce, and RBAC database schema

### What this ticket builds

OPE-277 is the first Serviq migration that creates real product-domain tables. It creates the database foundation for organizations, workforce identities, organization membership, roles, permissions, and role assignments. The six tables are `tenants`, `users`, `memberships`, `roles`, `role_permissions`, and `membership_roles`. They are created by Alembic revision `20260814_0002`, directly after the empty OPE-275 persistence baseline.

A useful way to understand the model is to separate a *person* from a *person's membership in an organization*. `users` stores the workforce identity recognized through OIDC. `tenants` stores Serviq customer organizations. `memberships` joins a user to a tenant and gives that relationship its own status. A user can therefore exist once in Serviq and later belong to one or more tenants without duplicating the user's identity record.

`roles` describes named access roles. A role may belong to one tenant or may be global when `tenant_id` is null. `role_permissions` lists the permission keys attached to each role. `membership_roles` assigns roles to a particular membership. This avoids storing comma-separated permissions or hard-coding access logic inside a user row.

### Why CCR-004 was required before coding

The architecture says `memberships.created_by_invitation_id` eventually references `organization_invitations(id)` with `ON DELETE SET NULL`. However, OPE-277 is explicitly forbidden from creating invitation tables; those belong to OPE-278. PostgreSQL cannot create a foreign key to a table that does not exist. Trying to follow both instructions literally in one migration would therefore make the migration invalid.

The issue was handled as a contract-sequencing decision instead of being hidden in code. `CCR-004-invitation-foreign-key-migration-sequencing.md` records that OPE-277 creates the nullable `created_by_invitation_id` column now, while OPE-278 creates `organization_invitations` and then adds the final foreign key in that later migration. The Architecture document now carries the same note. The final schema contract is not weakened or renamed; only the order in which PostgreSQL can safely reach that final schema is clarified.

OPE-277 still creates an index on `created_by_invitation_id`. That prepares the column for its final foreign-key role and follows the architecture's broader rule that foreign-key columns are indexed. No invitation API or business logic can write the field in this ticket.

### Shared primary-key and timestamp rules

All six tables follow Serviq's database conventions. Their primary key is a PostgreSQL UUID with `DEFAULT uuidv7()`, so the database creates identifiers when an insert does not supply one. Each mutable table also gets `created_at` and `updated_at` as non-null timezone-aware timestamps defaulting to `now()`. These shared columns come from small migration helper functions so the six table definitions do not accidentally drift from one another.

### `tenants`

A tenant is one organization using Serviq. Its `slug` is required, unique, and restricted to 3–63 characters. `display_name` is required and 1–120 characters. `status` can only be `active`, `suspended`, or `deleted`. `default_locale` defaults to `en`. The migration creates the unique slug constraint and a status index.

These checks happen in PostgreSQL itself. Even if a future API bug tries to insert a tenant with an invalid status or short slug, the database still refuses the invalid state. This is intentional defense in depth: UI/API validation improves user feedback, but database constraints protect the stored truth.

### `users`

A workforce user stores `oidc_issuer`, `oidc_subject`, `email`, `display_name`, and an `active|disabled` status. The pair `(oidc_issuer, oidc_subject)` is unique. OIDC subjects are only meaningful in the context of their issuer, so this pair prevents one external identity from being represented twice while allowing different identity providers to use the same subject string. Email receives an index for later lookup but is not treated as the immutable identity key.

### `memberships`

A membership links one tenant and one user. Both foreign keys use `ON DELETE RESTRICT`, which prevents a tenant or user from being deleted while a membership still depends on it. Membership status is limited to `active|suspended`, and `(tenant_id, user_id)` is unique so the same user cannot receive duplicate membership rows in one tenant.

Indexes support tenant/status queries, user membership lookup, and the future invitation-origin foreign key. As described by CCR-004, the invitation-origin column is present and nullable but its foreign-key constraint is deliberately deferred until OPE-278 creates the referenced table.

### `roles` and the important NULL uniqueness rule

A role has an optional `tenant_id`, a 2–64 character `key`, a 1–80 character `display_name`, and `is_system`, which defaults to false. Tenant-owned roles reference `tenants` with `ON DELETE RESTRICT`.

The uniqueness rule is not an ordinary `(tenant_id, key)` unique constraint. Serviq requires PostgreSQL's `UNIQUE NULLS NOT DISTINCT (tenant_id, key)`. Normally SQL treats two NULL values as different for uniqueness, which could allow multiple global roles with the same key because their `tenant_id` is NULL. `NULLS NOT DISTINCT` changes that behavior so only one global role with a given key can exist while still allowing the same role key in different tenants. The integration tests verify both the actual PostgreSQL constraint definition and a duplicate global-role rejection.

### `role_permissions`

Each row attaches a 2–120 character permission key to a role. The role foreign key uses `ON DELETE CASCADE`: deleting a role removes its permission rows because those permissions have no meaning without that role. `(role_id, permission_key)` is unique, preventing the same permission from being attached twice. The role foreign key is indexed.

### `membership_roles`

This join table assigns a role to a membership. The membership foreign key uses `ON DELETE CASCADE`, so deleting a membership automatically removes its role assignments. The role foreign key uses `ON DELETE RESTRICT`, so a role cannot be removed while memberships still reference it. `(membership_id, role_id)` is unique and both foreign keys are indexed.

### Dependency-safe migration order

Upgrade order is `tenants`, `users`, `memberships`, `roles`, `role_permissions`, then `membership_roles`. That order ensures every referenced table exists before a foreign key is added, except the one invitation relationship explicitly deferred by CCR-004. Downgrade uses the reverse dependency direction: `membership_roles`, `role_permissions`, `roles`, `memberships`, `users`, `tenants`. Alembic/PostgreSQL can therefore remove the schema without encountering a child table that still depends on a parent.

### Real PostgreSQL constraint tests

The database integration suite now expects exactly the Alembic bookkeeping table plus these six product tables after migration head. A dedicated `test_rbac_migration.py` validates the schema and attempts invalid writes against real PostgreSQL. It proves duplicate tenant slugs, duplicate OIDC identities, duplicate tenant/user memberships, invalid tenant/user/membership statuses, duplicate membership-role mappings, duplicate role permissions, and duplicate global role keys are rejected by PostgreSQL. It also inspects the temporary invitation column/index and confirms CCR-004's foreign key has not been added early.

Each negative test creates its seed data and the failing insert in one transaction. The expected `IntegrityError` causes that transaction to roll back, so one test cannot pollute another with leftover rows. This lets the suite exercise actual PostgreSQL constraints rather than mocking database behavior or using SQLite.

### Upgrade, downgrade, upgrade verification

The permanent CI database job now performs a stronger migration sequence. It upgrades a clean PostgreSQL database to `head`, runs all integration tests, downgrades the tenant/RBAC migration back to `20260814_0001`, upgrades to `head` again, and finally downgrades the entire chain to `base`. This checks both directions and proves the migration can be reapplied after removal.

### What this improves

Before OPE-277, Serviq had a reliable database connection and migration framework but no organization or workforce data model. After this ticket, future authentication, tenant onboarding, invitations, team management, and authorization work can build on an explicit relational foundation whose invalid states are blocked at the database layer. The role/permission model is normalized and tenant-aware rather than being embedded in application conditionals.

### What is intentionally not built

This ticket adds no organization invitation table, invitation token logic, API endpoint, service, repository, seed data, platform-operator shortcut, authentication middleware, or permission-enforcement middleware. It also does not add the deferred invitation foreign key; OPE-278 owns that final step under CCR-004. The schema is foundation only.

### Validation required before completion

The pull request must pass normal repository lint/type/tests, the real PostgreSQL migration/constraint/reversibility job, and the Security workflow. The cumulative guide and repository context must describe CCR-004 so a later engineer does not misinterpret the temporary missing invitation foreign key as an accidental omission.


## OPE-278 — Secure organization invitation database schema

### What this ticket builds

OPE-278 adds the database structure Serviq will later use when one organization invites a person to join its workforce. The important word is *later*: this ticket does not send invitation emails, generate invitation links, accept invitations, or calculate runtime expiry. It builds the safe persistence layer those future workflows need.

The migration is Alembic revision `20260814_0003_organization_invitations.py`, directly after the OPE-277 tenant/workforce/RBAC revision. It creates exactly two new product tables: `organization_invitations` and `organization_invitation_roles`. It also completes the one foreign-key step deliberately deferred by CCR-004 from OPE-277.

### A simple way to think about an invitation token

An invitation link will eventually contain a random secret value. Whoever possesses that secret can attempt to prove they received the invitation. Storing that secret directly in the database would be risky: if a database snapshot, support query, or accidental export exposed the table, the raw invitation links could potentially be reused.

Serviq therefore stores only `token_hash`. A hash is a one-way representation of the future secret. The intended runtime pattern is similar to password verification: when a user presents an invitation token, future application code will hash the presented value and compare the result with the stored hash. The database does not need the plaintext token after the invitation is created.

This migration makes that security choice structural. There is no `token`, `raw_token`, `invite_token`, `invitation_token`, or equivalent plaintext column. The database has only `token_hash`, and that hash is globally unique. Even two different tenants cannot store the same invitation hash. OPE-278 tests inspect the real PostgreSQL table metadata to make sure the plaintext-token columns do not exist.

### `organization_invitations`

Each invitation belongs to one tenant through `tenant_id`. The foreign key uses `ON DELETE RESTRICT`, meaning a tenant cannot be removed while invitation history still depends on it.

`email_normalized` stores the email form that future application code will use for matching. Its length is restricted to 3–320 characters. This ticket intentionally does not implement the normalization algorithm itself; that belongs to runtime invitation logic. The database contract simply makes the normalized value the canonical matching field.

`status` can only be one of four values: `pending`, `accepted`, `revoked`, or `expired`. PostgreSQL enforces that list with a CHECK constraint. A typo such as `acceptd` or an unapproved lifecycle state cannot silently enter the database.

`invited_by_user_id` records which workforce user created the invitation and is required. `accepted_by_user_id` is nullable because a new invitation has not yet been accepted. Both reference `users` with `ON DELETE RESTRICT`, preserving the identity history while invitation rows exist. Because Serviq's database conventions require foreign-key lookup support, both user-reference columns have explicit indexes.

`expires_at` is required and records when the invitation stops being usable. `accepted_at` and `revoked_at` are optional lifecycle timestamps. The frozen product rule says invitations expire after seven days, but calculating that seven-day value is deliberately not done by this migration. Future invitation creation logic will write the correct expiry time. The database only requires that a value exists.

Like the other mutable product tables, invitations receive UUIDv7 primary keys plus timezone-aware `created_at` and `updated_at` timestamps using the shared architecture convention.

### Why only one pending invitation may exist for one tenant/email

Imagine an administrator clicking “Invite” multiple times for the same person. If the database allowed several simultaneously pending invitations for the same tenant and normalized email, later code would have to guess which invitation is authoritative. That creates confusing user experiences and increases the number of valid invitation secrets.

OPE-278 prevents that with a PostgreSQL *partial unique index*. The index is unique on `(tenant_id, email_normalized)` only when `status = 'pending'`. In plain language, a tenant may have only one currently pending invitation for an email address.

The word *partial* matters because historical invitations must remain useful history. An accepted, revoked, or expired invitation does not block a later new pending invitation for the same email. The integration tests prove both sides of this rule: a second pending invitation is rejected, while an accepted historical invitation and a new pending invitation can coexist.

The migration also creates ordinary indexes for `(tenant_id, status, expires_at)` and `(tenant_id, email_normalized)`. These support future jobs that search for expiring invitations and future organization-scoped invitation lookups.

### `organization_invitation_roles`

An invitation may request one or more Serviq roles. Those role requests are not stored as a comma-separated string inside the invitation row. Instead, `organization_invitation_roles` is a proper join table between an invitation and a role.

`invitation_id` references `organization_invitations` with `ON DELETE CASCADE`. If an invitation row is deleted, its requested-role mappings have no independent meaning, so PostgreSQL removes them automatically. `role_id` references `roles` with `ON DELETE RESTRICT`, preventing a role from disappearing while an invitation still requests it.

The pair `(invitation_id, role_id)` is unique, so the same role cannot be attached twice to one invitation. Both foreign-key columns are indexed. Real PostgreSQL tests verify duplicate mappings are rejected and a mapping cannot point to a role that does not exist.

### CCR-004 is now fully completed

OPE-277 created `memberships.created_by_invitation_id` but could not add its final foreign key because `organization_invitations` did not exist yet. CCR-004 documented that migration-order dependency before OPE-277 was merged.

OPE-278 now completes the contract. After creating `organization_invitations`, revision `20260814_0003` adds the named foreign key from `memberships.created_by_invitation_id` to `organization_invitations.id` with `ON DELETE SET NULL`. This means a membership can remember the invitation that originally created it, but deleting an invitation record does not delete the membership. Instead PostgreSQL preserves the membership and clears only its invitation-origin pointer.

The integration suite proves this behavior by creating a tenant, user, invitation, and membership linked to that invitation; deleting the invitation; and confirming the membership still exists with `created_by_invitation_id = NULL`. The existing OPE-277 schema test is also updated from the temporary “FK intentionally absent” state to the final “FK exists and uses SET NULL” state.

### Why downgrade drops the membership foreign key first

A database migration must work in both directions. On upgrade, the invitation table has to exist before the membership foreign key can reference it. On downgrade, the dependency order is reversed: PostgreSQL cannot drop `organization_invitations` while `memberships` still has a foreign key pointing at it.

The OPE-278 downgrade therefore removes the deferred membership foreign key first, then removes `organization_invitation_roles`, then removes `organization_invitations`. Once revision `20260814_0002` is restored, the database is back in the exact CCR-004 intermediate state expected by OPE-277.

### Real PostgreSQL tests

OPE-278 extends the permanent database integration suite instead of relying on SQLite or mocked migration behavior. At migration head, the expected schema now includes the two invitation tables in addition to the OPE-277 tables and Alembic metadata.

The invitation-specific integration tests verify: only a token hash is persisted; the expected tenant/user/FK indexes exist; the partial unique index is really a unique PostgreSQL index whose predicate is limited to `pending`; duplicate pending invitations are rejected; accepted history does not block a new pending invitation; duplicate token hashes are rejected globally; invalid invitation status and invalid email length are rejected; duplicate invitation-role mappings are rejected; nonexistent role references are rejected; and deleting an invitation sets the membership-origin reference to null. Test hashes use clearly fake strings rather than anything resembling a production invitation secret.

The CI migration sequence is now aligned with this revision: upgrade a clean PostgreSQL database to `head`, run the full integration suite, downgrade specifically to `20260814_0002`, upgrade to `head` again to prove OPE-278 can be reapplied, then downgrade the complete chain to `base`. This gives explicit evidence that both the new tables and CCR-004 foreign key can be created and removed safely.

### What this improves

After OPE-278, Serviq has a database-safe way to represent an organization invitation lifecycle without requiring plaintext invitation secrets. The schema prevents duplicate live invitations for the same organization/email, preserves historical invitations, records who invited and who accepted, supports requested role assignments, and connects resulting memberships back to their originating invitations with safe delete behavior.

These protections are enforced at the PostgreSQL layer. Future API validation can provide friendlier error messages, but even a bug in future application code cannot bypass the database's unique, CHECK, or foreign-key constraints without deliberately changing the schema.

### What is intentionally not built

This ticket does not generate secure random tokens, hash presented tokens, send email, normalize email strings, create an invitation API, calculate seven-day expiry at runtime, automatically mark expired invitations, accept/revoke invitations, assign roles to memberships, or implement authorization rules. It also does not add example plaintext tokens to fixtures. Those behaviors belong to later runtime/service tickets and must consume this schema rather than expanding it ad hoc.

### Validation required before completion

The final pull request must pass the normal repository quality job, including lint, strict type checking, tests, and Compose validation; the real PostgreSQL integration job with upgrade/downgrade/re-upgrade coverage; and the OPE-272 Security workflow. The temporary OPE-278 documentation workflow is removed before merge.

---

# OPE-272 through OPE-278 — final completion reconciliation

This section closes the loop on OPE-272 through OPE-278. The detailed sections above remain the main plain-language implementation record. This final reconciliation confirms which work is actually present on `main`, which GitHub issue and pull request delivered it, and what the seven-ticket batch improved as a whole.

No duplicate GitHub issues or replacement implementation branches were created during this reconciliation. Each ticket had already followed the intended one-ticket, one-branch, one-pull-request workflow and was already completed in Linear and GitHub.

## OPE-272 — baseline repository security scanning

**Final status:** Completed. GitHub issue #69 was closed as completed through merged PR #76.

This ticket added permanent automated security checks for source code, accidentally committed secrets, filesystem and configuration risks, and vulnerable dependencies. It also turned the local `make security` command into a real check instead of a placeholder. The practical improvement is that basic repository security no longer depends on a developer remembering to run several unrelated tools manually before every change.

## OPE-273 — typed platform configuration and safe environment example

**Final status:** Completed. GitHub issue #70 was closed as completed through merged PR #77.

This ticket created typed configuration boundaries for the API and worker and added a safe root `.env.example`. Invalid settings now fail early with messages that identify the bad field without printing secret values. Production-only secrets have no unsafe production defaults, and tenant-owned provider keys remain outside this platform configuration boundary. The improvement is predictable startup behavior and a much lower chance of confusing configuration bugs or accidental credential exposure.

## OPE-274 — public README and reproducible local setup

**Final status:** Completed. GitHub issue #71 was closed as completed through merged PR #78.

This ticket replaced the placeholder README with a real public project entry point. It explains the product, current implementation status, repository map, prerequisites, verified setup and validation commands, documentation links, and important limitations. Planned commands are labeled as planned, the 10-million-connection goal is described as a future architecture target rather than a proven benchmark, and DoorDash/Stripe references are clearly non-affiliated. The improvement is trust: a new reader can understand what exists today without being misled by aspirational product claims.

## OPE-275 — SQLAlchemy database sessions and Alembic foundation

**Final status:** Completed. GitHub issue #72 was closed as completed through merged PR #79.

This ticket introduced Serviq's real PostgreSQL persistence foundation without prematurely creating product tables. Because the architecture had not frozen synchronous versus asynchronous SQLAlchemy usage, ADR-001 recorded the decision before code was written. The project now has one asynchronous SQLAlchemy/Psycopg session pattern, one model base, Alembic configuration, a reversible baseline migration, and real PostgreSQL integration validation. The improvement is that future database-backed features have one approved persistence pattern instead of competing connection/session designs.

## OPE-276 — database-aware readiness health check

**Final status:** Completed. GitHub issue #73 was closed as completed through merged PR #80.

This ticket made `/health/ready` prove that PostgreSQL can actually answer a simple query within the two-second readiness budget while keeping `/health/live` independent from the database. Failure and timeout responses use the frozen safe contract and do not expose credentials, database URLs, raw SQLAlchemy exceptions, or stack traces. ADR-002 records the health-module boundary that had not previously been frozen. The improvement is operational correctness: infrastructure can distinguish a process that is alive from an API instance that is truly ready for database-dependent traffic.

## OPE-277 — tenant, workforce, and RBAC database migration

**Final status:** Completed. GitHub issue #74 was closed as completed through merged PR #81.

This ticket created the six frozen tenant/workforce/RBAC tables and enforced their important uniqueness, state, index, and foreign-key rules directly in PostgreSQL. A migration sequencing conflict was discovered because memberships needed to reference invitations that would not exist until OPE-278. CCR-004 documented the safe two-step contract instead of silently expanding the ticket or creating an invalid dependency. Real PostgreSQL tests verify duplicate and invalid-state behavior. The improvement is a database-enforced identity and authorization foundation that later API code can rely on.

## OPE-278 — secure organization invitation persistence

**Final status:** Completed. GitHub issue #75 was closed as completed through merged PR #82.

This ticket created organization invitation and invitation-role persistence. Invitation secrets are represented only by a stored token hash, never a plaintext token. PostgreSQL enforces token-hash uniqueness, invitation lifecycle states, email constraints, role mappings, and one pending invitation per tenant and normalized email while preserving historical invitations. The migration also completes CCR-004 by adding the deferred membership-to-invitation foreign key with safe `ON DELETE SET NULL` behavior. The improvement is a secure persistence boundary that future invitation APIs can build on without weakening token or data-integrity rules.

## What the seven-ticket batch changes overall

After OPE-272 through OPE-278, Serviq has automated baseline security scanning, typed platform configuration, a truthful public setup guide, one documented PostgreSQL session pattern, reversible Alembic migrations tested against real PostgreSQL, database-aware API readiness, tenant/workforce/RBAC persistence, and secure invitation persistence.

These are foundation capabilities. They do **not** mean Serviq is production-ready yet. Authentication flows, authorization services, invitation runtime APIs, tenant onboarding, AI-agent workflows, business tools, deeper observability, production deployment, and later product behavior still need their own tickets and validation.

## Completion evidence

| Linear ticket | GitHub issue | Merged PR | Final result |
|---|---:|---:|---|
| OPE-272 | #69 | #76 | Security scanning baseline |
| OPE-273 | #70 | #77 | Typed platform configuration |
| OPE-274 | #71 | #78 | Verified public README/setup guide |
| OPE-275 | #72 | #79 | SQLAlchemy + Alembic persistence foundation |
| OPE-276 | #73 | #80 | Database-aware API readiness |
| OPE-277 | #74 | #81 | Tenant/workforce/RBAC schema |
| OPE-278 | #75 | #82 | Secure organization invitation schema |

All seven Linear tickets are in `Done`, all seven GitHub issues are closed as completed, and all seven implementation pull requests are merged. The detailed ticket sections earlier in this guide explain what changed, how it works, why it was done, what it improves, how it was validated, and what remains intentionally out of scope.


---

# OPE-279 — trusted RequestContext

OPE-279 implements Architecture Contract C-1 as real backend code. Before this ticket, `services/api/app/core/auth.py` was only a reserved placeholder. Serviq had an architecture description of trusted identity and tenant context, but there was no canonical Python object that later services could safely accept.

The ticket adds strict actor categories (`tenant_user`, `customer`, `service`, `platform_operator`) and strict assurance levels (`anonymous`, `verified`, `workforce`, `platform`). Unknown values are rejected during validation instead of being treated as approximately correct.

The new `RequestContext` keeps the exact meaning of Contract C-1: request ID, tenant UUID, actor, optional internal user/customer IDs, permissions, and assurance level. Python code uses snake_case names while Pydantic aliases preserve the frozen camelCase contract names when serialized.

The context is frozen after construction. The nested actor is frozen too, and the in-process permission collection is immutable. This prevents later code from changing trusted tenant or identity information after authentication/authorization resolution has already occurred.

A small `has_permission()` helper provides capability lookup without creating route guards in this ticket. A separate `require_tenant_id()` helper fails closed with a typed `MissingTenantContextError` when trusted context is unavailable. It never falls back to a default tenant, request body, or arbitrary tenant header.

OPE-279 also introduces the minimum internal typed authorization-context error hierarchy needed by that fail-closed helper. It deliberately does not add global HTTP exception handling. HTTP mapping remains a later concern.

Focused unit tests cover valid workforce, verified-customer, and anonymous-customer contexts, exact Contract C-1 serialization, invalid actor/assurance values, missing trusted tenant context, and immutability.

This ticket does **not** validate OIDC tokens, create sessions, query memberships, add route guards, or read tenant IDs from client input. Its purpose is narrower: provide one safe shape that later trusted auth and tenancy code can populate.

The detailed file-by-file explanation for this ticket is also recorded in `docs/OPE_279_285_IMPLEMENTATION_GUIDE.md`.


---

# OPE-280 — workforce OIDC token validation

OPE-280 adds Serviq's first real cryptographic workforce identity-verification boundary. A workforce JWT is not trusted because it contains familiar-looking fields. The API now verifies the signature against the configured issuer's JWKS, allows only RS256, requires exact issuer and audience, validates expiry, and requires a non-empty subject before identity data is considered trusted.

The API scaffold did not previously contain an approved JOSE/JWT package, so the ticket's architecture stop condition was triggered. ADR-003 resolves that deliberately by approving `joserfc` and moving the already-used `httpx` client into runtime dependencies for OIDC metadata retrieval. The dependency lockfile was regenerated so every environment installs the same resolved packages.

OIDC discovery always starts from configured `OIDC_ISSUER_URL`, never from an issuer supplied by the token. Discovery must repeat that exact issuer. Its `jwks_uri` is then validated before fetching. Production/staging metadata must use HTTPS, while local/test HTTP is limited to loopback development hosts. Redirects are disabled, requests have a five-second timeout, and metadata bodies are bounded.

Discovery and JWKS are cached for at most five minutes under one async lock. This prevents authentication from performing two identity-provider network requests for every API request and prevents a cold-cache burst from starting many identical refreshes.

Successful validation returns only `VerifiedWorkforceIdentity`: issuer, subject, optional normalized email, email verification state, and optional display name. Even a valid signed token cannot inject a Serviq tenant ID or permission list because those fields are not copied into the trusted DTO. Tenant membership and authorization remain database-owned.

All failures become the stable internal `UNAUTHENTICATED` category with the generic message `Authentication failed.` Raw token text and raw JOSE/network exceptions are not logged, stored, or returned.

Automated tests cover success plus wrong issuer, wrong audience, expiry, invalid signature, missing/blank subject, malformed token, discovery mismatch, caching, email verification behavior, claim filtering, and token redaction. A dedicated security review is recorded at `docs/security-reviews/OPE-280-workforce-oidc-validation.md`.

This ticket does not implement browser PKCE/session handling, user persistence, membership lookup, tenant resolution, or RequestContext construction. Those remain separate trust boundaries in later tickets.

The detailed implementation narrative for OPE-280 is in `docs/OPE_279_285_IMPLEMENTATION_GUIDE.md`.


---

# OPE-281 — stable internal workforce user identity

OPE-281 connects the verified OIDC identity from OPE-280 to Serviq's existing `users` table. The primary identity is always the exact `(oidc_issuer, oidc_subject)` pair, never email.

The ticket adds a workforce domain module with an ORM mapping for the already-created users table, an exact identity repository query, a frozen internal-user DTO, typed disabled/profile errors, and a transaction-owning upsert service. No database migration or membership logic is added.

On first login, the service inserts an active user. On repeat login, it returns the same internal UUID and safely synchronizes changed email/display-name profile data. A missing email fails before persistence because the frozen database contract requires a non-null email. A disabled internal user remains disabled even when the external OIDC identity is valid.

Concurrent first login is handled using the database unique constraint plus a nested savepoint. If two callers race, one insert wins. The losing savepoint rolls back and reloads the winning row, so both successful callers resolve the same `users.id` instead of creating duplicates or returning an avoidable 500.

Real PostgreSQL integration tests cover first/repeat login, multiple issuers, profile synchronization, disabled-user behavior, concurrent first-login contention, and incomplete verified profile input.

The detailed implementation narrative is in `docs/OPE_279_285_IMPLEMENTATION_GUIDE.md`.


---

# OPE-282 — tenant membership and effective capability resolution

OPE-282 adds the tenant-scoped authorization resolver that sits between a stable internal workforce user and later protected organization APIs. The resolver requires the exact trusted `(user_id, tenant_id)` pair and accepts only an `active` membership. Missing and suspended memberships fail closed.

ADR-004 resolves the previously unstated system-role rule before coding: a tenant-owned role contributes only to its own tenant, while a global role is reusable only when `tenant_id IS NULL` and `is_system = true`. A role owned by another tenant is filtered out even if a malformed mapping row points to it. Global system roles remain workforce RBAC and cannot create platform-operator access.

The new tenancy module maps the existing membership/RBAC tables without changing the schema, performs tenant-safe joins, deduplicates permission keys, and returns one immutable `ResolvedTenantMembership` DTO.

Real PostgreSQL tests deliberately map a Tenant A membership to a Tenant B role and prove the foreign permission is excluded. They also cover overlapping permission deduplication, approved global system roles, global non-system exclusion, suspended membership, and missing membership.

A dedicated security review is recorded at `docs/security-reviews/OPE-282-tenant-capability-resolution.md`. No HTTP route or middleware behavior is added in this ticket.

The detailed implementation narrative is in `docs/OPE_279_285_IMPLEMENTATION_GUIDE.md`.


---

# OPE-283 — organization list and create APIs

OPE-283 exposes the first tenant-management workforce endpoints: GET and POST `/api/v1/organizations`.

Two explicit stop conditions were resolved before route code. CCR-005 freezes and seeds global workforce system roles `owner` and `admin`, each with `organization.settings.write` and `organization.members.manage`. ADR-005 freezes the protected-route principal handoff as server-owned `request.state.serviq_user_id`; organization routes never accept a client-supplied user ID.

The API now mirrors Serviq's frozen `{data:...}` and `{error:{...}}` envelopes in Python and maps authentication/request-validation failures into those shapes. Organization creation validates the exact slug/display-name contract and rejects unknown fields.

GET lists only tenants reached through the current user's active memberships. POST performs one transaction that creates the tenant, the creator's active membership, and the mapping to the pre-seeded Owner role. Duplicate slug maps to 409. Any later mapping failure rolls the whole transaction back.

Real PostgreSQL/API tests cover empty/two-organization lists, cross-user isolation, Owner mappings, duplicate slug, all specified validation failures, unauthenticated access, and a forced mapping failure proving atomic rollback.

A focused security review is recorded at `docs/security-reviews/OPE-283-organization-list-create.md`, and the detailed implementation narrative is in `docs/OPE_279_285_IMPLEMENTATION_GUIDE.md`.


---

# OPE-284 — organization detail and update APIs

OPE-284 adds GET and PATCH `/api/v1/organizations/{organizationId}` while preserving tenant non-disclosure. Both routes first prove that the current server-owned workforce user has an active membership before returning organization metadata. A foreign user receives 404 rather than learning whether another tenant's UUID exists.

PATCH then reuses OPE-282 capability resolution and requires the exact CCR-005 permission `organization.settings.write`. Owner/Admin can update, while same-tenant roles without that capability receive 403.

The PATCH schema exposes only trimmed `displayName` and V1 `defaultLocale=en`, rejects unknown fields, and rejects an empty change set. `slug` and `status` are therefore immutable through this API. The membership check, capability check, mutation, and flush run inside one transaction.

Real PostgreSQL/API tests cover member read, Owner/Admin updates, support-role denial, cross-tenant 404 behavior, unsupported locale, invalid display names, immutable `slug`/`status`, empty PATCH, and unauthenticated access.

A focused review is recorded at `docs/security-reviews/OPE-284-organization-detail-update.md`; the detailed narrative is in `docs/OPE_279_285_IMPLEMENTATION_GUIDE.md`.


---

# OPE-285 — secure invitation create, list, and revoke APIs

OPE-285 adds workforce invitation management without ever storing a plaintext invitation token. The new routes are GET/POST `/api/v1/organizations/{organizationId}/invitations` and DELETE `/api/v1/organizations/{organizationId}/invitations/{invitationId}`.

ADR-006 resolves the ticket's security stop conditions before implementation. Serviq now has one deterministic invitation-email normalization rule, 256-bit `secrets.token_urlsafe(32)` bearer-token generation, SHA-256 storage of the random token, a one-time `{SERVIQ_PUBLIC_BASE_URL}/invite?token=...` response URL, and an explicit assignable-role policy. Tenant-owned roles are allowed, while global roles are assignable only when they are the approved workforce `owner` or `admin` roles. Foreign and other global system/platform-like roles are rejected.

All invitation operations require an active target-tenant membership plus `organization.members.manage`. Missing membership is non-disclosing 404; a same-tenant member without the capability receives 403.

Create validates authorization and roles before generating the secret, then hashes the token immediately. Invitation metadata and all role mappings are one transaction, and PostgreSQL's partial unique index remains the authority for one pending invitation per normalized tenant/email. The invitation expires exactly seven days after creation. Only the successful create response contains `inviteUrl`; normal list/revoke serializers contain no token, token hash, or invite URL.

Revoke is tenant-scoped and pending-only. Accepted, already-revoked, or time-expired invitations return lifecycle conflict rather than being treated as pending. A foreign tenant cannot probe an invitation ID through revoke.

Real PostgreSQL/API tests verify Owner/Admin creation, support denial, foreign-tenant isolation, foreign/global-platform role rejection, duplicate pending-email conflict, normalized email, one-time token URL, stored SHA-256 digest, seven-day expiry, log redaction, secret-free list/revoke responses, successful pending revoke, repeated-revoke conflict, accepted-invite conflict, strict input validation, and unauthenticated access.

The premium security review is recorded at `docs/security-reviews/OPE-285-invitation-management.md`. The full non-technical implementation narrative is in `docs/OPE_279_285_IMPLEMENTATION_GUIDE.md`.

This ticket does not implement invitation acceptance or email delivery. Those later workflows must reuse the exact normalization and hashing helpers established here.


---

# OPE-286 through OPE-295 — final implementation reconciliation

This reconciliation records the final, actually merged state of the ten-ticket OPE-286 through OPE-295 batch. It complements the detailed ticket narratives in this build guide and `docs/OPE_286_295_IMPLEMENTATION_GUIDE.md`.

The important distinction is **merged and validated on `main`**, not merely “code existed on a feature branch.” During this batch several earlier stacked branches had to be rebuilt cleanly, and permanent CI found real defects that were corrected before merge.

## Final ticket-by-ticket status

### OPE-286 — invitation acceptance

**GitHub issue #98, merged PR #108, Linear Done.**

Serviq can accept a valid pending workforce invitation atomically after authenticated identity and verified email checks. The flow protects single-use invitation semantics, tenant-safe role assignment, token-hash handling, and concurrent acceptance behavior. The practical improvement is that the invitation lifecycle is now complete enough to turn an issued invite into real organization membership safely.

### OPE-287 — member list and role/status management

**GitHub issue #99, merged PR #109, Linear Done.**

Authorized Owners/Admins can list tenant members and update allowed membership roles/status without crossing tenant boundaries. The service enforces role allowlisting and protects the last active Owner from being removed or suspended. The practical improvement is a real backend foundation for Team & Access administration instead of invitations only.

### OPE-288 — reusable tenant-isolation harness

**GitHub issue #100, merged PR #110, Linear Done.**

The real PostgreSQL test suite now has reusable adversarial tenant-A/tenant-B fixtures, deliberately overlapping visible values, known foreign UUID attacks, and persisted-state assertions. The practical improvement is that future tenant-owned domains can prove isolation using a common hostile test pattern instead of writing weak one-off tests.

### OPE-289 — provider/model metadata

**GitHub issue #101, merged PR #116, Linear Done.**

PostgreSQL now has `provider_connections` and `model_configurations`. Provider rows contain safe metadata and an opaque `secret_ref`, never a plaintext provider key. Model aliases are tenant-scoped and decouple product/agent code from provider model strings. The practical improvement is a database-enforced BYOK/model configuration foundation.

### OPE-290 — tenant secret adapter

**GitHub issue #102, merged PR #117, Linear Done.**

Serviq now has a `TenantSecretStore` abstraction plus a real encrypted local implementation. Secrets are referenced by random opaque IDs, encrypted before disk persistence, tenant-bound, redacted from representation/errors, and written atomically. The practical improvement is a credential boundary that can later be replaced with a managed secret service without rewriting provider-management code.

### OPE-291 — provider connection CRUD

**GitHub issue #103, merged PR #118, Linear Done.**

Authorized tenant users can create/list/read/update/delete BYOK provider connections. The API uses trusted tenant context, `ai.providers.manage`, encrypted secret-store coordination, row locking for replacement/deletion-sensitive operations, safe compensation/cleanup, and provider-in-use protection. Plaintext API keys are never returned.

The clean mainline rebuild was important: CI exposed incorrect module imports, the wrong ORM base reference, a FastAPI 204 response-contract problem, secret-store dependency drift, and a tuple/list API type mismatch. Each was fixed and the full matrix rerun before merge.

### OPE-292 — normalized C-4 gateway contract

**GitHub issue #104, merged PR #119, Linear Done.**

The LLM Gateway now owns strict provider-neutral request, response, usage, streaming, and error models. It freezes token/timeout hard ceilings and exactly five normalized provider failure categories. Agents/domain code can depend on Serviq types rather than provider SDK types.

### OPE-293 — deterministic fake LLM adapter

**GitHub issue #105, merged PR #121, Linear Done.**

The shared `LLMAdapter`/`AdapterContext` boundary and deterministic fake provider make AI success, streaming, malformed-output, timeout, rate-limit, unavailable, and auth-failure tests reproducible with zero paid calls and zero network dependency. ADR-010 keeps fake behavior out of the public provider enum.

The fake streaming tests also uncovered a shared C-4 correctness issue: global string trimming could corrupt provider-generated chunks. That was corrected separately in PR #123 so request identifiers remain normalized while provider output text is preserved exactly.

### OPE-294 — OpenAI adapter

**GitHub issue #106, merged PR #124, Linear Done.**

After ADR-011 froze `openai==2.53.0`, the official SDK adapter was implemented behind C-4. It supports non-stream text, JSON Schema structured output, ordered streaming, usage/finish/request ID normalization, bounded time/output tokens, safe BYOK handling, `max_retries=0`, and full C-4 error normalization.

Tests inject mocked SDK clients and make no paid OpenAI call. Strict mypy caught a request/output SDK type mismatch during validation; the final implementation uses the actual request parameter types.

### OPE-295 — Anthropic adapter

**GitHub issue #107, merged PR #125, Linear Done.**

After ADR-011 froze `anthropic==0.121.0`, the Anthropic adapter was added behind the same C-4 interface. Leading C-4 system messages are translated to Anthropic's top-level system field while user/assistant history remains ordered. Unsupported late system messages fail explicitly rather than being silently reordered.

The adapter supports non-stream generation, JSON Schema structured output, text/structured streaming, usage/stop/request ID normalization, bounded calls, disabled hidden retries, safe BYOK handling, and the same five provider-neutral error categories. Mocked tests make no live Anthropic call.

## Supporting decisions/fixes that were required to finish the batch

### PR #122 — official provider SDK baseline

The original OPE-294/OPE-295 tickets correctly stopped because no approved official provider SDK version existed in the repository. ADR-011 resolved that prerequisite before feature implementation by pinning:

```text
openai==2.53.0
anthropic==0.121.0
```

SDK classes are restricted to provider adapters/tests. C-4 remains Serviq-owned, and API keys enter adapters only through server-resolved context.

### PR #123 — preserve generated text

C-4 originally used one whitespace-trimming Pydantic base for both request identifiers and provider output. That could change streamed model text such as `" world"` into `"world"`.

PR #123 introduced an output-specific strict base that does not strip generated text. This is a correctness fix, not a provider-specific extension: the C-4 field set, provider enum, and budgets did not change.

## Validation discipline

Across the final PRs, merge required the repository's permanent quality/security gates:

- frontend/Python lint;
- strict TypeScript/Python type checking;
- unit/contract tests;
- Docker Compose validation;
- real PostgreSQL integration tests;
- migration upgrade/downgrade/re-upgrade coverage;
- Trivy filesystem/configuration scanning;
- dependency vulnerability audit;
- Gitleaks history/tree secret scanning;
- Python CodeQL;
- JavaScript/TypeScript CodeQL.

Transient GitHub action-download HTTP 429 failures were rerun unchanged. Code/security rules were not weakened to turn infrastructure noise green.

## Clean-branch reconciliation

Several OPE-289 through OPE-293 implementations originally existed as stacked PRs. As predecessor tickets were squash-merged, those historical stacks polluted later diffs with already-merged files.

The final implementations were rebuilt from the real mainline so the authoritative PRs contain only the intended ticket delta:

- OPE-289 -> PR #116;
- OPE-290 -> PR #117;
- OPE-291 -> PR #118;
- OPE-292 -> PR #119;
- OPE-293 -> PR #121.

Superseded stacked PRs remain historical evidence but are not the merged source of truth.

## What the ten-ticket batch changes overall

After OPE-286 through OPE-295, Serviq now has:

- complete workforce invitation acceptance;
- protected member/role/status administration;
- reusable tenant-isolation adversarial tests;
- provider/model metadata with no relational plaintext provider keys;
- a tenant-scoped secret-store contract and encrypted local adapter;
- tenant-scoped BYOK provider CRUD;
- one strict provider-neutral LLM gateway contract;
- deterministic offline AI testing;
- an official OpenAI adapter;
- an official Anthropic adapter.

This is a major V1 production-foundation step, but it is not the end of the AI platform. Gemini/OpenRouter adapters, provider connectivity testing, model-configuration CRUD/alias resolution, runtime provider routing/fallback, knowledge ingestion, agent workflows, production managed secret storage, and later observability/deployment work remain separate tickets.

## Completion evidence

| Linear ticket | GitHub issue | Final merged PR | Result |
|---|---:|---:|---|
| OPE-286 | #98 | #108 | Invitation acceptance |
| OPE-287 | #99 | #109 | Member/RBAC management |
| OPE-288 | #100 | #110 | Tenant-isolation test harness |
| OPE-289 | #101 | #116 | Provider/model metadata schema |
| OPE-290 | #102 | #117 | Tenant secret-store adapter |
| OPE-291 | #103 | #118 | Provider connection CRUD |
| OPE-292 | #104 | #119 | C-4 normalized gateway contract |
| OPE-293 | #105 | #121 | Deterministic fake LLM adapter |
| OPE-294 | #106 | #124 | OpenAI adapter |
| OPE-295 | #107 | #125 | Anthropic adapter |

Supporting merged PRs: **#122** (provider SDK architecture baseline) and **#123** (C-4 provider-output whitespace correctness).

All ten Linear tickets are `Done`, all ten feature implementations are merged to `main`, and this documentation records what changed, why it changed, what it improves, how it was validated, and what remains intentionally outside the batch.


# OPE-296 through OPE-299 — architecture-blocked implementation reconciliation

## Why this section exists

OPE-296 through OPE-299 were started using the same disciplined workflow as earlier Serviq tickets: read Linear first, inspect current repository reality, compare it with frozen Architecture/ADRs, create separate GitHub tracking, and only then change production code.

This batch reached an important result: **all four feature tickets triggered their own `Needs Architect Decision` stop conditions before safe production implementation could begin.**

That does not mean nothing was done. It means the repository audit found missing decisions that builder tickets are explicitly forbidden to invent. The correct production-grade behavior was to stop, record the evidence, preserve the branch/issue history, and leave the feature tickets open.

A separate detailed explanation now exists at:

`docs/OPE_296_299_IMPLEMENTATION_GUIDE.md`

Ticket-specific blocker records are under:

`docs/architecture-blockers/`

## Ticket tracking and branch history

| Linear ticket | GitHub issue | Branch | Merged documentation PR | Feature status |
|---|---:|---|---:|---|
| OPE-296 | #127 | `agent/ope-296-gemini-adapter` | #131 | Needs Architect Decision |
| OPE-297 | #128 | `agent/ope-297-openrouter-adapter` | #132 | Needs Architect Decision |
| OPE-298 | #129 | `agent/ope-298-provider-connectivity-test` | #133 | Needs Architect Decision |
| OPE-299 | #130 | `agent/ope-299-model-configuration-crud` | #134 | Needs Architect Decision |

All four ticket PRs passed both CI and Security before merge.

The GitHub issues and Linear tickets remain open/backlogged because documentation of a blocker is not the same as implementing the requested product feature.

---

## OPE-296 — Gemini generation and streaming adapter

### What we were supposed to build

A Gemini implementation behind Serviq's Contract C-4, including non-stream generation, ordered streaming, safe message translation, usage/finish/request-ID normalization, timeout/output limits, provider error normalization, and explicit rejection of unsupported capabilities.

### What repository audit found

ADR-011 freezes only:

- `openai==2.53.0`;
- `anthropic==0.121.0`.

The ADR explicitly says it does not approve Gemini dependencies. `services/llm-gateway/pyproject.toml` therefore has no approved Gemini SDK.

OPE-296 expressly says to stop when no approved Gemini SDK exists in repo context.

### What changed

GitHub issue #127 and branch `agent/ope-296-gemini-adapter` were created.

The branch added:

`docs/architecture-blockers/OPE-296-gemini-sdk-decision.md`

PR #131 passed CI/Security and was squash-merged.

### Why we did not add code anyway

Selecting a Gemini SDK from a builder ticket would silently decide production dependency provenance, Python 3.14 compatibility, streaming behavior, retries, exception semantics, and future upgrade policy. That is exactly the architecture decision the ticket requires to exist first.

### What this improves

It protects C-4/provider neutrality and makes the missing dependency decision visible and reviewable instead of hiding it in implementation code.

### What must happen next

An architect-approved change must freeze the Gemini SDK/transport, exact compatible version or version policy, retry/timeout ownership, Python 3.14 support, reproducibility expectations, and any unsupported C-4 capability behavior.

---

## OPE-297 — OpenRouter generation and streaming adapter

### What we were supposed to build

An OpenRouter C-4 adapter using only a server-resolved BYOK secret and validated upstream model, with fixed Serviq-owned endpoint behavior, streaming/non-stream normalization, error mapping, and no provider-specific leakage.

### What repository audit found

No OpenRouter transport/client choice is frozen. ADR-011 explicitly excludes OpenRouter dependency approval.

Possible approaches exist, such as reusing an OpenAI-compatible client or using direct HTTP, but the ticket says the transport choice must already be frozen. A builder is not authorized to pick one implicitly.

### What changed

GitHub issue #128 and branch `agent/ope-297-openrouter-adapter` were created.

The branch added:

`docs/architecture-blockers/OPE-297-openrouter-transport-decision.md`

PR #132 passed CI/Security and was squash-merged.

### Why this matters

OpenRouter's endpoint/transport decision is security-sensitive because Serviq must never let a tenant turn provider configuration into arbitrary outbound URL control. The stop preserves server ownership of the destination and keeps transport behavior explicit.

### What must happen next

Freeze the OpenRouter transport, dependency/version if any, immutable base URL, caller-override prohibition, provider header policy, timeout/retry ownership, and Python/reproducibility rules.

---

## OPE-298 — Provider connectivity test endpoint

### What we were supposed to build

`POST /api/v1/providers/{providerConnectionId}/test` should perform one fixed, tiny, bounded provider request using the saved tenant credential and return/store only safe normalized status.

The user must not be able to supply an arbitrary prompt, model, endpoint, or provider body.

### What is already frozen

Architecture already defines the route and these built-in rate limits:

- `provider.test.user`: 10/minute;
- `provider.test.connection`: 30/hour.

The provider table also defines `untested|active|invalid|disabled` status values.

### What repository audit found missing

The ticket requires an architecture-approved minimal model-selection strategy. None is frozen in the current repository.

The Architecture also does not define exact persisted status semantics for temporary provider outcomes such as `429`, timeout, or provider unavailable. Those failures do not prove a credential is invalid, so guessing the transition would make provider status misleading.

OPE-296 and OPE-297 are also blocked, meaning a four-provider connectivity test cannot yet use all supported adapters.

### What changed

GitHub issue #129 and branch `agent/ope-298-provider-connectivity-test` were created.

The branch added:

`docs/architecture-blockers/OPE-298-provider-test-contract-decisions.md`

PR #133 passed CI/Security and was squash-merged.

### What this improves

It prevents a supposedly harmless test endpoint from becoming a free-form completion proxy or from marking healthy credentials invalid because of temporary provider conditions.

### What must happen next

Freeze provider-by-provider test-model selection, whether model configuration is required first, transient status transitions, stable test error codes, API-to-gateway invocation boundaries, and finish Gemini/OpenRouter adapter prerequisites.

---

## OPE-299 — Model configuration CRUD and alias validation

### What we were supposed to build

Tenant-scoped CRUD for stable Serviq model configurations through:

- `GET /api/v1/models`;
- `POST /api/v1/models`;
- `PATCH /api/v1/models/{modelConfigurationId}`;
- `DELETE /api/v1/models/{modelConfigurationId}`.

The table already freezes tenant/provider relationship, alias, upstream model, purpose, enabled state, and tenant-unique alias behavior.

### What repository audit found missing

The ticket requires referenced model configurations to be protected from deletion, including a required test where referenced deletion returns conflict.

But there is currently no implemented/frozen authoritative reference from an agent or another configuration to `model_configurations`:

- no current FK points to the table;
- no `model_configuration_id` is implemented elsewhere;
- `agent_versions` is not implemented yet;
- the planned agent JSON `config` does not freeze a model-reference path or whether identity is UUID versus alias.

Therefore the system cannot truthfully determine whether a model configuration is “referenced” without inventing another module's contract.

### What changed

GitHub issue #130 and branch `agent/ope-299-model-configuration-crud` were created.

The branch added:

`docs/architecture-blockers/OPE-299-model-reference-rules.md`

PR #134 passed CI/Security and was squash-merged.

### Why partial CRUD was rejected

A delete endpoint that succeeds simply because agent references are not implemented yet would create a dangerous future compatibility trap. Inventing a new FK or JSON path would be an unauthorized architecture change. The ticket explicitly says to stop in this situation.

### What this improves

It protects future published/deployed agent configuration from silent model deletion or incompatible mutation.

### What must happen next

Freeze how agents/configurations reference a model, what draft/published/deployed references block deletion, which model fields remain mutable after reference, and the authoritative conflict-check mechanism.

---

## Batch-level result

### Completed in this work

- four separate GitHub issues (#127–#130);
- four separate ticket branches;
- current Linear/repository/Architecture/ADR audit for every ticket;
- detailed `Needs Architect Decision` comments on all four Linear tickets;
- visible blocker status in all four GitHub issues;
- four ticket-specific version-controlled blocker documents;
- four ticket PRs (#131–#134), all passing CI and Security before merge;
- detailed batch guide `docs/OPE_296_299_IMPLEMENTATION_GUIDE.md`;
- this cumulative build-guide reconciliation.

### Not completed and not claimed as completed

- Gemini adapter;
- OpenRouter adapter;
- provider connectivity-test runtime endpoint;
- model configuration CRUD runtime API.

### Why this distinction matters

Serviq's builder rules exist to prevent implementation tickets from quietly changing architecture. Calling these tickets “done” because blocker documentation was merged would be misleading. The correct state is: **investigation and blocker documentation complete; feature implementation blocked pending architect decisions.**

## Recommended unblock order

1. Freeze Gemini SDK and OpenRouter transport decisions.
2. Implement/validate OPE-296 and OPE-297.
3. Freeze provider-test model selection and transient status semantics.
4. Implement/validate OPE-298.
5. Freeze model-reference/mutability rules for agents and other configurations.
6. Implement/validate OPE-299.

Only after actual feature code satisfies each ticket's acceptance tests should GitHub issues #127–#130 and their corresponding Linear tickets be closed.


---

# OPE-296 follow-up — Gemini adapter architecture decision and runtime implementation

> **Status correction to the earlier OPE-296–OPE-299 blocker section:** the earlier section correctly recorded that OPE-296 was blocked at that time. That blocker has now been resolved by ADR-012, and the Gemini runtime adapter has been implemented and validated in PR #137. OPE-297, OPE-298, and OPE-299 are unaffected by this update and keep their previously documented status.

## Why this follow-up exists

The original OPE-296 investigation found that Serviq had no architecture-approved Gemini SDK. The ticket explicitly required implementation to stop in that situation, so the first OPE-296 branch added only the blocker record.

That was the correct state then, but it is no longer the current state.

This follow-up records the complete chain from blocker to implementation so a reader does not have to reconstruct the story from several GitHub issues and pull requests.

The lifecycle is now:

1. OPE-296 was investigated.
2. The explicit `Needs Architect Decision` stop condition was found.
3. The blocker was documented instead of guessed around.
4. An architect decision was researched and written.
5. The architecture PR passed CI and Security and was merged.
6. OPE-296 moved to In Progress.
7. A fresh implementation branch was created from the architecture-approved `main` branch.
8. The Gemini dependency was added as an exact pin.
9. The provider-local adapter was implemented behind C-4.
10. Mocked contract tests were added.
11. The premium security review and a plain-language implementation guide were added.
12. The implementation head passed repository CI and Security before this cumulative documentation finalization.
13. The implementation PR must still pass the final post-documentation run and merge before the ticket is closed.

## Architecture decision that unblocked the ticket

The new decision is:

`docs/architecture-decisions/ADR-012-gemini-sdk-baseline.md`

It was developed on:

`agent/ope-296-gemini-sdk-adr`

and merged through GitHub PR #136.

The architecture PR passed the normal Serviq CI and Security workflows and was squash-merged to `main` as:

`002ec7acabd4c8bc44e6319b181e485c11c89005`

### What ADR-012 freezes

Serviq now explicitly approves:

- Google's official `google-genai` package;
- exact version `google-genai==2.17.0`;
- the Gemini Developer API for this tenant-BYOK adapter;
- Python 3.14 compatibility as a requirement;
- server-resolved provider credentials only;
- no caller-controlled Gemini base URL/project/location/enterprise mode;
- explicit Developer API mode rather than environment-selected enterprise routing;
- C-4 as the only shared request/response contract;
- Serviq-owned timeout and retry policy;
- one provider attempt/no hidden SDK retry loop;
- leading C-4 system messages mapped to Gemini system instructions;
- C-4 `assistant` translated internally to Gemini `model`;
- native JSON Schema structured output when C-4 requests it;
- asynchronous normal and streaming generation;
- the existing five safe C-4 provider error categories;
- mock/fake-only required CI tests;
- a premium security review before the runtime merge.

### Why an ADR was necessary

Choosing a provider SDK is not just a syntax choice. It determines dependency provenance, Python compatibility, streaming behavior, timeout/retry behavior, provider exception types, structured-output capabilities, security review surface, and upgrade responsibility.

OPE-296 was a builder ticket, not an architecture ticket. Resolving that choice separately keeps Serviq's contract discipline real instead of allowing the first implementation to become architecture by accident.

## Runtime implementation branch and PR

The runtime work is on:

`agent/ope-296-gemini-adapter-implementation`

GitHub PR:

`#137 — feat: implement Gemini C-4 adapter for OPE-296`

The branch was created from `main` **after** ADR-012 was merged, so the runtime implementation starts from the architecture-approved state rather than from the old blocked branch.

## Micro-level implementation changes

The work was intentionally committed in small changes so each step can be understood and reviewed independently.

### 1. Add the approved SDK dependency

Commit:

`30fdd497d3dd23eeff29476d362e181beec78189`

Changed:

`services/llm-gateway/pyproject.toml`

Added:

- `google-genai==2.17.0`;
- `httpx==0.28.1`.

`google-genai` is the architecture-approved provider library.

`httpx` is declared directly because production adapter code deliberately recognizes its timeout and transport exception classes. Depending on those classes only through an undeclared transitive dependency would hide a real production dependency.

### 2. Implement the Gemini C-4 adapter

Commit:

`3298a9999e9d8b626b052f3584e03736b726ea8b`

Added:

`services/llm-gateway/app/adapters/gemini.py`

The adapter implements:

- non-stream generation;
- ordered streaming;
- system/user/assistant translation;
- upstream-model forwarding from resolved `AdapterContext` only;
- output-token and timeout forwarding from already validated C-4 values;
- native structured JSON Schema configuration;
- response text/structured normalization;
- input/output token normalization;
- finish-reason normalization;
- provider response ID normalization when supplied;
- auth/rate-limit/timeout/unavailable/invalid-request normalization;
- request-scoped SDK cleanup;
- provider SDK type containment.

### 3. Harden fail-closed behavior and endpoint mode

Commit:

`d8adab21405c88385dbe7692f9f844fad0ec54a9`

This follow-up changed two important security/correctness details.

First, it explicitly builds the Google client with `enterprise=False`.

Why: the Google SDK supports more than one Google AI backend. A tenant BYOK request must not be redirected because of an unrelated machine-level enterprise/Vertex environment variable. This adapter owns one approved mode: Gemini Developer API.

Second, provider-specific message validation now runs **before** the SDK client is created.

Why: if a C-4 message layout cannot be represented safely by Gemini, Serviq should reject it before unnecessarily handing the tenant key to provider client construction.

The commit also uses safe cleanup suppression so a provider-specific cleanup exception cannot replace an already normalized C-4 result.

### 4. Export the new adapter

Commit:

`10faf9914dc54e9c1a5e6a81927c4597487c2063`

Changed:

`services/llm-gateway/app/adapters/__init__.py`

`GeminiAdapter` now follows the same package-level adapter export pattern as OpenAI and Anthropic.

### 5. Add mocked C-4 contract tests

Commit:

`dcff12bfd564cf5669024e067ef45b6f8cf8ca03`

Added:

`services/llm-gateway/tests/test_gemini_adapter.py`

The tests use a fake injected Google client. No required test makes a real Gemini call, requires a real tenant key, spends provider credits, or depends on external Gemini availability.

The coverage verifies:

- non-stream success;
- normalized provider/model/usage/finish/request metadata;
- multiple leading system messages;
- `user -> user` mapping;
- `assistant -> model` mapping;
- conversation order;
- maximum output-token forwarding;
- timeout forwarding;
- one-attempt/no-hidden-retry configuration;
- Developer API mode being forced even if an enterprise environment variable exists;
- structured JSON Schema configuration;
- structured output normalization;
- streaming order;
- streaming whitespace preservation;
- streaming terminal metadata;
- structured streaming;
- authentication failure normalization;
- 429/rate-limit normalization;
- timeout normalization;
- provider outage normalization;
- invalid-request normalization;
- raw provider-error and fake-key redaction;
- late system-message rejection;
- system-only request rejection;
- malformed structured-output rejection;
- missing-key failure;
- wrong-provider context failure;
- wrong stream/non-stream path failure;
- empty-stream failure;
- Serviq-owned return types rather than Google SDK return types.

## Message translation in simple terms

C-4 uses the roles:

- `system`;
- `user`;
- `assistant`.

Gemini uses a separate system instruction plus conversation roles `user` and `model`.

The adapter therefore translates:

| Serviq C-4 | Gemini |
|---|---|
| leading `system` | `system_instruction` |
| `user` | `user` |
| `assistant` | `model` |

Multiple leading system messages keep their order and are joined with a blank line.

A system message appearing after normal conversation has started is not silently moved. The adapter returns `PROVIDER_INVALID_REQUEST` because silently changing message order would change the meaning of the request.

A system-only request also fails explicitly because the selected provider path cannot preserve it as a normal conversation.

## Structured output behavior

When C-4 contains `responseSchema`, the adapter uses Gemini's native JSON structured-output configuration instead of ignoring the schema.

It requests:

- MIME type `application/json`;
- the validated C-4 JSON Schema.

The provider's response text is then parsed into Serviq's own `structured` dictionary before leaving the adapter.

Malformed structured output fails closed rather than being passed downstream as trusted structured data.

During structured streaming, partial JSON fragments are buffered and parsed at completion, then emitted as a C-4 `structuredDelta`.

## Timeout, retry, and cost control

C-4 already validates the maximum provider timeout and maximum output tokens.

The Gemini adapter passes those bounded values to the SDK and configures:

`HttpRetryOptions(attempts=1)`

That prevents the provider library from quietly retrying the generation underneath Serviq.

This is important because hidden retries can:

- increase cost;
- create duplicate generation;
- exceed visible time budgets;
- make telemetry inaccurate;
- interfere with future Serviq-owned retry/fallback logic.

Retry/fallback therefore remains an explicit orchestration responsibility above the provider adapter.

## Safe provider error mapping

Gemini-specific exception objects never become the public error contract.

The adapter maps provider conditions to C-4 as follows:

| Provider condition | C-4 code |
|---|---|
| 401/403 | `PROVIDER_AUTH_FAILED` |
| 429 | `PROVIDER_RATE_LIMITED` |
| timeout / provider 408 | `PROVIDER_TIMEOUT` |
| network failure / provider 5xx | `PROVIDER_UNAVAILABLE` |
| invalid model/schema/request or other applicable provider 4xx | `PROVIDER_INVALID_REQUEST` |

The returned messages are fixed Serviq-authored messages.

The raw Google response body, exception string, headers, SDK stack object, and API key are deliberately discarded at this boundary.

## Premium security review

Added:

`docs/security-reviews/OPE-296-gemini-adapter.md`

The review covers:

- SDK/dependency trust boundary;
- tenant BYOK handling;
- provider-context binding;
- endpoint/enterprise routing control;
- timeout/retry ownership;
- message translation;
- structured output;
- streaming integrity;
- metadata minimization;
- raw provider-error redaction;
- resource cleanup;
- logging exposure;
- mock-only testing.

The conclusion is that Gemini remains an implementation detail behind C-4 rather than becoming a new product-wide trust boundary.

## Blocker record reconciliation

Updated:

`docs/architecture-blockers/OPE-296-gemini-sdk-decision.md`

Its status now records:

**Resolved by ADR-012 and PR #136.**

The original blocker explanation remains useful history: it explains why the first implementation attempt intentionally stopped and what decision was required.

This makes the document an audit trail rather than deleting the old rationale after the problem was solved.

## Detailed plain-language implementation document

Added:

`docs/OPE_296_IMPLEMENTATION.md`

It explains the product problem, architecture decision, request flow, message translation, BYOK handling, endpoint hardening, timeout/retry policy, non-stream behavior, streaming behavior, structured output, error normalization, dependency reasoning, cleanup behavior, tests, security improvements, scope exclusions, and completion gates.

## Validation completed before this build-guide finalization

On implementation head:

`ee1afc6a63bdc85f33025815f6553d0d424c9343`

GitHub CI run #174 completed successfully for:

- dependency installation;
- lint;
- strict type checking;
- full repository tests;
- Compose configuration validation;
- real PostgreSQL database integration/migration checks.

GitHub Security run #150 completed successfully for:

- Gitleaks secret scan;
- Trivy filesystem/configuration scan;
- dependency vulnerability audit;
- CodeQL JavaScript/TypeScript;
- CodeQL Python.

This cumulative documentation update creates a newer PR head, so the final merge still requires the workflows to be green on that final head as well.

## What this improves for Serviq

### Gemini becomes a real C-4 provider

Before this work, `gemini` existed in the provider enum and architecture but lacked the production provider adapter.

The runtime implementation now exists without adding Gemini-specific fields to C-4.

### Agent/domain code stays provider-neutral

The rest of Serviq receives `GatewayResponse`, `GatewayStreamEvent`, `GatewayUsage`, and normalized `GatewayProviderError` objects, not Google SDK objects.

### Tenant keys remain behind the existing secret boundary

OPE-296 does not invent a new secret-storage path. It receives only an already resolved `SecretStr` from the gateway context.

### Provider behavior is bounded

The adapter cannot accept a caller-controlled base URL, enterprise mode, Google Cloud project, or location. C-4 timeout/output-token bounds remain authoritative and hidden retries are disabled.

### Failures are predictable

OpenAI, Anthropic, and Gemini can now surface the same five provider-neutral error categories rather than forcing every caller to understand different SDK exception hierarchies.

### Testing is deterministic and free

Required CI tests do not depend on provider uptime, real keys, or paid generation.

## What OPE-296 intentionally does not include

This ticket does not implement:

- OpenRouter;
- provider connectivity testing;
- model configuration CRUD;
- arbitrary model routing/fallback;
- provider retry orchestration;
- Vertex/enterprise Gemini deployment;
- arbitrary provider base URLs;
- agent runtime changes;
- secret-store changes;
- Gemini-specific C-4 extensions.

Those remain separate architectural/product responsibilities.

## OPE-296 closure gate

At the point this follow-up is appended, the implementation and pre-finalization validation are complete, but the ticket is **not yet considered Done solely because this text exists**.

The final closure sequence is:

1. commit this cumulative build-guide update;
2. run CI and Security on the resulting final PR head;
3. make PR #137 ready for review;
4. merge PR #137 only if those final checks remain green;
5. close GitHub issue #127 as completed;
6. move Linear OPE-296 to Done;
7. record the final merge SHA and closure in the ticket comments.

This preserves the rule used throughout Serviq: documentation can explain completion, but only validated merged runtime code can complete a runtime ticket.


---

# OPE-297 follow-up — OpenRouter generation and streaming adapter

## From architecture blocker to runtime implementation

The earlier OPE-296 through OPE-299 reconciliation correctly recorded OPE-297 as architecture-blocked. At that time Serviq had not frozen which OpenRouter transport was approved or who controlled the upstream endpoint. The ticket explicitly required the builder to stop in that situation, so the first branch documented the blocker rather than quietly selecting a client.

That blocker is now resolved and the runtime feature has been implemented. This follow-up preserves the complete history so a new engineer, product teammate, intern, or non-technical reader can understand how the feature moved from “cannot safely build yet” to a merge-ready implementation.

The lifecycle was:

1. inspect OPE-297 and the existing C-4 provider boundary;
2. identify the missing OpenRouter transport decision;
3. document the stop condition rather than guessing;
4. review OpenRouter's current official API documentation;
5. create a dedicated architecture issue and ADR;
6. merge ADR-013 after CI and Security passed;
7. create a fresh runtime branch from architecture-approved `main`;
8. build a separate `OpenRouterAdapter` behind C-4;
9. add mock/fake-only contract and security tests;
10. handle OpenRouter's special embedded and mid-stream provider errors;
11. reconcile the old blocker document;
12. add a premium security review and plain-language implementation guide;
13. keep strict mypy enabled and fix the dynamic metadata type boundary found by CI;
14. perform final CI/Security validation on the exact merge candidate before closing the ticket.

## Architecture decision — ADR-013

The approved decision is:

`docs/architecture-decisions/ADR-013-openrouter-transport-baseline.md`

Architecture PR #141 passed CI #184 and Security #160, then merged as:

`592136fd02a22976ec87a685436810a89bc9b4fa`

ADR-013 freezes these rules:

- Serviq reuses the already pinned `openai==2.53.0` Python SDK as the OpenRouter transport;
- the protocol surface is OpenAI-compatible Chat Completions;
- the only OpenRouter destination is the Serviq-owned constant `https://openrouter.ai/api/v1`;
- callers, tenants, model configurations, and agent configurations cannot override that endpoint;
- only a server-resolved OpenRouter BYOK secret may reach the adapter;
- only the already validated `AdapterContext.upstream_model` may be sent as the provider model;
- C-4 timeout and output-token limits remain authoritative;
- SDK retries are disabled with `max_retries=0`;
- JSON Schema structured output uses the existing C-4 `responseSchema` contract;
- streaming output remains Serviq-owned `GatewayStreamEvent` data;
- provider failures normalize into the existing five C-4 error categories;
- OpenRouter provider preferences, automatic fallback arrays, plugins, web search, arbitrary headers, and OpenRouter-only C-4 fields remain out of scope;
- required CI tests use mocks/fakes only.

OpenRouter officially supports an OpenAI-compatible API, so reusing Serviq's existing SDK avoids introducing another runtime dependency. The provider still gets its own `OpenRouterAdapter`; it is not an alias for `OpenAIAdapter`, because its endpoint, provider identity, credentials, error wording, and in-band provider-error behavior are different.

## Runtime branch and PR

Runtime branch:

`agent/ope-297-openrouter-adapter-implementation`

Runtime PR:

`#142 — feat: implement OpenRouter C-4 adapter for OPE-297`

The branch was created only after ADR-013 merged.

## Runtime adapter

The main implementation is:

`services/llm-gateway/app/adapters/openrouter.py`

The adapter:

- requires `GatewayProvider.OPENROUTER` context;
- fails closed when the OpenRouter key is missing or blank;
- creates a request-scoped `AsyncOpenAI` client using the fixed OpenRouter base URL;
- disables SDK retries;
- forwards the C-4 timeout and output-token budget;
- sends exactly the resolved upstream model;
- preserves system/user/assistant message order;
- supports non-stream generation;
- supports ordered text streaming while preserving whitespace;
- supports native JSON Schema structured output;
- buffers structured streaming fragments until valid JSON can be normalized;
- normalizes input/output token usage;
- normalizes finish reason and provider request ID where available;
- returns only Serviq-owned C-4 types;
- closes request-scoped client resources after success or failure.

`services/llm-gateway/app/adapters/__init__.py` exports `OpenRouterAdapter` alongside the other providers.

## Fixed destination and SSRF/proxy protection

The most important security property is that a tenant can choose a configured provider and validated model, but cannot choose where Serviq sends network traffic.

The OpenRouter endpoint is a code-owned constant. Contract C-4 has no `baseUrl` or `endpoint` property and rejects unknown request fields.

The tests explicitly attempt to insert both an attacker-controlled web address and a link-local metadata-style endpoint into C-4 input. Validation rejects both.

This protects the gateway from becoming an arbitrary outbound proxy or SSRF-like primitive.

## Validated model ownership

The adapter does not accept a raw upstream model from customer request JSON. Higher-level Serviq model resolution converts `modelAlias` into the validated provider model and puts it in `AdapterContext.upstream_model`.

The adapter sends that exact value. It does not infer a model from prompt text, append OpenRouter variants, construct fallback arrays, choose a cheaper model, or silently substitute another model after failure.

## Non-stream and streaming normalization

Non-stream generation returns a Serviq `GatewayResponse` containing only C-4 fields: content or structured data, provider identity, upstream model, usage, finish reason, and request ID where provided.

Text streaming emits Serviq `GatewayStreamEvent` objects in provider order and preserves leading/trailing whitespace exactly.

Structured streaming buffers JSON fragments, parses the completed provider output, and emits Serviq-owned structured data rather than exposing provider SDK chunks or incomplete JSON as trusted output.

A stream ending without meaningful terminal metadata fails safely.

## OpenRouter embedded and mid-stream failures

OpenRouter can encounter an upstream model-provider failure after generation has already started. Once streaming has begun, the outer HTTP response may already be successful, so the provider can represent the failure inside the completion payload or stream.

OPE-297 explicitly handles this instead of treating OpenRouter as a simple copy of OpenAI.

The adapter reads only the embedded numeric code and stable `error_type` needed for classification. Raw provider messages and metadata bodies are discarded.

The normalized categories remain:

- authentication/permission -> `PROVIDER_AUTH_FAILED`;
- rate limit -> `PROVIDER_RATE_LIMITED`;
- timeout -> `PROVIDER_TIMEOUT`;
- upstream/provider/server failure -> `PROVIDER_UNAVAILABLE`;
- applicable request/model/schema validation failure -> `PROVIDER_INVALID_REQUEST`.

Tests cover a failure arriving after partial streamed text and a non-stream response containing partial output plus an embedded error. In both cases the partial provider output is not returned as a successful completed answer.

## No hidden retries

The request-scoped SDK client sets `max_retries=0`.

This keeps cost, latency, telemetry, and future fallback behavior under Serviq's control. A provider library cannot silently make multiple attempts while the orchestration layer thinks only one provider call happened.

## No new runtime dependency

OPE-297 adds no new package. It reuses the existing exact `openai==2.53.0` dependency.

The LLM Gateway dependency set is already included in Serviq's explicit vulnerability audit, so this shared transport is covered by the Security workflow.

## Test coverage

`services/llm-gateway/tests/test_openrouter_adapter.py` uses injected fake clients and streams only. No required test needs an OpenRouter account, real key, network request, provider availability, or paid API call.

Coverage includes:

- exact fixed base URL;
- retries disabled;
- non-stream success;
- exact validated model forwarding;
- timeout and output-token forwarding;
- role/order preservation;
- arbitrary endpoint rejection;
- structured output;
- ordered text streaming and whitespace preservation;
- terminal usage/finish/request metadata;
- structured streaming;
- auth/rate-limit/timeout/unavailable/invalid-request normalization;
- raw provider error and fake-key containment;
- embedded OpenRouter auth/rate/timeout/unavailable/invalid errors;
- mid-stream failure after partial output;
- non-stream embedded failure after partial output;
- missing-key and wrong-provider fail-closed behavior;
- malformed structured output;
- empty stream;
- provider SDK type containment.

## Premium security review

The complete review is:

`docs/security-reviews/OPE-297-openrouter-adapter.md`

It covers the fixed outbound destination, SSRF/proxy risk, BYOK containment, provider binding, validated model ownership, provider-routing exclusions, timeout/retry ownership, structured output, stream integrity, embedded provider failures, raw error minimization, SDK-type containment, cleanup, dependency security, and mock-only CI testing.

## CI typing finding

The initial runtime CI run found a strict mypy error because dynamically read OpenRouter SDK metadata was inferred as `Any` while an internal helper promised `object | None`.

The fix keeps strict mypy enabled. Dynamic provider metadata is explicitly contained as `object | None` at the adapter boundary before classification. This is safer than weakening type checking or allowing provider-dynamic values to propagate through the gateway.

## Documentation and audit trail

The original blocker file now says:

**Resolved by ADR-013 and GitHub PR #141.**

The detailed implementation explanation is:

`docs/OPE_297_IMPLEMENTATION.md`

The premium security review is:

`docs/security-reviews/OPE-297-openrouter-adapter.md`

This cumulative section connects those detailed artifacts to the overall Serviq build history.

## What OPE-297 intentionally does not add

This ticket does not implement model-configuration CRUD, provider connectivity testing, automatic model fallback, provider preference routing, cheapest-model routing, OpenRouter plugins, web search, arbitrary provider metadata, arbitrary HTTP headers, arbitrary base URLs, agent-runtime changes, secret-store changes, or OpenRouter-specific C-4 extensions.

Those remain separate product and architecture responsibilities.

## Closure gate

This section documents the implementation but does not itself complete the runtime ticket.

OPE-297 becomes Done only after:

1. the temporary append mechanism removes itself and only this permanent guide change remains;
2. CI and Security pass on the exact final PR #142 head;
3. PR #142 is marked ready and merged while that validated head SHA still matches;
4. OpenRouter runtime code and documentation are verified on `main`;
5. GitHub issue #128 is closed as completed;
6. Linear OPE-297 is moved to Done with the final merge and validation record.

That preserves the Serviq rule that validated merged behavior—not documentation alone—completes a runtime ticket.


---

# OPE-298 follow-up — Provider connectivity testing from architecture blocker to production-safe endpoint

> **Status correction to the earlier OPE-298 blocker section:** the earlier section correctly recorded that OPE-298 could not safely be implemented at that time because Serviq had not frozen its test-model strategy or transient failure semantics, and Gemini/OpenRouter adapters were incomplete. Those prerequisites are now resolved. ADR-014 freezes the missing rules, all four provider adapters exist on `main`, and OPE-298 now has a runtime implementation in PR #144. This section preserves both parts of the history instead of rewriting the earlier decision as if the blocker never existed.

## What problem OPE-298 solves in normal language

A Serviq tenant can connect its own AI-provider account by saving a provider API key. For example, a company may connect OpenAI, Anthropic, Gemini, or OpenRouter.

Saving a key and knowing that the key works are two different things.

A key may be:

- mistyped;
- expired or revoked;
- valid but temporarily rate limited;
- valid while the provider is temporarily down;
- valid even though Serviq's chosen health-check model has changed upstream.

A real client therefore needs a **Test connection** action.

The backend route created by OPE-298 is:

```text
POST /api/v1/providers/{providerConnectionId}/test
```

When an authorized administrator uses this route, Serviq performs one tiny, server-controlled AI-provider request and stores a safe health result.

The important phrase is **server-controlled**.

We deliberately did not build a route where the browser can say:

```text
Use this model
Send this prompt
Use this provider URL
Return 5,000 tokens
Retry several times
```

If we allowed that, a health-check endpoint would quietly become another model-completion API. That would make security, cost control, model governance, and auditing harder.

The OPE-298 route answers only one question:

> Can the provider connection that this tenant already saved complete Serviq's tiny approved connectivity check right now?

## Why the earlier implementation correctly stopped

The first OPE-298 investigation already knew the route and the two rate-limit numbers, but important rules were not frozen.

### Missing decision 1: which model should a health check use?

The repository supported multiple providers, but it did not say which upstream model Serviq should use for a provider test.

Hard-coding a random model inside feature code would be dangerous. If that model later disappeared, the UI could incorrectly imply that the tenant's API key was broken.

It was also unclear whether a tenant had to create a normal model configuration before testing the provider. That would create an awkward onboarding loop: a client would need a model configuration to test whether the underlying provider connection worked.

### Missing decision 2: what does a temporary provider failure do to stored status?

Serviq already had these provider states:

```text
untested
active
invalid
disabled
```

But the architecture had not yet answered whether a timeout, provider outage, or rate limit should change a connection to `invalid`.

That question matters because a temporary upstream problem does not prove that the tenant's credential is wrong.

### Missing prerequisite 3: not every supported provider adapter was ready

At that earlier point, Gemini and OpenRouter were still waiting for their own adapter/transport decisions. A four-provider health feature implemented for only two providers would have created an inconsistent product.

The correct engineering action was therefore to stop, document the blocker, and resolve the architecture first.

That is exactly what happened.

## ADR-014 resolves the missing rules

The architecture decision is:

`docs/architecture-decisions/ADR-014-provider-connectivity-test-semantics.md`

ADR-014 was merged before the runtime implementation branch was created.

It freezes four major ideas:

1. the browser cannot control the model, prompt, provider URL, headers, timeout, or token budget;
2. Serviq owns a small health-check model for every supported provider;
3. temporary provider failures preserve the connection's existing status instead of falsely proving the credential invalid;
4. the provider call happens outside the database transaction, with a second safety check before the result is written.

This is why the runtime branch is not just “add one POST endpoint.” It implements a state, security, cost, and concurrency contract.

## The server-owned health-check models

The LLM Gateway owns this mapping:

| Provider | Connectivity-test model |
|---|---|
| OpenAI | `gpt-5-nano` |
| Anthropic | `claude-haiku-4-5-20251001` |
| Gemini | `gemini-3.5-flash-lite` |
| OpenRouter | `openrouter/free` |

A tenant cannot override these through the `/test` request.

These test models are also independent of the tenant's normal model aliases.

That separation is useful because the provider connection is lower-level infrastructure. We should be able to prove that the provider credential works before asking the tenant to build the rest of its model configuration.

If a health-check model needs to change later, we change the architecture-owned mapping and its tests. We do not expose a free-form model field to the browser.

## The exact provider request is intentionally tiny

Every connectivity test uses the same basic request shape:

```text
One user message: "Reply with OK."
Maximum output: 4 tokens
Provider timeout: 5 seconds
Streaming: false
OPE-298 retry loop: none
```

A token is a small unit of model text. Four output tokens are enough for this administrative check.

The provider's generated words are not used as business content. The gateway discards them.

A successful normalized response is enough to demonstrate that:

- Serviq resolved the credential;
- the provider accepted the authentication;
- the adapter can translate the request;
- the selected small model path is reachable.

The public API does not return provider-generated content, usage, raw headers, provider request IDs, or provider response bodies.

## Why the public request has no body

The public route takes the provider connection ID from the URL and nothing else.

If a caller sends a non-empty JSON body, Serviq rejects it.

For example, this is rejected:

```json
{
  "model": "something-expensive",
  "prompt": "write a long report",
  "baseUrl": "https://another-server.example"
}
```

We chose explicit rejection instead of silently ignoring those fields.

Why?

Because silently ignoring a `model` field makes the contract ambiguous. A caller may believe the field controls the request even though it does not. Explicit rejection makes the security boundary obvious and testable.

## Authorization stays tenant-safe

The connectivity endpoint reuses the existing permission:

```text
ai.providers.manage
```

The workflow first checks that the current workforce user has the required access for the current tenant.

The provider lookup is scoped by:

```text
tenant ID + provider connection ID
```

If tenant A sends the ID of a provider connection belonging to tenant B, Serviq does not reveal:

> "Yes, this provider exists, but it belongs to another company."

Instead it follows the same safe not-found behavior.

The real PostgreSQL integration test creates two tenants to verify that this is not just an assumption in code review.

## The stored API key never comes from the `/test` request

A provider connection stores a `secret_ref`, not the intended plaintext API key in the normal provider row.

The flow is conceptually:

```text
Browser
   |
   | POST /providers/<id>/test
   v
Serviq API
   |
   | tenant-scoped provider lookup
   v
provider_connections row
   |
   | secret_ref
   v
Tenant secret store
   |
   | plaintext key exists briefly in server memory
   v
Private LLM-Gateway request
```

The client does not resend the stored API key just to test it.

This reduces accidental key exposure and keeps secret retrieval inside the server trust boundary.

## Why the API talks to a private LLM-Gateway route

Serviq's public API should not become a second home for OpenAI, Anthropic, Gemini, and OpenRouter SDK logic.

Those provider-specific adapters already live behind the LLM Gateway and Contract C-4.

OPE-298 therefore adds a narrow service-to-service path:

```text
POST /internal/v1/provider-connectivity-test
```

The private request contains only server-resolved administrative context:

```text
tenant ID
stored provider enum
resolved API key
server-generated correlation ID
```

It deliberately does not carry:

```text
caller model
caller prompt
caller base URL
caller timeout
caller token budget
caller headers
```

The LLM Gateway constructs the fixed health request itself.

This preserves the architectural rule that provider SDK knowledge stays in the gateway instead of spreading through the API service.

## Private gateway authentication

The private route is not anonymous.

It requires Serviq's existing internal bearer credential:

```text
LLM_GATEWAY_INTERNAL_TOKEN
```

The gateway uses a constant-time comparison for the supplied and expected token.

In simple terms, a constant-time comparison is a secret-comparison method designed not to leak useful information based on how early two strings differ.

The private route fails closed if the expected internal token is not configured.

Production infrastructure must still protect API-to-gateway traffic with the normal private-network/TLS rules because the server-resolved provider credential necessarily crosses that service boundary in memory/on the protected internal connection.

## Why OPE-298 adds Valkey to the API dependency set

The architecture already defined these provider-test rate limits:

```text
provider.test.user       = 10 requests / minute
provider.test.connection = 30 requests / hour
```

A rate limit restricts how often an operation can be performed.

This matters even though the provider request is tiny because repeated tests still consume external provider capacity and can create noise or cost.

A simple Python dictionary would not be production-safe.

Imagine three API workers:

```text
Worker 1 thinks user count = 8
Worker 2 thinks user count = 7
Worker 3 thinks user count = 9
```

Each process has a different local memory. The user can exceed the intended total limit just by requests landing on different workers.

OPE-298 therefore uses Serviq's shared Valkey infrastructure.

Valkey is an in-memory data store used here so every API worker sees the same rate-limit state.

The API now declares the Valkey Python client as a runtime dependency and refreshes the frozen `services/api/uv.lock`. On the repository CI environment this resolves `valkey==6.1.1` for Python 3.14.6.

## Both rate limits are consumed atomically

OPE-298 does not perform this unsafe sequence:

```text
read user counter
read connection counter
decide
increment user counter
increment connection counter
```

Two workers could race between those steps.

Instead, one Valkey script performs the complete decision:

1. read the user count;
2. read the provider-connection count;
3. reject if either is already exhausted;
4. otherwise increment both;
5. set their expiration windows when needed;
6. return a retry-after value on rejection.

This is called an **atomic** decision because concurrent workers cannot interleave separate check-and-increment steps in a way that grants the same remaining allowance twice.

The rate-limit keys contain tenant/user/connection identifiers. They do not contain API keys.

## The limiter fails closed

If Valkey is unavailable or returns malformed data, Serviq does not say:

> "Our safety counter is broken, so go ahead and call the provider anyway."

It returns a safe:

```text
PROVIDER_TEST_UNAVAILABLE
```

and does not invoke the provider.

This is called **failing closed**.

For an externally charged or capacity-consuming action, failing open would make the endpoint unlimited precisely while the protection layer is broken.

## Two different kinds of rate limiting are kept separate

There are two distinct situations:

### Serviq rate limit

Serviq blocks the request before a provider call because the administrator has used the health endpoint too often.

Result:

```text
HTTP 429
PROVIDER_TEST_RATE_LIMITED
Retry-After header
```

No provider metadata is changed because no provider test happened.

### Provider rate limit

Serviq allowed the test, called the upstream provider, and that provider responded with a rate-limit condition.

Normalized result:

```text
PROVIDER_RATE_LIMITED
```

This counts as a connectivity attempt, so Serviq records the attempt timestamp/error code while preserving the connection's previous status.

Keeping these concepts separate gives the UI and operators a truthful explanation of where the limit occurred.

## The status state machine

The provider connection has four possible statuses:

```text
untested
active
invalid
disabled
```

OPE-298 gives these states precise connectivity-test behavior.

### Success

On a successful provider response:

```text
status = active
last_tested_at = now
last_error_code = null
```

### Authentication failure

If the provider explicitly rejects authentication:

```text
PROVIDER_AUTH_FAILED
```

Serviq stores:

```text
status = invalid
last_tested_at = now
last_error_code = PROVIDER_AUTH_FAILED
```

This is the one provider-test failure that proves the tested credential is not usable for the approved request.

### Provider rate limit

For:

```text
PROVIDER_RATE_LIMITED
```

Serviq records the attempt but preserves the previous status.

A rate limit does not prove the credential is wrong.

### Timeout

For:

```text
PROVIDER_TIMEOUT
```

Serviq records the attempt but preserves the previous status.

A slow or temporarily unreachable provider does not prove the credential is wrong.

### Provider unavailable

For:

```text
PROVIDER_UNAVAILABLE
```

Serviq records the attempt but preserves the previous status.

### Provider invalid request

For:

```text
PROVIDER_INVALID_REQUEST
```

Serviq also preserves the previous status.

This may seem surprising, but the health-check model/prompt are Serviq-owned. If Serviq's selected test model is no longer accepted by the provider, that is not proof that the client's API key is bad.

This distinction prevents false `invalid` states in the client console.

## Disabled connections do not get reactivated by testing

A connection already marked:

```text
disabled
```

is not sent to the provider.

Serviq does not:

- spend a provider request;
- consume the health-test rate limiter;
- resolve its secret;
- reactivate it.

The endpoint returns safe disabled status.

The second database phase also checks for a connection that became disabled while a test was in flight, so the completed test does not override the later administrative decision.

## Why the provider call is outside a database transaction

An AI-provider call is a network operation. Networks can be slow or fail.

Holding a PostgreSQL transaction or row lock while waiting several seconds can cause:

- blocked updates;
- longer lock queues;
- exhausted database connections;
- cascading latency during provider incidents.

OPE-298 instead uses two short database phases.

### Phase 1 — short read/authorization transaction

Serviq:

1. validates the tenant/user permission;
2. reads the tenant-scoped provider connection;
3. checks whether it is disabled;
4. captures the provider enum and current `secret_ref`;
5. closes the transaction.

### Between transactions — external work

Serviq:

1. enforces Valkey rate limits;
2. resolves the captured secret;
3. calls the private LLM Gateway/provider.

No database transaction is kept open while this happens.

### Phase 2 — short locked persistence transaction

Serviq:

1. locks the provider row;
2. checks that the provider and `secret_ref` still match the values that were tested;
3. applies the safe status/timestamp/error update;
4. commits.

This gives us short database transactions without sacrificing concurrency correctness.

## The key-rotation race that a simple implementation would miss

Consider this real-world timing problem:

```text
12:00:00  Health test starts with key A
12:00:01  Administrator replaces key A with key B
12:00:02  Provider says key A worked
12:00:02  Old health request tries to store "active"
```

If Serviq simply stores `active`, the UI now says key B is tested and active even though only key A was tested.

OPE-298 protects against this.

Before the external call it remembers the tested `secret_ref`.

After the call, with the row locked, it asks:

> Does the current provider record still point at the exact credential reference I tested?

If yes, the result is current.

If no, the result is stale and Serviq returns:

```text
PROVIDER_TEST_STALE
```

without applying the old result.

The real PostgreSQL integration test deliberately rotates the credential from a second database session while the fake provider request is in progress. It verifies that the new credential remains `untested` and receives no old timestamp/error.

This is one of the strongest production-readiness improvements in OPE-298 because it prevents a rare race from creating false trust metadata.

## Safe error vocabulary instead of raw provider text

Provider SDKs and HTTP responses can contain long, provider-specific, or sensitive error messages.

OPE-298 does not save or return those bodies.

Provider outcomes use the existing C-4 categories:

```text
PROVIDER_AUTH_FAILED
PROVIDER_RATE_LIMITED
PROVIDER_TIMEOUT
PROVIDER_UNAVAILABLE
PROVIDER_INVALID_REQUEST
```

Serviq's own administrative/control failures use separate safe codes such as:

```text
PROVIDER_NOT_FOUND
FORBIDDEN
PROVIDER_TEST_RATE_LIMITED
PROVIDER_TEST_UNAVAILABLE
PROVIDER_TEST_STALE
```

This helps the UI explain the difference between:

- bad provider authentication;
- provider outage;
- upstream provider rate limiting;
- Serviq's own health-test rate limiting;
- Serviq health infrastructure being unavailable;
- a concurrent credential rotation.

Raw provider bodies are not a browser contract and are not stored in `last_error_code`.

## What the private gateway returns

The private gateway intentionally returns only:

```json
{
  "ok": true,
  "errorCode": null
}
```

or a normalized failure code.

Even when the provider produces generated text, the health route discards it.

Tests deliberately make the fake adapter produce a sentence and a provider request ID, then verify that neither appears in the private health response.

This stops the health-check path from slowly evolving into an inference path.

## Production boundary tests added beyond the PostgreSQL integration test

The PostgreSQL test intentionally uses fake provider/gateway dependencies so CI never needs real provider credentials.

That leaves two production-only boundaries that deserve their own tests.

### API-to-LLM-Gateway HTTP client test

`services/api/tests/test_provider_connectivity_gateway.py` uses `httpx.MockTransport`.

It verifies:

- the exact internal path;
- the internal bearer Authorization header;
- the private JSON contains only tenant/provider/key/correlation ID;
- no model/prompt/base URL is sent;
- a raw HTTP 500 body containing fake sensitive text is discarded;
- a timeout becomes only `PROVIDER_TIMEOUT`;
- the timeout is not retried by OPE-298.

### Valkey limiter test

`services/api/tests/test_provider_test_rate_limits.py` uses a fake Valkey `eval` client.

It verifies:

- both frozen limits are evaluated in one script;
- exact `10`, `30`, `60`, and `3600` values;
- tenant/user/connection scoped keys;
- no API key appears in rate-limit keys;
- `Retry-After` information survives a denial;
- Valkey connection errors fail closed;
- malformed Valkey responses fail closed.

This gives meaningful coverage without depending on a live external model provider or a separate Valkey service in the PostgreSQL CI job.

## Real PostgreSQL integration behavior covered

`services/api/tests/integration/test_provider_connectivity_api.py` uses the repository's real PostgreSQL integration environment.

It verifies the complete business state machine:

1. success marks the provider active;
2. authentication failure marks it invalid;
3. provider rate limit preserves active status;
4. timeout preserves active status;
5. provider unavailable preserves active status;
6. provider invalid-request preserves active status;
7. safe timestamps/error codes are stored;
8. arbitrary public body is rejected before provider invocation;
9. Serviq rate-limit denial prevents provider invocation;
10. rate-limit infrastructure failure prevents provider invocation;
11. disabled provider is not invoked;
12. concurrent key rotation causes a stale conflict and does not stamp the replacement key;
13. another tenant's provider ID remains non-disclosing;
14. same-tenant user without `ai.providers.manage` is forbidden;
15. the fake provider key does not appear in the public response, encrypted local secret file, or captured logs.

## Why CI uses fake provider calls

We deliberately do not require real OpenAI, Anthropic, Gemini, or OpenRouter API keys in CI.

Live-provider tests would be:

- slower;
- flaky when the internet/provider is unavailable;
- potentially chargeable;
- dangerous because real API keys would need to exist in the CI environment;
- difficult to reproduce exactly.

Instead, OPE-298 tests the adapter/gateway contracts deterministically with fakes/mocks and tests the database behavior against real PostgreSQL.

This gives stable evidence without external secrets.

## Files changed by OPE-298

### Architecture/audit

`docs/architecture-decisions/ADR-014-provider-connectivity-test-semantics.md`

Freezes the formerly missing decisions.

`docs/architecture-blockers/OPE-298-provider-test-contract-decisions.md`

Preserves the original stop history and now explains why it is resolved.

### LLM Gateway

`services/llm-gateway/app/connectivity.py`

Adds private schemas, internal authentication, server-owned model mapping, fixed request construction, adapter selection, and normalized response.

`services/llm-gateway/app/main.py`

Registers the new private route.

`services/llm-gateway/tests/test_provider_connectivity.py`

Covers model mapping, fixed request, internal auth, extra-field rejection, generated-content suppression, and provider error normalization.

### API

`services/api/app/core/rate_limits.py`

Replaces the provider-test limiter placeholder with shared Valkey-backed atomic enforcement.

`services/api/app/modules/providers/gateway.py`

Adds the narrow internal HTTP client to the LLM Gateway.

`services/api/app/modules/providers/router.py`

Adds the public `/test` route, public-body rejection, dependencies, and HTTP error mapping.

`services/api/app/modules/providers/service.py`

Adds permission checks, two-phase database behavior, secret resolution, external call, stale credential guard, and safe state persistence.

`services/api/app/modules/providers/schemas.py`

Adds the small browser-safe connectivity result and error-code type.

`services/api/app/modules/providers/errors.py`

Adds stable provider-test control-plane exceptions.

`services/api/pyproject.toml`

Adds the Valkey Python client.

`services/api/uv.lock`

Freezes the resolved dependency graph.

### Tests

`services/api/tests/integration/test_provider_connectivity_api.py`

Real PostgreSQL business/integration coverage.

`services/api/tests/test_provider_connectivity_gateway.py`

Mock transport coverage of the real API-to-gateway client.

`services/api/tests/test_provider_test_rate_limits.py`

Unit coverage of shared atomic limiter behavior.

### Documentation/security

`docs/OPE_298_IMPLEMENTATION.md`

Detailed plain-language implementation explanation.

`docs/security-reviews/OPE-298-provider-connectivity-test.md`

Adversarial security/reliability review.

## What OPE-298 intentionally does not build

This ticket does not add:

- general chat/completion behavior;
- caller-selected provider models;
- caller-selected prompts;
- arbitrary provider/base URLs;
- automatic provider failover;
- scheduled provider monitoring;
- background health tests;
- model-configuration CRUD;
- published-agent model-reference rules;
- new provider SDKs;
- general C-4 HTTP routing for every agent request.

Those are separate architecture/product responsibilities and should not be hidden inside a provider health endpoint.

## What this changes for a real Serviq client

For a real company using Serviq, provider setup can now become a trustworthy workflow rather than a blind save operation.

An administrator can:

1. save the company's provider API key through the existing provider-management flow;
2. click/test the stored connection without resending that key from the browser;
3. receive a clear status;
4. distinguish invalid credentials from temporary upstream problems;
5. avoid unlimited repeated tests because the action is rate limited;
6. rotate credentials safely without an old in-flight result marking the new key active;
7. rely on the same public workflow for OpenAI, Anthropic, Gemini, and OpenRouter.

This moves Serviq closer to a client-ready control plane where administrators can understand and trust the state of their AI-provider integrations.

## Premium security review

The full adversarial review is:

`docs/security-reviews/OPE-298-provider-connectivity-test.md`

It checks:

- free-form model proxy risk;
- arbitrary endpoint/SSRF risk;
- BYOK credential containment;
- tenant isolation and RBAC;
- shared abuse/cost controls;
- temporary outage vs credential-invalid semantics;
- stale key-rotation races;
- database lock duration;
- raw provider error leakage;
- hidden retries;
- disabled-state protection;
- private gateway authentication;
- observability/logging boundaries;
- fake-only provider CI;
- Valkey dependency/security audit coverage.

## Closure gate

This section records the implementation and the reasons behind it, but OPE-298 is not considered Done merely because documentation exists.

The runtime ticket becomes complete only when:

1. the temporary build-guide append helper removes itself, leaving this section in the permanent guide;
2. the final runtime PR #144 head passes strict lint and mypy;
3. all unit and real PostgreSQL integration tests pass;
4. Compose/migration validation passes;
5. the Security workflow passes Gitleaks, Trivy, CodeQL, and dependency audits on the exact final head;
6. PR #144 is marked ready and merged from that validated head;
7. the merged files are verified on `main`;
8. GitHub issue #129 is closed as completed;
9. Linear OPE-298 is moved to Done with the final merge/validation record.

This preserves the Serviq rule used on the previous provider tickets: **validated merged runtime behavior, not documentation alone, completes the ticket.**

---

# OPE-299 — Model configuration CRUD and stable aliases

**Status:** Completed. Runtime implementation was validated and merged through PR #145. The model-management contract is frozen by ADR-015.

## What OPE-299 adds

OPE-299 gives each Serviq tenant a safe model catalog instead of forcing future agents to store raw provider model names everywhere.

A tenant can now define a stable Serviq model configuration such as:

```text
alias = support-primary
purpose = generation
provider connection = approved OpenAI connection
upstream model = gpt-5-mini
```

The important idea is that `support-primary` belongs to Serviq and the tenant. The raw provider model name belongs to the upstream AI provider. Keeping those concepts separate means future agent configuration can depend on a stable Serviq identity while the provider or upstream model can change behind that identity in a controlled way.

A non-technical analogy is a phone contact. People use the saved contact name instead of memorizing the current phone number. If the number changes, the contact can be updated once. Model aliases provide the same kind of indirection for AI infrastructure.

## Why this ticket had previously stopped

The `model_configurations` table already existed, so basic CRUD would have been straightforward. The unsafe part was deletion.

The ticket requires Serviq to refuse deletion when production configuration still depends on a model. Earlier, the repository did not have an authoritative way to answer that question. The future agent-version JSON shape had not frozen an exact model-reference path, and inventing one inside OPE-299 would have coupled model management to architecture owned by another module.

The earlier implementation therefore stopped with a `Needs Architect Decision` record rather than pretending deletion was safe.

## ADR-015 resolves the blocker

`docs/architecture-decisions/ADR-015-model-configuration-reference-and-mutation-semantics.md` freezes the missing rules.

The approved behavior is:

- model configuration UUID is the authoritative internal identity;
- `alias` is immutable after creation;
- `purpose` is immutable after creation;
- `providerConnectionId`, `upstreamModel`, and `enabled` are PATCH-mutable;
- creation requires a provider connection that belongs to the same tenant and is currently `active`;
- changing provider, changing upstream model, or enabling a model also requires an active provider;
- disabling remains allowed even if a provider later becomes unhealthy, because disabling is the safe action;
- foreign-tenant identifiers are handled without disclosing that the foreign resource exists;
- deletion is protected by an explicit relational reference registry rather than by parsing another module's JSON.

## The model reference registry

The migration adds:

```text
model_configuration_references
```

This table is a small “something important is using this model” register. It records:

```text
tenant_id
model_configuration_id
reference_kind
reference_id
created_at
```

A future published agent-version workflow can register a blocking dependency when that agent version becomes production-relevant. When an administrator later tries to delete the model, OPE-299 asks the database whether a blocking reference exists.

```text
No blocking reference -> deletion may continue
Blocking reference exists -> 409 MODEL_CONFIGURATION_IN_USE
```

The database uses a tenant/model composite foreign key so a malformed internal write cannot claim that one tenant references another tenant's model UUID.

Future modules own their own lifecycle. They register or remove blocking rows in the same transaction in which their production reference becomes active or inactive. Model management therefore does not need to know the internal JSON layout of agents or future configuration domains.

## Why alias and purpose are immutable

The alias is supposed to be stable. Letting ordinary PATCH rename `support-primary` would make historical logs, audits, configuration reviews, and future alias-based references harder to understand.

Purpose is even more semantic. Turning a `generation` configuration into an `embedding` configuration changes what the resource means. Downstream code expecting generated text should not suddenly receive a vector-model configuration.

OPE-299 therefore freezes:

```text
Immutable after create:
- alias
- purpose

PATCH-mutable:
- providerConnectionId
- upstreamModel
- enabled
```

A future rename or purpose-migration workflow can be designed explicitly if the product needs one.

## Why the provider must be active

Provider connections can be `untested`, `active`, `invalid`, or `disabled`. OPE-298 added the connectivity-test path that can prove a stored credential works and mark the connection active.

A new model configuration should not appear usable while pointing at an untested, invalid, or disabled provider. OPE-299 therefore requires an active same-tenant provider for creation.

The same rule applies when changing the provider, changing the upstream model, or setting `enabled=true`.

There is one intentional fail-safe exception. Setting `enabled=false` remains allowed when the current provider is unhealthy. Administrators must always be able to turn unsafe configuration off.

## Routes implemented

The API now exposes the frozen model-management surface:

```text
GET    /api/v1/models
POST   /api/v1/models
PATCH  /api/v1/models/{modelConfigurationId}
DELETE /api/v1/models/{modelConfigurationId}
```

### GET `/api/v1/models`

Returns only model configurations owned by the current tenant.

### POST `/api/v1/models`

Creates a configuration using:

```text
providerConnectionId
alias
upstreamModel
purpose
enabled
```

Validation includes:

- alias is trimmed before validation and must be 1 to 80 characters;
- upstream model is trimmed before validation and must be 1 to 160 characters;
- purpose must be exactly `generation`, `embedding`, or `rerank`;
- provider connection must exist inside the current tenant and be active;
- unknown fields are rejected;
- `enabled` defaults to true when omitted.

### PATCH `/api/v1/models/{modelConfigurationId}`

Only these fields are accepted:

```text
providerConnectionId
upstreamModel
enabled
```

An empty PATCH is rejected. `alias` and `purpose` are rejected because they are intentionally immutable.

### DELETE `/api/v1/models/{modelConfigurationId}`

The service locks the model row, checks the blocking-reference registry, and then either returns a stable conflict or deletes the unreferenced row.

```text
Referenced -> HTTP 409 MODEL_CONFIGURATION_IN_USE
Unreferenced -> HTTP 204
```

There is no cascade that silently rewrites or deletes production configuration.

## Tenant-unique aliases

The database enforces:

```text
UNIQUE(tenant_id, alias)
```

Two aliases named `support-primary` inside one tenant conflict and return `409 MODEL_ALIAS_CONFLICT`.

Two different tenants can both use `support-primary` because their catalogs are isolated.

The database constraint is also the final protection if concurrent requests race to create the same tenant alias.

## Tenant isolation and non-disclosure

Every model lookup used for mutation includes the current tenant ID and the requested model UUID. Every provider lookup used by model CRUD includes the current tenant ID and provider UUID.

Knowing a UUID is not authorization. If Tenant A submits a provider or model UUID belonging to Tenant B, the API does not reveal Tenant B's ownership or configuration details.

## Authorization

Model management uses the existing capability:

```text
ai.providers.manage
```

A tenant member without that capability cannot list or mutate model configurations through this management API.

## Credentials never enter model responses

Model responses contain only safe metadata:

```text
id
providerConnectionId
alias
upstreamModel
purpose
enabled
createdAt
updatedAt
```

They do not return API keys, `secretRef`, raw provider responses, provider headers, provider SDK objects, or provider exception details.

Provider credentials remain inside the provider/BYOK control plane. Model aliases remain a separate abstraction.

## Backend structure

The implementation follows Serviq's existing service boundaries:

```text
HTTP request
   |
   v
model_router.py
   |
   v
service.py
   |
   v
repository.py
   |
   v
PostgreSQL
```

`model_router.py` owns HTTP transport and safe status/error mapping.

`schemas.py` owns strict request and response validation.

`service.py` owns authorization, mutability, provider eligibility, transaction boundaries, and deletion protection.

`repository.py` owns tenant-scoped SQLAlchemy persistence operations.

`models.py` maps database tables.

The Alembic migration owns the reference-registry database change.

## Concurrency protection

PATCH and DELETE lock the target model row before making their final decision. Safety-sensitive provider checks also lock the selected provider connection.

These are short database transactions with no external model/provider request inside them. The goal is to prevent stale-state decisions without holding database locks during slow network work.

## Automated validation

The real PostgreSQL integration suite covers:

- generation alias creation;
- embedding alias creation;
- rerank alias creation;
- whitespace normalization;
- same-tenant duplicate alias conflict;
- the same alias in another tenant;
- blank and oversized alias rejection;
- blank and oversized upstream-model rejection;
- invalid purpose rejection;
- unknown field rejection;
- foreign-provider non-disclosure;
- disabled and untested provider rejection;
- tenant list isolation;
- authorized updates of mutable fields;
- rejection of alias and purpose PATCH;
- rejection of empty PATCH;
- fail-safe disabling;
- rejection of re-enabling against an inactive provider;
- foreign-model non-disclosure;
- unauthorized list/update/delete behavior;
- referenced-delete conflict;
- unreferenced-delete success;
- absence of provider credential fields in model responses.

The migration is also exercised through clean upgrade, downgrade, re-upgrade, and full-chain downgrade in CI.

## Exact runtime validation

Before the runtime stage was merged, exact head:

```text
0fc1bfd0922175193e3857afb6a16cb6ea0e91ed
```

passed:

- CI #236, including lint, strict type checking, tests, Compose validation, PostgreSQL integration tests, and migration reversibility;
- Security #212, including Gitleaks, Trivy, CodeQL for Python and JavaScript/TypeScript, and dependency vulnerability audits.

The runtime stage was merged as PR #145. Detailed evidence is also recorded in `docs/validation/OPE-299-runtime-validation.md`.

## Main implementation files

```text
docs/architecture-decisions/ADR-015-model-configuration-reference-and-mutation-semantics.md
docs/architecture-blockers/OPE-299-model-reference-rules.md
docs/validation/OPE-299-runtime-validation.md
services/api/alembic/versions/20260819_0007_model_configuration_references.py
services/api/app/modules/providers/models.py
services/api/app/modules/providers/repository.py
services/api/app/modules/providers/schemas.py
services/api/app/modules/providers/errors.py
services/api/app/modules/providers/service.py
services/api/app/modules/providers/model_router.py
services/api/app/main.py
services/api/tests/integration/test_model_configuration_crud_api.py
services/api/tests/integration/test_database_integration.py
```

## What OPE-299 deliberately does not add

This ticket does not implement provider API-key rotation, provider connectivity testing, fallback chains, agent publishing/deployment, the future agent configuration schema, provider SDK selection, alias renaming, purpose migration, or automatic migration of future agent configuration.

Those responsibilities remain in their own architecture and ticket boundaries.

## What improves after OPE-299

Before this work, Serviq had model-configuration database rows but not a complete production-safe tenant management API around them.

After OPE-299, Serviq has a stable tenant model catalog with strict validation, tenant isolation, permission checks, active-provider eligibility, credential-free responses, deterministic conflicts, controlled mutation, and real reference-aware deletion.

The larger product improvement is decoupling. Future agents can depend on a Serviq-owned model identity while credentials stay in the provider control plane and provider-specific execution stays behind the LLM Gateway. Upstream models can evolve without forcing every domain object to understand provider naming conventions.


---

# OPE-300 — Knowledge source, document, and chunk schema

**Status:** Implemented on branch `ope300`. This section is part of the implementation branch and the ticket is closed only after the final branch head passes the repository's required CI and PostgreSQL integration checks.

## What problem this ticket solves

Serviq is designed to answer customer questions from company-approved information rather than from an AI model's memory alone. Before OPE-300, the product architecture described that knowledge system, but PostgreSQL did not yet have the durable tables needed to store where knowledge came from, which version of a document was ingested, or which text chunks are searchable.

OPE-300 creates that database foundation.

A simple way to think about the three new tables is:

```text
knowledge source
    |
    v
versioned document
    |
    v
searchable chunks
```

For example, a company might add a public refund-policy URL. That URL is the **source**. Serviq fetches a particular version of the page and records it as a **document**. The document is then divided into smaller **chunks** that a later retrieval system can search and cite.

The ticket deliberately stops at persistence and lexical search. It does not build the crawler, file uploader, chunking worker, knowledge API, embeddings pipeline, or retrieval API.

## The migration added

The new Alembic revision is:

```text
services/api/alembic/versions/20260819_0008_knowledge_schema.py
```

It follows revision `20260819_0007` and creates the tables in dependency order:

1. `knowledge_sources`;
2. `knowledge_documents`;
3. `knowledge_chunks`.

The downgrade removes them in the reverse order so foreign-key dependencies are never torn down out of sequence.

All three are mutable architecture-owned tables, so they follow the shared Serviq database convention of UUIDv7 primary keys plus `created_at` and `updated_at` timestamps.

## `knowledge_sources`: where approved knowledge comes from

`knowledge_sources` stores the top-level origin of a knowledge collection.

The source type is restricted by the database to exactly:

```text
url
sitemap
pdf
markdown
text
```

This means later code cannot silently invent values such as `website`, `docx`, or `notion` and persist them without an architecture change.

The table also stores:

```text
tenant_id
name
source_uri
object_key
access_scope
status
sync_version
last_synced_at
last_error_code
created_by
```

### Why both `source_uri` and `object_key` exist

A URL or sitemap is fetched from a network address, so those source types require `source_uri`.

A PDF, Markdown file, or text file is represented by an object-storage location, so those file source types require `object_key`.

The database enforces that rule itself. A URL without a URI is rejected. A PDF without an object key is rejected. The application cannot bypass the requirement accidentally by forgetting validation in one code path.

The migration does **not** add a raw credential field. If a future private-source design needs authentication, that requires a separate security and architecture contract rather than placing passwords or API tokens in the knowledge-source row.

## Explicit customer versus internal scope

Every source must declare:

```text
customer
```

or:

```text
internal
```

There is no null value that means "guess the scope later."

This matters because a future retrieval system needs to know whether a piece of knowledge is safe to use in a customer-facing answer or is restricted to employees/internal workflows. OPE-300 only stores the explicit scope. Enforcement in retrieval and APIs belongs to later tickets.

## Source lifecycle

The allowed source statuses are frozen as:

```text
pending
syncing
ready
failed
disabled
```

`sync_version` starts at `0`. Later ingestion work can increment it as synchronization attempts or accepted revisions are defined by their own contract.

The source also preserves `last_synced_at` and `last_error_code` so later workers and operators have durable synchronization provenance instead of relying only on temporary logs.

## Tenant and foreign-key indexes

Knowledge is tenant-owned. The migration adds the architecture-required tenant-leading indexes for common source filtering:

```text
(tenant_id, status)
(tenant_id, source_type)
```

`created_by` is also indexed because it is a foreign key to `users` and the architecture's general database convention requires foreign keys to be index-supported.

## `knowledge_documents`: a specific ingested version

A source can produce one or many documents. A sitemap may discover many pages, and the same page may be fetched again later after its content changes.

`knowledge_documents` records a durable version with:

```text
tenant_id
source_id
canonical_uri
title
content_hash
document_version
status
fetched_at
```

The allowed statuses are exactly:

```text
active
deprecated
failed
```

The row keeps both provenance and version information. A later answer should be traceable back to the source document/version that produced the retrieved chunk rather than only storing anonymous text.

The database enforces the architecture's uniqueness rule:

```text
UNIQUE(source_id, canonical_uri, document_version)
```

That prevents two rows from claiming to be the same version of the same canonical document under one source.

The architecture indexes are also present:

```text
(tenant_id, source_id, status)
(content_hash)
```

## Why `content_hash` matters

A content hash is a compact fingerprint of document contents. Later ingestion logic can use it to detect that content is unchanged or to reason about provenance without comparing every character of a large document.

OPE-300 only stores the hash. It does not choose the hashing workflow, recrawl policy, or deduplication algorithm for later ingestion tickets.

## `knowledge_chunks`: the searchable pieces

Large documents are usually too big and too imprecise to search as one block. Later ingestion work will split a document into smaller ordered pieces called chunks.

OPE-300 stores each chunk with:

```text
tenant_id
document_id
ordinal
content
token_count
metadata
embedding
embedding_model_alias
tsv
```

`ordinal` starts at zero or greater and must be unique within the document:

```text
UNIQUE(document_id, ordinal)
```

This preserves chunk order and prevents two chunks in one document from claiming the same position.

Empty chunk content is rejected at the database boundary. `token_count` cannot be negative. `metadata` defaults to an empty JSON object so callers do not need to manufacture `{}` for every chunk while the field still remains explicitly non-null.

The document foreign key uses `ON DELETE CASCADE`. If a document version is intentionally removed, its derived chunks are removed with it rather than becoming orphaned text with no provenance.

## Lexical full-text search is available immediately

Each chunk has a generated PostgreSQL `tsvector` column named `tsv`.

The database computes it from the chunk content using the frozen expression:

```text
to_tsvector('english', content)
```

The important word is **generated**. Application code does not manually calculate and store the search vector. PostgreSQL derives it whenever the row is written, keeping the searchable representation synchronized with `content`.

A GIN index is created on `tsv`.

GIN is a PostgreSQL index type well suited to full-text search. In practical terms, it lets later retrieval code find chunks containing useful terms without scanning every chunk row one by one.

The integration test proves this behavior by inserting a chunk about a partial refund and successfully finding it with a PostgreSQL full-text query.

## Why the `embedding` column exists but has no dimension yet

Serviq plans to support semantic/vector retrieval with pgvector. The architecture already freezes the presence of an `embedding` column, but the embedding profile has **not** yet frozen a vector dimension or vector index strategy.

OPE-300 therefore creates exactly a dimensionless PostgreSQL:

```text
vector
```

column.

It does **not** guess something such as:

```text
vector(1536)
vector(3072)
```

because those values would silently choose an embedding model/profile that belongs to a later architecture decision.

The migration also creates **no HNSW, IVF/IVFFlat, cosine, L2, or other vector index**. The ticket explicitly defers that work until the embedding profile ADR and V1.3.12.

This is deliberate sequencing. Lexical search is usable now, while semantic-search indexing waits until the dimensions, distance metric, and embedding model contract are known.

## Why the migration ensures the pgvector extension exists

The repository's local Docker image contains pgvector, but a clean PostgreSQL database still needs the extension registered before PostgreSQL understands the `vector` type.

The migration therefore runs:

```text
CREATE EXTENSION IF NOT EXISTS vector
```

before creating the chunk table.

This does not choose a dimension or create a vector index. It only makes the architecture-approved PostgreSQL type available on clean environments such as CI.

The downgrade intentionally does not drop the extension. Extensions are shared database infrastructure and may have existed before this application revision. A table rollback should not remove a shared capability that another migration or operator may own.

## Tests added

The real PostgreSQL integration test is:

```text
services/api/tests/integration/test_knowledge_schema.py
```

It verifies the ticket's database behavior rather than only checking that a migration file exists.

The test covers:

- a valid URL source insert;
- rejection of URL and sitemap sources without `source_uri`;
- rejection of PDF, Markdown, and text sources without `object_key`;
- rejection of invalid source type;
- rejection of invalid access scope;
- rejection of invalid source status;
- the default `sync_version = 0`;
- rejection of an invalid document status;
- document version/provenance uniqueness;
- rejection of duplicate `(document_id, ordinal)` chunks;
- rejection of empty chunk content;
- rejection of negative token counts;
- nullable `embedding` storage;
- default empty JSON metadata;
- automatically generated `tsv` content;
- a real lexical full-text query;
- existence of the GIN `tsv` index;
- confirmation that the embedding type is dimensionless `vector`;
- confirmation that no index targets the embedding column.

The repository's existing database-integration workflow already upgrades a clean PostgreSQL database to migration head, runs the integration suite, downgrades through the migration chain, upgrades to head again, and finally downgrades to base. OPE-300 relies on that shared gate instead of creating a second migration runner.

## Security and data-integrity decisions

OPE-300 keeps several future safety requirements visible in the schema itself:

- every source is tenant-owned;
- every document keeps its source relationship;
- every chunk keeps its document relationship;
- customer/internal scope is explicit;
- source provenance fields are durable;
- no raw credential column is introduced;
- statuses are closed sets enforced by CHECK constraints;
- invalid source locations are rejected by PostgreSQL;
- document/chunk uniqueness is enforced under concurrency by the database;
- searchable text is derived from content rather than trusted from a caller;
- vector indexing is blocked until its architecture is frozen.

These checks do not replace later authorization or row-level security. They make malformed data harder to create even if a future application bug reaches the persistence layer.

## Main files changed

```text
services/api/alembic/versions/20260819_0008_knowledge_schema.py
services/api/tests/integration/test_knowledge_schema.py
docs/SERVIQ_BUILD_GUIDE.md
```

The temporary workflow used only to append this section removes itself in the same documentation commit, so it is not part of the permanent OPE-300 repository tree.

## What OPE-300 deliberately does not implement

This ticket does not add:

- knowledge-source REST APIs;
- file upload or object-storage workflows;
- website/sitemap crawling;
- PDF parsing;
- chunking algorithms;
- ingestion workers;
- embedding generation;
- embedding model selection;
- a vector dimension;
- a vector index;
- hybrid retrieval/ranking APIs;
- citations in customer answers;
- source authentication/credential design;
- knowledge-scope authorization enforcement.

Those are separate product, architecture, security, and worker concerns.

## What improves after OPE-300

Before this change, Serviq's knowledge subsystem existed mainly as an architecture contract. The database could not yet persist a trustworthy source-to-document-to-chunk chain for later retrieval.

After OPE-300, Serviq has the durable relational backbone for knowledge ingestion and lexical retrieval. A future ingestion worker has a precise place to record source provenance, document versions, and ordered chunks. A future retrieval system can perform PostgreSQL full-text search immediately, while vector search remains deliberately blocked from premature optimization or an invented embedding profile.

The larger engineering improvement is sequencing: Serviq can now build ingestion and lexical retrieval on a stable schema without coupling that work to an embedding vendor or vector-index decision that has not been made yet.

## Completion gate

The implementation is considered complete when the final `ope300` branch head passes the repository quality checks and real PostgreSQL integration workflow, including migration upgrade/downgrade coverage, with the permanent build-guide section present and the temporary documentation helper absent.

## OPE-301 — S3-Compatible Storage Adapter and Generated Object Keys

**Completed on branch:** `ope301`  
**Linear ticket:** `OPE-301`  
**Architecture decision:** `docs/architecture-decisions/ADR-016-s3-compatible-object-storage-client.md`

### What this ticket was trying to solve

Serviq already had a local object-storage server in Docker. That server is SeaweedFS, and it exposes an S3-compatible interface. In simple terms, the infrastructure could hold files, but the Python application did not yet have a safe, reusable way to talk to it.

Without an application-owned adapter, every future feature that needs to save a file could make its own S3 calls. One developer might use a filename as the storage path. Another might retry failed requests many times. Another might leak the internal storage URL in an exception. Another might call a SeaweedFS-specific API that would later make an AWS S3 migration difficult. All of those approaches would work in a small demo and become expensive security or maintenance problems later.

OPE-301 creates one narrow storage doorway for the API. Future feature code uses that doorway instead of talking directly to the storage vendor.

### The storage adapter we added

The main implementation is `services/api/app/core/object_storage.py`.

The adapter exposes the four required storage operations plus one convenience helper:

1. `put_object` stores bytes or a binary stream and records the supplied content type.
2. `get_object` reads an object and returns its bytes plus the small amount of metadata downstream code needs today, including content type, content length, and ETag when the backend provides one.
3. `head` reads object metadata such as content type, content length, ETag, and custom metadata without downloading the object body.
4. `delete_object` removes an object. Deleting an object that is already gone is treated as success, which makes cleanup code safe to repeat.
5. `exists` is a convenience helper implemented on top of `head`. It returns `False` when an object is missing without downloading the object body.

We intentionally did **not** add object listing, public buckets, presigned URLs, multipart-upload policy, ACL management, retention policy, lifecycle policy, or customer attachments. Those features carry additional product and security decisions and OPE-301 was not allowed to guess them.

### Why Serviq now uses botocore

The ticket required an approved S3-compatible client, but the repository did not actually name one. That was an architecture gap, so we resolved it explicitly in ADR-016 instead of silently choosing a dependency inside the code.

The API now uses the AWS-maintained low-level `botocore` S3 client in the 1.42 release line. The exact patch is stored in `services/api/uv.lock`.

We chose the low-level client because this adapter needs only basic S3 requests. Adding the full boto3 resource and transfer layers would increase dependency surface without helping these four operations. The important design point is that feature code still does not depend on botocore. Botocore stays inside the Serviq adapter. If the infrastructure changes later, the rest of the product keeps calling the same Serviq interface.

### How network failures are bounded

Storage calls are external network calls, even when the storage server is running on the developer's laptop. An external dependency must never be allowed to wait or retry forever.

OPE-301 therefore configures the S3 client with:

- a 5-second connection timeout;
- a 30-second read timeout;
- one total SDK attempt;
- S3 Signature Version 4;
- path-style S3 addressing for the local SeaweedFS endpoint.

The one-attempt setting is important. It prevents an SDK from quietly multiplying retries underneath a future worker's own retry policy. A higher-level ingestion or export workflow can own its business retry strategy later without two retry systems fighting each other.

### Why object keys are generated instead of supplied as strings

An object key is similar to a path inside an S3 bucket. Letting a browser filename become that path creates several problems. Filenames can contain slashes, repeated names, unusual characters, or text chosen by an attacker. They can also reveal personal or business information in logs and storage tooling.

OPE-301 does not accept a filename when it builds an object key. Instead, it accepts trusted UUID identifiers generated or validated by Serviq and produces one of four exact layouts:

```text
tenants/{tenantId}/knowledge/{sourceId}/raw/{objectId}
tenants/{tenantId}/knowledge/{sourceId}/normalized/{documentId}/{version}
tenants/{tenantId}/exports/{exportId}
tenants/{tenantId}/evaluation/{evaluationRunId}
```

The Python code represents these as typed key objects rather than a generic full-key string. The constructors also reject non-UUID identifiers at runtime. This gives us two safety layers: type checking catches normal developer mistakes, and runtime validation prevents an accidental string such as `../../another-tenant` from becoming an object path.

A user-facing filename can still be stored later as metadata when a dedicated upload feature is implemented. It simply cannot decide where the object lives.

### Tenant isolation at the storage-key layer

Every supported object key starts with `tenants/{tenantId}/`.

That does not replace database authorization, permission checks, or future bucket/IAM policy. It adds another clear isolation boundary. Two tenants using the same source ID or document ID still produce different storage paths because their tenant IDs are different.

The tests build otherwise-identical keys for two tenant UUIDs and verify that the prefixes and final keys are different.

### Stable errors instead of SDK internals

Raw S3 errors can include internal endpoint names, bucket information, request details, and sometimes values that should not escape the infrastructure boundary. Passing those exceptions directly to routers or logs would make future redaction much harder.

The adapter therefore normalizes failures into Serviq-owned errors:

```text
OBJECT_STORAGE_UNAVAILABLE
OBJECT_NOT_FOUND
```

A missing `get_object` becomes `OBJECT_NOT_FOUND`. A missing `exists` becomes `False`. Repeated delete remains successful. Other SDK or network failures become `OBJECT_STORAGE_UNAVAILABLE` with a generic message.

Unit tests deliberately create an SDK error containing a fake credential and fake internal URL, then verify neither value appears in the Serviq exception representation.

### Local configuration was corrected

Before this ticket, the repository had a subtle local configuration mismatch:

- `ARCHITECTURE.md` defined the local bucket as `serviq-local-objects`.
- Docker Compose also defaulted to `serviq-local-objects`.
- `.env.example` still used `serviq-local`.

OPE-301 aligns `.env.example` with the architecture and Compose source of truth. The example also uses the same development-only access-key and secret-key defaults as the local Compose service. These values are local placeholders, not production credentials.

This matters because a new developer can now copy `.env.example`, start the local storage service, and have the API point to the same bucket instead of debugging a configuration disagreement that had nothing to do with application code.

### Real local integration coverage

Unit tests are necessary, but an S3 adapter can look correct with a fake client and still fail against the real local service because of signing, addressing style, endpoint behavior, or bucket configuration.

OPE-301 therefore adds `services/api/tests/integration/test_object_storage_integration.py`. The test performs a complete round trip against the Compose object-storage service:

1. make sure the test object is absent;
2. store known bytes;
3. confirm the object exists;
4. read it back and compare the content and metadata;
5. delete it;
6. confirm it no longer exists;
7. delete it again to prove cleanup is idempotent.

`.github/workflows/ci.yml` now has a dedicated `object-storage-integration` job. It starts only the local object-storage service, waits for the S3 endpoint to accept connections, runs the real integration test, and tears the service down even when the test fails.

### Files changed for OPE-301

- `services/api/app/core/object_storage.py` adds the adapter, typed keys, factory, metadata result, and stable errors.
- `services/api/tests/test_object_storage.py` covers exact keys, tenant separation, runtime key validation, adapter behavior, configuration, retries/timeouts, and error redaction.
- `services/api/tests/integration/test_object_storage_integration.py` proves a real local S3-compatible round trip.
- `services/api/pyproject.toml` adds the approved low-level S3 client dependency.
- `services/api/uv.lock` freezes the resolved dependency graph.
- `.github/workflows/ci.yml` adds the object-storage integration gate.
- `.env.example` aligns the local bucket and development credentials with Compose.
- `docs/architecture-decisions/ADR-016-s3-compatible-object-storage-client.md` records the missing client/retry decision.
- `docs/repo_context.md` records the storage adapter as implemented repository reality.
- `docs/TECH_STACK.md` records botocore as the Python object-storage client behind the Serviq adapter.
- `docs/SERVIQ_BUILD_GUIDE.md` contains this implementation explanation.

### What this improves

For a non-technical reader, the main improvement is consistency. Serviq now has one controlled place that decides how application code stores and reads objects. A future knowledge upload, export, or evaluation feature does not need to solve S3 connectivity, path generation, timeout behavior, retry behavior, and error redaction again.

For developers, this reduces duplicate infrastructure code and makes storage behavior testable.

For security, it prevents user filenames from becoming object paths, keeps tenant IDs at the start of every supported key, limits automatic retry behavior, and hides raw SDK failure details behind stable errors.

For operations, local development now uses one bucket convention and CI proves the real S3-compatible path instead of relying only on mocks.

For future AWS deployment, the application remains behind an S3-compatible abstraction instead of depending on SeaweedFS-specific behavior. Production IAM, signing-region configuration, encryption, lifecycle, retention, and bucket-policy decisions are still intentionally left to the deployment/security tickets that own them.

### What OPE-301 intentionally leaves for later

Completing this ticket does **not** mean Serviq has a user-facing upload feature. It also does not mean a knowledge document is parsed, chunked, embedded, or searchable.

The following work remains separate:

- MIME, extension, and file-size enforcement in an upload boundary;
- knowledge source upload APIs;
- ingestion workers;
- presigned URL contracts;
- exports that actually produce files;
- evaluation jobs that actually produce artifacts;
- customer attachment storage;
- production AWS identity/IAM and regional configuration;
- server-side encryption and retention/lifecycle policy.

Keeping those concerns out of OPE-301 is deliberate. This ticket builds the safe storage foundation those features can reuse without pretending the higher-level product workflows already exist.


## OPE-302 — URL and sitemap knowledge-source registration

**Implemented on branch:** `ope302`  
**Linear ticket:** `OPE-302`

### What problem this ticket solves

OPE-300 created Serviq's relational knowledge schema, but an authorized tenant administrator still had no API for registering a public website or sitemap as a knowledge source. OPE-302 adds that control-plane boundary without starting ingestion in the request thread.

The API now exposes:

```text
GET  /api/v1/knowledge-sources
POST /api/v1/knowledge-sources
```

POST accepts only URL-backed source metadata:

```text
sourceType  = url | sitemap
name        = trimmed, 1 to 160 characters
sourceUri   = absolute HTTPS URL
accessScope = customer | internal
```

Unknown request fields are rejected rather than silently ignored.

### URL validation and why registration does not crawl

Registration validates syntax before persistence. Requests are rejected when they use HTTP or another non-HTTPS scheme such as `file:`, `ftp:`, `data:`, or `javascript:`, contain embedded username/password credentials, contain a URL fragment, have malformed host/port syntax, or contain whitespace/control characters.

OPE-302 deliberately performs no DNS resolution, private-network classification, redirects, HTTP fetching, robots checks, sitemap parsing, chunking, embedding work, or vector indexing. SSRF-sensitive network behavior belongs to the later crawler/fetch boundary, where redirect and resolved-IP rules can be enforced immediately before an outbound request.

### Metadata-only creation

A successful POST creates one tenant-owned `knowledge_sources` row with server-controlled lifecycle values:

```text
status          = pending
sync_version    = 0
object_key      = NULL
last_synced_at  = NULL
last_error_code = NULL
```

The tenant and creator come from trusted server-side workforce context. The browser cannot choose another tenant, creator, lifecycle state, sync version, storage object key, or ingestion behavior.

There is no HTTP client, crawler, parser, object-storage write, embedding call, or background-ingestion trigger in the create service. Registration is intentionally a small metadata transaction.

### Tenant isolation

GET and POST use the trusted `serviq_tenant_id` request principal established by the authentication/tenancy foundation. There is no tenant ID request field or query parameter for callers to override.

Repository reads include `knowledge_sources.tenant_id = current_tenant_id`. The real PostgreSQL integration test uses Serviq's shared V1.1.14 tenant-isolation harness, seeds a second tenant with a foreign knowledge source, and proves the current tenant's list excludes it.

### Capability-based authorization

OPE-302 adds the capability:

```text
knowledge.sources.manage
```

Alembic revision `20260819_0009_knowledge_permissions.py` seeds that capability onto the existing global workforce `owner` and `admin` system roles.

Runtime authorization does not hard-code role names such as `Knowledge Manager`. It reuses OPE-282's effective-capability resolver and requires the current active tenant membership to contain `knowledge.sources.manage`. A future tenant Knowledge Manager role can therefore receive the same capability through normal RBAC configuration without changing these routes.

A workforce user without the capability receives a safe 403 response. Missing or inactive tenant membership fails closed through the same authorization boundary.

### Safe list response

GET returns browser-safe metadata only:

```text
id
sourceType
name
sourceUri
accessScope
status
syncVersion
lastSyncedAt
lastErrorCode
createdAt
updatedAt
```

It does not expose `objectKey`, `createdBy`, storage internals, credentials, or secret values.

The response model supports all five architecture-approved source types and permits `sourceUri = null`. That keeps the list route compatible with future PDF, Markdown, and text sources, whose records use object storage instead of a URL, while OPE-302 POST remains intentionally restricted to `url | sitemap`.

### Tests added

`services/api/tests/test_knowledge_source_schemas.py` covers strict request validation, including valid trimming and rejection of unsafe schemes, malformed URLs, credentials, fragments, invalid source types/scopes, blank or oversized names, and unknown fields.

`services/api/tests/integration/test_knowledge_sources_api.py` uses the real PostgreSQL environment plus the shared tenant-isolation harness. It covers valid URL creation, valid sitemap creation, `pending` plus `sync_version = 0`, null object-storage state, tenant isolation, unauthorized access, safe response fields, and the HTTP validation matrix.

That integration test also replaces the default `httpx` outbound transport with a guard that raises immediately. FastAPI requests use the in-process ASGI transport, so the test fails if knowledge-source registration later starts an ordinary outbound HTTP request. This protects the metadata-only rule.

`services/api/tests/integration/test_knowledge_permissions.py` verifies that the RBAC migration grants `knowledge.sources.manage` to the existing Owner and Admin system roles.

### Main files changed

```text
services/api/alembic/versions/20260819_0009_knowledge_permissions.py
services/api/app/modules/knowledge/__init__.py
services/api/app/modules/knowledge/models.py
services/api/app/modules/knowledge/repository.py
services/api/app/modules/knowledge/schemas.py
services/api/app/modules/knowledge/errors.py
services/api/app/modules/knowledge/service.py
services/api/app/modules/knowledge/router.py
services/api/app/main.py
services/api/tests/test_knowledge_source_schemas.py
services/api/tests/integration/test_knowledge_sources_api.py
services/api/tests/integration/test_knowledge_permissions.py
docs/SERVIQ_BUILD_GUIDE.md
```

### What this improves

Serviq administrators can now begin knowledge setup through a real tenant-scoped API instead of direct database writes. The browser cannot choose arbitrary URL schemes, credentials-in-URL, tenant identity, creator identity, or source lifecycle state. Authorization is capability-based, list queries are tenant-scoped, and normal responses omit storage internals.

Registration also remains fast and deterministic. It writes metadata and leaves expensive or SSRF-sensitive network work to the dedicated ingestion system that will own those controls.

The GET projection is forward-compatible with future file-backed knowledge sources without expanding this ticket's POST contract.

### What OPE-302 intentionally leaves for later

This ticket does not implement website crawling, sitemap fetching/parsing, DNS/private-network SSRF checks for outbound fetches, redirect rules, robots/allowlist enforcement, file uploads, document parsing, chunking, embeddings, vector indexing, synchronization jobs, knowledge-source edit/disable routes, or customer-answer retrieval.

Those remain separate tickets and must reuse this tenant/RBAC/source foundation instead of expanding OPE-302 into an ingestion worker.

### Completion and validation rule

The implementation is complete on `ope302` only after the final branch head, including this cumulative documentation update, passes the repository's normal CI/security checks and real PostgreSQL migration/integration coverage. Until it is merged, this work must not be represented as production behavior on `main`.


## OPE-303 — Knowledge file uploads

**Implemented on branch:** `ope303`  
**Linear ticket:** `OPE-303`

OPE-303 extends the existing knowledge-source API so authorized business users can register approved PDF, Markdown, and plain-text files in addition to the URL and sitemap sources added by OPE-302. The same `POST /api/v1/knowledge-sources` path keeps JSON registration for URL-backed sources and accepts `multipart/form-data` for file-backed sources.

PDF accepts only `.pdf` with `application/pdf` up to 25 MiB. Markdown accepts `.md` or `.markdown` with `text/markdown` or `text/plain` up to 5 MiB. Plain text accepts `.txt` with `text/plain` up to 5 MiB. The server checks source type, extension, MIME type, actual byte count, and content sanity together. PDFs must begin with the PDF signature, while Markdown/text must be valid UTF-8 without NUL bytes. Uploaded content is untrusted data and is never executed.

File size is counted with bounded chunk reads. User filenames never become storage paths. Serviq generates source and object UUIDs and reuses the OPE-301 key format `tenants/{tenantId}/knowledge/{sourceId}/raw/{objectId}`. A sanitized basename can exist only as object metadata.

Serviq checks `knowledge.sources.manage`, validates the file, uploads the generated object outside a database transaction, and then creates a pending `knowledge_sources` row with `source_uri = NULL`, the generated `object_key`, and `sync_version = 0`. Storage failure creates no source row. A database failure after storage succeeds triggers deletion of the just-uploaded object so it cannot become an orphan.

Responses remain browser-safe and omit `objectKey`, bucket names, internal endpoints, credentials, and `createdBy`. Tests cover accepted file formats, size boundaries, MIME/extension mismatch, fake PDFs, invalid UTF-8, malicious filenames, authorization, tenant scoping, storage failure, and database-failure compensation.

OPE-303 does not parse documents, chunk or embed content, run synchronization workers, crawl URLs, add customer attachments, introduce presigned uploads, or change the frozen object-key layout.
