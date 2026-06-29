from __future__ import annotations

from alembic import op
from app.db.base import Base
from app.models import entities  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunks_fts "
        "ON chunks USING gin (to_tsvector('english', coalesce(text, '')))"
    )
    for table in (
        "organizations",
        "organization_members",
        "provider_connections",
        "knowledge_bases",
        "categories",
        "documents",
        "document_versions",
        "document_access_rules",
        "document_quality_reports",
        "derived_document_content",
        "chunks",
        "embedding_vectors",
        "pipeline_runs",
        "chat_sessions",
        "chat_messages",
        "retrieval_events",
        "notifications",
        "audit_logs",
        "telegram_integrations",
        "telegram_allowed_users",
        "telegram_message_logs",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
    op.execute("DROP EXTENSION IF EXISTS vector")
