from __future__ import annotations

from alembic import op

revision = "0007_team_chat"
down_revision = "0006_user_profiles_model_enablement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS team_chat_conversations (
            id uuid PRIMARY KEY,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            kind varchar(40) NOT NULL,
            name varchar(160),
            description text,
            created_by_user_id uuid NOT NULL REFERENCES users(id),
            direct_key varchar(160),
            is_archived boolean NOT NULL DEFAULT false,
            last_message_at timestamptz,
            UNIQUE (organization_id, direct_key)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_team_chat_conversations_organization_id ON team_chat_conversations (organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_team_chat_conversations_created_by_user_id ON team_chat_conversations (created_by_user_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_team_chat_conversations_org_last ON team_chat_conversations (organization_id, last_message_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS team_chat_participants (
            id uuid PRIMARY KEY,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            conversation_id uuid NOT NULL REFERENCES team_chat_conversations(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role varchar(40) NOT NULL DEFAULT 'member',
            last_read_at timestamptz,
            UNIQUE (conversation_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_team_chat_participants_organization_id ON team_chat_participants (organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_team_chat_participants_conversation_id ON team_chat_participants (conversation_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_team_chat_participants_user_id ON team_chat_participants (user_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_team_chat_participants_user ON team_chat_participants (organization_id, user_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS team_chat_messages (
            id uuid PRIMARY KEY,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            organization_id uuid NOT NULL REFERENCES organizations(id),
            conversation_id uuid NOT NULL REFERENCES team_chat_conversations(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES users(id),
            content text NOT NULL,
            edited_at timestamptz,
            deleted_at timestamptz
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_team_chat_messages_organization_id ON team_chat_messages (organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_team_chat_messages_conversation_id ON team_chat_messages (conversation_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_team_chat_messages_user_id ON team_chat_messages (user_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_team_chat_messages_conversation_created ON team_chat_messages (conversation_id, created_at)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_team_chat_messages_org_created ON team_chat_messages (organization_id, created_at)")


def downgrade() -> None:
    op.drop_table("team_chat_messages")
    op.drop_table("team_chat_participants")
    op.drop_table("team_chat_conversations")
