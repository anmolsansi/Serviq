from __future__ import annotations

import asyncio
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import load_settings
from app.core.database import create_database_engine, create_database_session_factory

pytestmark = pytest.mark.skipif(
    os.getenv("SERVIQ_DATABASE_INTEGRATION") != "1",
    reason="requires the real PostgreSQL integration environment",
)


async def _expect_integrity_error(
    session_factory: async_sessionmaker[AsyncSession],
    statement: str,
    params: dict[str, object],
) -> None:
    """Keep every rejected row isolated so one failure does not poison later checks."""

    async with session_factory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(text(statement), params)
        await session.rollback()


def test_knowledge_schema_constraints_full_text_search_and_vector_deferral() -> None:
    async def scenario() -> None:
        engine = create_database_engine(load_settings())
        session_factory = create_database_session_factory(engine)
        tenant_id = uuid4()
        user_id = uuid4()
        source_id = uuid4()
        document_id = uuid4()
        chunk_id = uuid4()

        source_insert = """
            INSERT INTO knowledge_sources (
              id, tenant_id, source_type, name, source_uri, object_key,
              access_scope, status, created_by
            ) VALUES (
              :id, :tenant, :source_type, :name, :source_uri, :object_key,
              :access_scope, :status, :created_by
            )
        """
        document_insert = """
            INSERT INTO knowledge_documents (
              id, tenant_id, source_id, canonical_uri, title,
              content_hash, document_version, status, fetched_at
            ) VALUES (
              :id, :tenant, :source, :canonical_uri, :title,
              :content_hash, :document_version, :status, now()
            )
        """
        chunk_insert = """
            INSERT INTO knowledge_chunks (
              id, tenant_id, document_id, ordinal, content,
              token_count, embedding, embedding_model_alias
            ) VALUES (
              :id, :tenant, :document, :ordinal, :content,
              :token_count, :embedding, :embedding_model_alias
            )
        """

        try:
            async with session_factory() as session, session.begin():
                await session.execute(
                    text(
                        """
                        INSERT INTO tenants (id, slug, display_name, status, default_locale)
                        VALUES (:id, :slug, 'Knowledge Tenant', 'active', 'en')
                        """
                    ),
                    {
                        "id": tenant_id,
                        "slug": f"knowledge-{tenant_id.hex[:12]}",
                    },
                )
                await session.execute(
                    text(
                        """
                        INSERT INTO users (
                          id, oidc_issuer, oidc_subject, email, display_name, status
                        ) VALUES (
                          :id, 'https://ope300.test', :subject,
                          :email, 'Knowledge Owner', 'active'
                        )
                        """
                    ),
                    {
                        "id": user_id,
                        "subject": f"knowledge-owner-{user_id.hex}",
                        "email": f"knowledge-{user_id.hex[:12]}@example.com",
                    },
                )
                await session.execute(
                    text(source_insert),
                    {
                        "id": source_id,
                        "tenant": tenant_id,
                        "source_type": "url",
                        "name": "Refund policy",
                        "source_uri": "https://example.test/refund-policy",
                        "object_key": None,
                        "access_scope": "customer",
                        "status": "pending",
                        "created_by": user_id,
                    },
                )

            for missing_uri_type in ("url", "sitemap"):
                await _expect_integrity_error(
                    session_factory,
                    source_insert,
                    {
                        "id": uuid4(),
                        "tenant": tenant_id,
                        "source_type": missing_uri_type,
                        "name": "Missing URI",
                        "source_uri": None,
                        "object_key": None,
                        "access_scope": "customer",
                        "status": "pending",
                        "created_by": user_id,
                    },
                )

            for file_type in ("pdf", "markdown", "text"):
                await _expect_integrity_error(
                    session_factory,
                    source_insert,
                    {
                        "id": uuid4(),
                        "tenant": tenant_id,
                        "source_type": file_type,
                        "name": "Missing object",
                        "source_uri": None,
                        "object_key": None,
                        "access_scope": "internal",
                        "status": "pending",
                        "created_by": user_id,
                    },
                )

            for field, bad_value in (
                ("source_type", "web"),
                ("access_scope", "public"),
                ("status", "complete"),
            ):
                source_values: dict[str, object] = {
                    "id": uuid4(),
                    "tenant": tenant_id,
                    "source_type": "url",
                    "name": "Invalid source",
                    "source_uri": "https://example.test/invalid",
                    "object_key": None,
                    "access_scope": "customer",
                    "status": "pending",
                    "created_by": user_id,
                }
                source_values[field] = bad_value
                await _expect_integrity_error(
                    session_factory,
                    source_insert,
                    source_values,
                )

            async with session_factory() as session, session.begin():
                sync_version = (
                    await session.execute(
                        text(
                            "SELECT sync_version FROM knowledge_sources WHERE id = :id"
                        ),
                        {"id": source_id},
                    )
                ).scalar_one()
                assert sync_version == 0

                await session.execute(
                    text(document_insert),
                    {
                        "id": document_id,
                        "tenant": tenant_id,
                        "source": source_id,
                        "canonical_uri": "https://example.test/refund-policy",
                        "title": "Refund policy",
                        "content_hash": "sha256:ope300-refund-policy-v1",
                        "document_version": 1,
                        "status": "active",
                    },
                )

            await _expect_integrity_error(
                session_factory,
                document_insert,
                {
                    "id": uuid4(),
                    "tenant": tenant_id,
                    "source": source_id,
                    "canonical_uri": "https://example.test/failed-policy",
                    "title": "Bad document status",
                    "content_hash": "sha256:ope300-bad-status",
                    "document_version": 1,
                    "status": "ready",
                },
            )
            await _expect_integrity_error(
                session_factory,
                document_insert,
                {
                    "id": uuid4(),
                    "tenant": tenant_id,
                    "source": source_id,
                    "canonical_uri": "https://example.test/refund-policy",
                    "title": "Duplicate document version",
                    "content_hash": "sha256:ope300-refund-policy-duplicate",
                    "document_version": 1,
                    "status": "active",
                },
            )

            async with session_factory() as session, session.begin():
                await session.execute(
                    text(chunk_insert),
                    {
                        "id": chunk_id,
                        "tenant": tenant_id,
                        "document": document_id,
                        "ordinal": 0,
                        "content": (
                            "The support policy allows a partial refund when an order "
                            "arrives with a missing item."
                        ),
                        "token_count": 17,
                        "embedding": None,
                        "embedding_model_alias": None,
                    },
                )

            await _expect_integrity_error(
                session_factory,
                chunk_insert,
                {
                    "id": uuid4(),
                    "tenant": tenant_id,
                    "document": document_id,
                    "ordinal": 0,
                    "content": "Duplicate ordinal",
                    "token_count": 2,
                    "embedding": None,
                    "embedding_model_alias": None,
                },
            )
            await _expect_integrity_error(
                session_factory,
                chunk_insert,
                {
                    "id": uuid4(),
                    "tenant": tenant_id,
                    "document": document_id,
                    "ordinal": 1,
                    "content": "",
                    "token_count": 0,
                    "embedding": None,
                    "embedding_model_alias": None,
                },
            )
            await _expect_integrity_error(
                session_factory,
                chunk_insert,
                {
                    "id": uuid4(),
                    "tenant": tenant_id,
                    "document": document_id,
                    "ordinal": 1,
                    "content": "Invalid token count",
                    "token_count": -1,
                    "embedding": None,
                    "embedding_model_alias": None,
                },
            )

            async with session_factory() as session:
                lexical_match = (
                    await session.execute(
                        text(
                            """
                            SELECT id
                            FROM knowledge_chunks
                            WHERE id = :id
                              AND tsv @@ plainto_tsquery('english', 'partial refund')
                            """
                        ),
                        {"id": chunk_id},
                    )
                ).scalar_one()
                assert lexical_match == chunk_id

                generated_tsv = (
                    await session.execute(
                        text("SELECT tsv::text FROM knowledge_chunks WHERE id = :id"),
                        {"id": chunk_id},
                    )
                ).scalar_one()
                assert "partial" in generated_tsv
                assert "refund" in generated_tsv

                metadata = (
                    await session.execute(
                        text("SELECT metadata FROM knowledge_chunks WHERE id = :id"),
                        {"id": chunk_id},
                    )
                ).scalar_one()
                assert metadata == {}

                embedding_type = (
                    await session.execute(
                        text(
                            """
                            SELECT format_type(attribute.atttypid, attribute.atttypmod)
                            FROM pg_attribute AS attribute
                            WHERE attribute.attrelid = 'knowledge_chunks'::regclass
                              AND attribute.attname = 'embedding'
                              AND NOT attribute.attisdropped
                            """
                        )
                    )
                ).scalar_one()
                assert embedding_type == "vector"

                tsv_generation = (
                    await session.execute(
                        text(
                            """
                            SELECT is_generated, generation_expression
                            FROM information_schema.columns
                            WHERE table_schema = current_schema()
                              AND table_name = 'knowledge_chunks'
                              AND column_name = 'tsv'
                            """
                        )
                    )
                ).one()
                assert tsv_generation.is_generated == "ALWAYS"
                assert "to_tsvector('english'::regconfig, content)" in (
                    tsv_generation.generation_expression or ""
                )

                indexes = (
                    await session.execute(
                        text(
                            """
                            SELECT indexname, indexdef
                            FROM pg_indexes
                            WHERE schemaname = current_schema()
                              AND tablename = 'knowledge_chunks'
                            """
                        )
                    )
                ).all()
                index_definitions = {
                    str(row.indexname): str(row.indexdef) for row in indexes
                }
                assert "ix_knowledge_chunks_tsv" in index_definitions
                assert "USING gin" in index_definitions["ix_knowledge_chunks_tsv"]
                assert all(
                    "embedding" not in definition.lower()
                    for definition in index_definitions.values()
                )
        finally:
            async with session_factory() as session, session.begin():
                await session.execute(
                    text("DELETE FROM knowledge_chunks WHERE tenant_id = :tenant"),
                    {"tenant": tenant_id},
                )
                await session.execute(
                    text("DELETE FROM knowledge_documents WHERE tenant_id = :tenant"),
                    {"tenant": tenant_id},
                )
                await session.execute(
                    text("DELETE FROM knowledge_sources WHERE tenant_id = :tenant"),
                    {"tenant": tenant_id},
                )
                await session.execute(
                    text("DELETE FROM users WHERE id = :id"),
                    {"id": user_id},
                )
                await session.execute(
                    text("DELETE FROM tenants WHERE id = :id"),
                    {"id": tenant_id},
                )
            await engine.dispose()

    asyncio.run(scenario())
