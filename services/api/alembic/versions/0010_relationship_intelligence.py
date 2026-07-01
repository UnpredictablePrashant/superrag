from __future__ import annotations

from alembic import op

revision = "0010_relationship_intelligence"
down_revision = "0009_team_chat_attachments_public_channel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS relationship_entities (
          organization_id uuid NOT NULL REFERENCES organizations(id),
          name varchar(260) NOT NULL,
          normalized_name varchar(300) NOT NULL,
          entity_type varchar(40) NOT NULL,
          summary text NULL,
          sector varchar(180) NULL,
          geography varchar(180) NULL,
          website_url text NULL,
          relationship_owner_user_id uuid NULL REFERENCES users(id),
          last_interaction_at timestamptz NULL,
          next_action_at timestamptz NULL,
          confidence numeric NULL,
          status varchar(40) NOT NULL DEFAULT 'suggested',
          metadata jsonb NOT NULL DEFAULT '{}',
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          deleted_at timestamptz NULL,
          id uuid NOT NULL PRIMARY KEY,
          CONSTRAINT uq_relationship_entities_org_name_type UNIQUE (organization_id, normalized_name, entity_type)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_relationship_entities_org_type "
        "ON relationship_entities (organization_id, entity_type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_relationship_entities_org_last "
        "ON relationship_entities (organization_id, last_interaction_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS relationship_entity_aliases (
          organization_id uuid NOT NULL REFERENCES organizations(id),
          relationship_entity_id uuid NOT NULL REFERENCES relationship_entities(id) ON DELETE CASCADE,
          alias varchar(260) NOT NULL,
          normalized_alias varchar(300) NOT NULL,
          source_type varchar(80) NOT NULL DEFAULT 'extraction',
          confidence numeric NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          id uuid NOT NULL PRIMARY KEY,
          CONSTRAINT uq_relationship_alias_org_normalized UNIQUE (organization_id, normalized_alias)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_relationship_aliases_entity "
        "ON relationship_entity_aliases (relationship_entity_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS relationship_roles (
          organization_id uuid NOT NULL REFERENCES organizations(id),
          relationship_entity_id uuid NOT NULL REFERENCES relationship_entities(id) ON DELETE CASCADE,
          role_name varchar(80) NOT NULL,
          confidence numeric NULL,
          metadata jsonb NOT NULL DEFAULT '{}',
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          id uuid NOT NULL PRIMARY KEY,
          CONSTRAINT uq_relationship_roles_entity_role UNIQUE (relationship_entity_id, role_name)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_relationship_roles_org_role "
        "ON relationship_roles (organization_id, role_name)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deals (
          organization_id uuid NOT NULL REFERENCES organizations(id),
          name varchar(260) NOT NULL,
          deal_type varchar(80) NOT NULL DEFAULT 'opportunity',
          stage varchar(80) NOT NULL DEFAULT 'identified',
          company_entity_id uuid NULL REFERENCES relationship_entities(id),
          relationship_owner_user_id uuid NULL REFERENCES users(id),
          amount numeric NULL,
          currency varchar(20) NULL,
          expected_close_date timestamptz NULL,
          summary text NULL,
          confidence numeric NULL,
          status varchar(40) NOT NULL DEFAULT 'suggested',
          metadata jsonb NOT NULL DEFAULT '{}',
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          deleted_at timestamptz NULL,
          id uuid NOT NULL PRIMARY KEY
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_deals_org_stage ON deals (organization_id, stage)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_deals_org_company ON deals (organization_id, company_entity_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deal_participants (
          organization_id uuid NOT NULL REFERENCES organizations(id),
          deal_id uuid NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
          relationship_entity_id uuid NOT NULL REFERENCES relationship_entities(id) ON DELETE CASCADE,
          role_name varchar(80) NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          id uuid NOT NULL PRIMARY KEY,
          CONSTRAINT uq_deal_participants_deal_entity_role UNIQUE (deal_id, relationship_entity_id, role_name)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_deal_participants_entity "
        "ON deal_participants (organization_id, relationship_entity_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS interactions (
          organization_id uuid NOT NULL REFERENCES organizations(id),
          title varchar(300) NOT NULL,
          interaction_type varchar(80) NOT NULL DEFAULT 'note',
          occurred_at timestamptz NULL,
          source_type varchar(80) NOT NULL,
          source_url text NULL,
          document_id uuid NULL REFERENCES documents(id),
          connector_item_id uuid NULL REFERENCES connector_items(id),
          summary text NULL,
          status varchar(40) NOT NULL DEFAULT 'suggested',
          metadata jsonb NOT NULL DEFAULT '{}',
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          id uuid NOT NULL PRIMARY KEY
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_interactions_org_occurred "
        "ON interactions (organization_id, occurred_at)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_interactions_document ON interactions (document_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS interaction_participants (
          organization_id uuid NOT NULL REFERENCES organizations(id),
          interaction_id uuid NOT NULL REFERENCES interactions(id) ON DELETE CASCADE,
          relationship_entity_id uuid NOT NULL REFERENCES relationship_entities(id) ON DELETE CASCADE,
          role_name varchar(80) NOT NULL DEFAULT 'mentioned',
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          id uuid NOT NULL PRIMARY KEY,
          CONSTRAINT uq_interaction_participants_interaction_entity_role
            UNIQUE (interaction_id, relationship_entity_id, role_name)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_interaction_participants_entity "
        "ON interaction_participants (organization_id, relationship_entity_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS action_items (
          organization_id uuid NOT NULL REFERENCES organizations(id),
          title varchar(300) NOT NULL,
          description text NULL,
          relationship_entity_id uuid NULL REFERENCES relationship_entities(id),
          deal_id uuid NULL REFERENCES deals(id),
          interaction_id uuid NULL REFERENCES interactions(id),
          owner_user_id uuid NULL REFERENCES users(id),
          due_at timestamptz NULL,
          priority varchar(40) NOT NULL DEFAULT 'medium',
          status varchar(40) NOT NULL DEFAULT 'open',
          source_type varchar(80) NOT NULL DEFAULT 'extraction',
          confidence numeric NULL,
          metadata jsonb NOT NULL DEFAULT '{}',
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          id uuid NOT NULL PRIMARY KEY
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_action_items_org_status_due "
        "ON action_items (organization_id, status, due_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_action_items_entity "
        "ON action_items (organization_id, relationship_entity_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS relationship_evidence (
          organization_id uuid NOT NULL REFERENCES organizations(id),
          relationship_entity_id uuid NULL REFERENCES relationship_entities(id),
          deal_id uuid NULL REFERENCES deals(id),
          interaction_id uuid NULL REFERENCES interactions(id),
          action_item_id uuid NULL REFERENCES action_items(id),
          document_id uuid NULL REFERENCES documents(id),
          chunk_id uuid NULL REFERENCES chunks(id),
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
        "CREATE INDEX IF NOT EXISTS ix_relationship_evidence_entity_field "
        "ON relationship_evidence (relationship_entity_id, field_name)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_relationship_evidence_document "
        "ON relationship_evidence (document_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_mentions (
          organization_id uuid NOT NULL REFERENCES organizations(id),
          relationship_entity_id uuid NOT NULL REFERENCES relationship_entities(id) ON DELETE CASCADE,
          document_id uuid NULL REFERENCES documents(id),
          chunk_id uuid NULL REFERENCES chunks(id),
          mention_text varchar(260) NOT NULL,
          normalized_mention varchar(300) NOT NULL,
          context text NULL,
          confidence numeric NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          id uuid NOT NULL PRIMARY KEY
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_entity_mentions_entity ON entity_mentions (relationship_entity_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_entity_mentions_document ON entity_mentions (document_id)")

    for table in (
        "relationship_entities",
        "relationship_entity_aliases",
        "relationship_roles",
        "deals",
        "deal_participants",
        "interactions",
        "interaction_participants",
        "action_items",
        "relationship_evidence",
        "entity_mentions",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS entity_mentions")
    op.execute("DROP TABLE IF EXISTS relationship_evidence")
    op.execute("DROP TABLE IF EXISTS action_items")
    op.execute("DROP TABLE IF EXISTS interaction_participants")
    op.execute("DROP TABLE IF EXISTS interactions")
    op.execute("DROP TABLE IF EXISTS deal_participants")
    op.execute("DROP TABLE IF EXISTS deals")
    op.execute("DROP TABLE IF EXISTS relationship_roles")
    op.execute("DROP TABLE IF EXISTS relationship_entity_aliases")
    op.execute("DROP TABLE IF EXISTS relationship_entities")
