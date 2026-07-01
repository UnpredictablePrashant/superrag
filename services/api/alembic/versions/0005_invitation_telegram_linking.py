from __future__ import annotations

from alembic import op

revision = "0005_invitation_telegram_linking"
down_revision = "0004_connectors_company_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE organization_invitations ADD COLUMN IF NOT EXISTS telegram_user_id bigint")
    op.execute("ALTER TABLE organization_invitations ADD COLUMN IF NOT EXISTS telegram_username varchar(160)")
    op.execute("ALTER TABLE organization_invitations ADD COLUMN IF NOT EXISTS telegram_phone_number varchar(40)")
    op.execute(
        "ALTER TABLE organization_invitations ADD COLUMN IF NOT EXISTS telegram_can_ingest boolean NOT NULL DEFAULT true"
    )
    op.execute(
        "ALTER TABLE organization_invitations ADD COLUMN IF NOT EXISTS telegram_can_query boolean NOT NULL DEFAULT true"
    )
    op.alter_column("organization_invitations", "telegram_can_ingest", server_default=None)
    op.alter_column("organization_invitations", "telegram_can_query", server_default=None)


def downgrade() -> None:
    op.drop_column("organization_invitations", "telegram_can_query")
    op.drop_column("organization_invitations", "telegram_can_ingest")
    op.drop_column("organization_invitations", "telegram_phone_number")
    op.drop_column("organization_invitations", "telegram_username")
    op.drop_column("organization_invitations", "telegram_user_id")
