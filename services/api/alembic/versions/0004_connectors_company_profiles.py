from __future__ import annotations

from alembic import op

revision = "0004_connectors_company_profiles"
down_revision = "0003_telegram_integration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS connector_connections (
          organization_id uuid NOT NULL REFERENCES organizations(id),
          user_id uuid NULL REFERENCES users(id),
          scope varchar(40) NOT NULL DEFAULT 'user',
          kind varchar(40) NOT NULL,
          name varchar(160) NOT NULL,
          encrypted_secret text NULL,
          masked_secret varchar(32) NULL,
          base_url text NULL,
          status varchar(40) NOT NULL DEFAULT 'untested',
          is_enabled boolean NOT NULL DEFAULT true,
          config jsonb NOT NULL DEFAULT '{}',
          last_synced_at timestamptz NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          deleted_at timestamptz NULL,
          id uuid NOT NULL PRIMARY KEY
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_connector_connections_org_user_name
        ON connector_connections (organization_id, user_id, name)
        WHERE scope = 'user' AND deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_connector_connections_org_name
        ON connector_connections (organization_id, name)
        WHERE scope = 'organization' AND deleted_at IS NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_connector_connections_org_kind "
        "ON connector_connections (organization_id, kind)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_connector_connections_user_id "
        "ON connector_connections (user_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS connector_runs (
          organization_id uuid NOT NULL REFERENCES organizations(id),
          connector_connection_id uuid NOT NULL REFERENCES connector_connections(id) ON DELETE CASCADE,
          requested_by_user_id uuid NULL REFERENCES users(id),
          status varchar(40) NOT NULL DEFAULT 'queued',
          options jsonb NOT NULL DEFAULT '{}',
          total_items integer NOT NULL DEFAULT 0,
          processed_items integer NOT NULL DEFAULT 0,
          error text NULL,
          logs jsonb NOT NULL DEFAULT '[]',
          started_at timestamptz NULL,
          completed_at timestamptz NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          id uuid NOT NULL PRIMARY KEY
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_connector_runs_connection "
        "ON connector_runs (connector_connection_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_connector_runs_org_created "
        "ON connector_runs (organization_id, created_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS connector_items (
          organization_id uuid NOT NULL REFERENCES organizations(id),
          connector_connection_id uuid NOT NULL REFERENCES connector_connections(id) ON DELETE CASCADE,
          connector_run_id uuid NULL REFERENCES connector_runs(id),
          document_id uuid NULL REFERENCES documents(id),
          external_id text NOT NULL,
          title varchar(500) NOT NULL,
          source_url text NULL,
          content_type varchar(120) NULL,
          checksum varchar(64) NULL,
          status varchar(40) NOT NULL DEFAULT 'discovered',
          metadata jsonb NOT NULL DEFAULT '{}',
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          id uuid NOT NULL PRIMARY KEY,
          CONSTRAINT uq_connector_items_connection_external UNIQUE (connector_connection_id, external_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_connector_items_org_connection "
        "ON connector_items (organization_id, connector_connection_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_connector_items_checksum "
        "ON connector_items (checksum)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_profiles (
          organization_id uuid NOT NULL REFERENCES organizations(id),
          name varchar(240) NOT NULL,
          normalized_name varchar(260) NOT NULL,
          website_url text NULL,
          description text NULL,
          industry varchar(200) NULL,
          headquarters varchar(240) NULL,
          finance_summary jsonb NOT NULL DEFAULT '{}',
          metadata jsonb NOT NULL DEFAULT '{}',
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          deleted_at timestamptz NULL,
          id uuid NOT NULL PRIMARY KEY,
          CONSTRAINT uq_company_profiles_org_normalized UNIQUE (organization_id, normalized_name)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_company_profiles_org_name "
        "ON company_profiles (organization_id, normalized_name)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS company_evidence (
          organization_id uuid NOT NULL REFERENCES organizations(id),
          company_profile_id uuid NOT NULL REFERENCES company_profiles(id) ON DELETE CASCADE,
          document_id uuid NULL REFERENCES documents(id),
          connector_item_id uuid NULL REFERENCES connector_items(id),
          field_name varchar(120) NOT NULL,
          source_type varchar(80) NOT NULL,
          source_url text NULL,
          excerpt text NULL,
          confidence numeric NULL,
          metadata jsonb NOT NULL DEFAULT '{}',
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          id uuid NOT NULL PRIMARY KEY
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_company_evidence_profile_field "
        "ON company_evidence (company_profile_id, field_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_company_evidence_org "
        "ON company_evidence (organization_id)"
    )

    for table in (
        "connector_connections",
        "connector_runs",
        "connector_items",
        "company_profiles",
        "company_evidence",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM connector_items)
             OR EXISTS (SELECT 1 FROM connector_runs)
             OR EXISTS (SELECT 1 FROM connector_connections)
             OR EXISTS (SELECT 1 FROM company_evidence)
             OR EXISTS (SELECT 1 FROM company_profiles) THEN
            RAISE EXCEPTION
              'Cannot downgrade connector/company profile migration while connector data exists. '
              'Export or intentionally remove records before downgrading.';
          END IF;
        END $$;
        """
    )
    op.execute("DROP TABLE IF EXISTS company_evidence")
    op.execute("DROP TABLE IF EXISTS company_profiles")
    op.execute("DROP TABLE IF EXISTS connector_items")
    op.execute("DROP TABLE IF EXISTS connector_runs")
    op.execute("DROP TABLE IF EXISTS connector_connections")
