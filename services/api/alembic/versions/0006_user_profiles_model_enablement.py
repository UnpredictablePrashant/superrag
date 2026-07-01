from __future__ import annotations

from alembic import op

revision = "0006_user_profiles_model_enablement"
down_revision = "0005_invitation_telegram_linking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS job_title varchar(160)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS department varchar(160)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number varchar(40)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_username varchar(160)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS location varchar(160)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS bio text")
    op.execute("ALTER TABLE model_profiles ADD COLUMN IF NOT EXISTS is_enabled boolean NOT NULL DEFAULT true")
    op.alter_column("model_profiles", "is_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("model_profiles", "is_enabled")
    op.drop_column("users", "bio")
    op.drop_column("users", "location")
    op.drop_column("users", "telegram_username")
    op.drop_column("users", "phone_number")
    op.drop_column("users", "department")
    op.drop_column("users", "job_title")
