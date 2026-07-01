from __future__ import annotations

from alembic import op

revision = "0011_relationship_scan_runs"
down_revision = "0010_relationship_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS relationship_scan_runs (
          organization_id uuid NOT NULL REFERENCES organizations(id),
          requested_by_user_id uuid NULL REFERENCES users(id),
          scan_type varchar(80) NOT NULL DEFAULT 'documents',
          status varchar(40) NOT NULL DEFAULT 'queued',
          options jsonb NOT NULL DEFAULT '{}',
          total_count integer NOT NULL DEFAULT 0,
          processed_count integer NOT NULL DEFAULT 0,
          last_scanned_document_id uuid NULL REFERENCES documents(id),
          result jsonb NOT NULL DEFAULT '{}',
          error text NULL,
          started_at timestamptz NULL,
          completed_at timestamptz NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          id uuid NOT NULL PRIMARY KEY
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_relationship_scan_runs_org_status "
        "ON relationship_scan_runs (organization_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_relationship_scan_runs_org_created "
        "ON relationship_scan_runs (organization_id, created_at)"
    )
    op.execute("ALTER TABLE relationship_scan_runs ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS relationship_scan_runs")
