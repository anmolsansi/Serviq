# @serviq/testkit

`@serviq/testkit` is the shared TypeScript boundary for reusable test-only helpers after their purpose is explicitly defined.

It may eventually contain deterministic fixtures, fakes, builders, and test utilities that are safe to reuse across packages or applications. This scaffold does not add fake LLMs, business fixtures, network mocks, test data, or runtime dependencies. Production code must not depend on test-only behavior, and this package must not import from `apps/`.

The package intentionally exports no behavior in this scaffold.
