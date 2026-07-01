from __future__ import annotations

from alembic import op

revision = "0009_team_chat_attachments_public_channel"
down_revision = "0008_member_presence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE team_chat_conversations ADD COLUMN IF NOT EXISTS is_public boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE team_chat_conversations ADD COLUMN IF NOT EXISTS is_default boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE team_chat_messages ADD COLUMN IF NOT EXISTS message_type varchar(40) NOT NULL DEFAULT 'text'")
    op.execute("ALTER TABLE team_chat_messages ADD COLUMN IF NOT EXISTS attachments jsonb NOT NULL DEFAULT '[]'::jsonb")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_team_chat_default_channel
        ON team_chat_conversations (organization_id)
        WHERE is_default = true AND is_archived = false
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_team_chat_default_channel")
    op.drop_column("team_chat_messages", "attachments")
    op.drop_column("team_chat_messages", "message_type")
    op.drop_column("team_chat_conversations", "is_default")
    op.drop_column("team_chat_conversations", "is_public")
