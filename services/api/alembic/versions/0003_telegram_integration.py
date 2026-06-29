from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_telegram_integration"
down_revision = "0002_flexible_embedding_dimensions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_integrations",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encrypted_bot_token", sa.Text(), nullable=True),
        sa.Column("masked_bot_token", sa.String(length=32), nullable=True),
        sa.Column("bot_username", sa.String(length=160), nullable=True),
        sa.Column("webhook_secret_token", sa.String(length=160), nullable=False),
        sa.Column("default_knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("default_chat_model_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("default_cleanup_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("default_chunking_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("default_embedding_profile_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("auto_ingest_text", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("auto_ingest_documents", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("auto_ingest_voice", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["default_chat_model_profile_id"], ["model_profiles.id"]),
        sa.ForeignKeyConstraint(["default_chunking_profile_id"], ["chunking_profiles.id"]),
        sa.ForeignKeyConstraint(["default_cleanup_profile_id"], ["cleanup_profiles.id"]),
        sa.ForeignKeyConstraint(["default_embedding_profile_id"], ["embedding_profiles.id"]),
        sa.ForeignKeyConstraint(["default_knowledge_base_id"], ["knowledge_bases.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id"),
    )
    op.create_index(
        op.f("ix_telegram_integrations_organization_id"),
        "telegram_integrations",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "telegram_allowed_users",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("username", sa.String(length=160), nullable=True),
        sa.Column("phone_number", sa.String(length=40), nullable=True),
        sa.Column("display_name", sa.String(length=220), nullable=True),
        sa.Column("can_ingest", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("can_query", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["integration_id"], ["telegram_integrations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("integration_id", "phone_number"),
        sa.UniqueConstraint("integration_id", "telegram_user_id"),
        sa.UniqueConstraint("integration_id", "username"),
    )
    op.create_index(
        op.f("ix_telegram_allowed_users_integration_id"),
        "telegram_allowed_users",
        ["integration_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_telegram_allowed_users_organization_id"),
        "telegram_allowed_users",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "telegram_message_logs",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_chat_id", sa.String(length=80), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("mode", sa.String(length=40), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="received"),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["integration_id"], ["telegram_integrations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("integration_id", "telegram_chat_id", "telegram_message_id"),
    )
    op.create_index(
        "ix_telegram_logs_org_created",
        "telegram_message_logs",
        ["organization_id", "created_at"],
        unique=False,
    )
    for table in ("telegram_integrations", "telegram_allowed_users", "telegram_message_logs"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM telegram_message_logs)
             OR EXISTS (SELECT 1 FROM telegram_allowed_users)
             OR EXISTS (SELECT 1 FROM telegram_integrations) THEN
            RAISE EXCEPTION
              'Cannot downgrade Telegram integration while Telegram data exists. '
              'Export or intentionally remove Telegram records before downgrading.';
          END IF;
        END $$;
        """
    )
    op.drop_index("ix_telegram_logs_org_created", table_name="telegram_message_logs")
    op.drop_table("telegram_message_logs")
    op.drop_index(op.f("ix_telegram_allowed_users_organization_id"), table_name="telegram_allowed_users")
    op.drop_index(op.f("ix_telegram_allowed_users_integration_id"), table_name="telegram_allowed_users")
    op.drop_table("telegram_allowed_users")
    op.drop_index(op.f("ix_telegram_integrations_organization_id"), table_name="telegram_integrations")
    op.drop_table("telegram_integrations")
