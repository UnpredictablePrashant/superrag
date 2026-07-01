from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005_invitation_telegram_linking"
down_revision = "0004_connectors_company_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organization_invitations", sa.Column("telegram_user_id", sa.BigInteger(), nullable=True))
    op.add_column("organization_invitations", sa.Column("telegram_username", sa.String(length=160), nullable=True))
    op.add_column("organization_invitations", sa.Column("telegram_phone_number", sa.String(length=40), nullable=True))
    op.add_column(
        "organization_invitations",
        sa.Column("telegram_can_ingest", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "organization_invitations",
        sa.Column("telegram_can_query", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("organization_invitations", "telegram_can_ingest", server_default=None)
    op.alter_column("organization_invitations", "telegram_can_query", server_default=None)


def downgrade() -> None:
    op.drop_column("organization_invitations", "telegram_can_query")
    op.drop_column("organization_invitations", "telegram_can_ingest")
    op.drop_column("organization_invitations", "telegram_phone_number")
    op.drop_column("organization_invitations", "telegram_username")
    op.drop_column("organization_invitations", "telegram_user_id")
