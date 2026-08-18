"""Create knowledge source, document, and chunk persistence.

Revision ID: 20260819_0008
Revises: 20260819_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260819_0008"
down_revision: str | Sequence[str] | None = "20260819_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


class Vector(sa.types.UserDefinedType):
    """Dimensionless pgvector type until the embedding profile is frozen."""

    cache_ok = True

    def get_col_spec(self, **_kw: object) -> str:
        return "vector"


def _id_column() -> sa.Column[object]:
    return sa.Column(
        "id",
        UUID,
        primary_key=True,
        nullable=False,
        server_default=sa.text("uuidv7()"),
    )


def _created_at_column() -> sa.Column[object]:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def _updated_at_column() -> sa.Column[object]:
    return sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def upgrade() -> None:
    # The local image already ships pgvector, but a clean PostgreSQL database still
    # needs the extension registered before a dimensionless `vector` column can exist.
    # This intentionally creates no embedding dimension and no vector index.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "knowledge_sources",
        _id_column(),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=True),
        sa.Column("object_key", sa.Text(), nullable=True),
        sa.Column("access_scope", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "sync_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.Text(), nullable=True),
        sa.Column("created_by", UUID, nullable=False),
        _created_at_column(),
        _updated_at_column(),
        sa.CheckConstraint(
            "source_type IN ('url', 'sitemap', 'pdf', 'markdown', 'text')",
            name="ck_knowledge_sources_source_type",
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 160",
            name="ck_knowledge_sources_name_length",
        ),
        sa.CheckConstraint(
            "access_scope IN ('customer', 'internal')",
            name="ck_knowledge_sources_access_scope",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'syncing', 'ready', 'failed', 'disabled')",
            name="ck_knowledge_sources_status",
        ),
        sa.CheckConstraint(
            "((source_type IN ('url', 'sitemap') AND source_uri IS NOT NULL) OR "
            "(source_type IN ('pdf', 'markdown', 'text') AND object_key IS NOT NULL))",
            name="ck_knowledge_sources_location_requirement",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_knowledge_sources_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_knowledge_sources_created_by_users",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_knowledge_sources_tenant_status",
        "knowledge_sources",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_knowledge_sources_tenant_source_type",
        "knowledge_sources",
        ["tenant_id", "source_type"],
    )
    op.create_index(
        "ix_knowledge_sources_created_by",
        "knowledge_sources",
        ["created_by"],
    )

    op.create_table(
        "knowledge_documents",
        _id_column(),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("source_id", UUID, nullable=False),
        sa.Column("canonical_uri", sa.Text(), nullable=True),
        sa.Column(
            "title",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.CheckConstraint(
            "status IN ('active', 'deprecated', 'failed')",
            name="ck_knowledge_documents_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_knowledge_documents_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["knowledge_sources.id"],
            name="fk_knowledge_documents_source_id_sources",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "source_id",
            "canonical_uri",
            "document_version",
            name="uq_knowledge_documents_source_uri_version",
        ),
    )
    op.create_index(
        "ix_knowledge_documents_tenant_source_status",
        "knowledge_documents",
        ["tenant_id", "source_id", "status"],
    )
    op.create_index(
        "ix_knowledge_documents_content_hash",
        "knowledge_documents",
        ["content_hash"],
    )

    op.create_table(
        "knowledge_chunks",
        _id_column(),
        sa.Column("tenant_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("embedding", Vector(), nullable=True),
        sa.Column("embedding_model_alias", sa.Text(), nullable=True),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', content)", persisted=True),
            nullable=True,
        ),
        _created_at_column(),
        _updated_at_column(),
        sa.CheckConstraint(
            "ordinal >= 0",
            name="ck_knowledge_chunks_ordinal_nonnegative",
        ),
        sa.CheckConstraint(
            "char_length(content) > 0",
            name="ck_knowledge_chunks_content_nonempty",
        ),
        sa.CheckConstraint(
            "token_count >= 0",
            name="ck_knowledge_chunks_token_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_knowledge_chunks_tenant_id_tenants",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name="fk_knowledge_chunks_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "document_id",
            "ordinal",
            name="uq_knowledge_chunks_document_ordinal",
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_tenant_document",
        "knowledge_chunks",
        ["tenant_id", "document_id"],
    )
    op.create_index(
        "ix_knowledge_chunks_tsv",
        "knowledge_chunks",
        ["tsv"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_tsv", table_name="knowledge_chunks")
    op.drop_index(
        "ix_knowledge_chunks_tenant_document",
        table_name="knowledge_chunks",
    )
    op.drop_table("knowledge_chunks")

    op.drop_index(
        "ix_knowledge_documents_content_hash",
        table_name="knowledge_documents",
    )
    op.drop_index(
        "ix_knowledge_documents_tenant_source_status",
        table_name="knowledge_documents",
    )
    op.drop_table("knowledge_documents")

    op.drop_index("ix_knowledge_sources_created_by", table_name="knowledge_sources")
    op.drop_index(
        "ix_knowledge_sources_tenant_source_type",
        table_name="knowledge_sources",
    )
    op.drop_index(
        "ix_knowledge_sources_tenant_status",
        table_name="knowledge_sources",
    )
    op.drop_table("knowledge_sources")

    # The vector extension is platform infrastructure and may predate this revision.
    # Never drop a shared extension during an application-table rollback.
