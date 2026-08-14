# ADR-001 — API database session model

**Status:** Accepted  
**Scope:** Serviq API persistence foundation  
**Decision owner:** Architecture  
**Applies from:** OPE-275

## Context

OPE-275 requires one SQLAlchemy engine/session pattern before repositories or product tables are added. The existing architecture froze PostgreSQL, SQLAlchemy 2, Alembic, and the `DATABASE_URL` environment contract, but it did not freeze whether FastAPI persistence should use synchronous or asynchronous SQLAlchemy sessions. The ticket explicitly forbids a builder from inventing or mixing both patterns.

## Decision

Serviq API persistence uses **SQLAlchemy 2 asynchronous ORM sessions**.

The exact ownership contract is:

- `services/api/app/core/database.py` owns database URL adaptation, `AsyncEngine` construction, `async_sessionmaker`, the cached process engine/session factory, and the FastAPI-compatible session dependency.
- `services/api/app/models/base.py` owns the single SQLAlchemy `DeclarativeBase` metadata root used by Alembic and future API models.
- `services/api/alembic/` owns schema migration scripts.
- `services/api/alembic.ini` owns Alembic command configuration.
- Application code must not create a second sync engine/session pattern.
- Future repositories receive an `AsyncSession`; they do not construct engines themselves.

The PostgreSQL driver is **Psycopg 3**. `DATABASE_URL` remains the frozen external variable name and may use the ordinary `postgresql://` scheme. The database adapter converts that scheme internally to SQLAlchemy's `postgresql+psycopg://` dialect before creating an async engine. This is an internal adapter detail, not a new environment contract.

The reusable session factory is created with `expire_on_commit=False`. A session is scoped to one request or explicit background work unit, is always closed by an async context manager, and future business services own explicit commit/rollback decisions. No external network calls should be performed while a database transaction is held open.

Alembic uses its supported async-engine environment pattern and imports the same `Base.metadata`. Migrations remain the only supported mechanism for schema changes.

## Why this decision

FastAPI request handlers and Serviq's future dependency calls are asynchronous. Using one async persistence pattern avoids blocking request workers on database I/O and prevents the repository from accumulating separate sync and async session factories. SQLAlchemy 2 supports `create_async_engine()` and `async_sessionmaker`, its PostgreSQL Psycopg dialect selects Psycopg's async implementation when used with an async engine, and Alembic supports running migrations through an async SQLAlchemy engine.

Psycopg 3 is chosen rather than Psycopg 2 because it provides native asyncio support and currently supports the repository's Python 3.14 / PostgreSQL 18 development targets.

## Consequences

Future API repository methods that perform database I/O are async. Tests that exercise persistence use real PostgreSQL for integration behavior instead of substituting SQLite. Code must not share one `AsyncSession` across concurrent tasks. Database URLs and driver exceptions must not be emitted to users or ordinary logs with credentials intact.

## Non-decisions

This ADR does not choose production connection-pool sizes, transaction isolation levels, read replicas, tenant row-level security, repository interfaces, or any product table. Those require later tickets and measured deployment needs.
