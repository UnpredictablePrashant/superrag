from __future__ import annotations

from alembic import op

revision = "0008_member_presence"
down_revision = "0007_team_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'chatpresencestatus') THEN
                CREATE TYPE chatpresencestatus AS ENUM ('ONLINE', 'BUSY', 'AWAY', 'DO_NOT_DISTURB', 'OFFLINE');
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        ALTER TABLE organization_members
        ADD COLUMN IF NOT EXISTS chat_status chatpresencestatus NOT NULL DEFAULT 'OFFLINE'
        """
    )
    op.execute("ALTER TABLE organization_members ADD COLUMN IF NOT EXISTS status_message varchar(160)")
    op.execute("ALTER TABLE organization_members ADD COLUMN IF NOT EXISTS status_updated_at timestamptz")
    op.execute("ALTER TABLE organization_members ALTER COLUMN chat_status DROP DEFAULT")


def downgrade() -> None:
    op.drop_column("organization_members", "status_updated_at")
    op.drop_column("organization_members", "status_message")
    op.drop_column("organization_members", "chat_status")
    op.execute("DROP TYPE IF EXISTS chatpresencestatus")
