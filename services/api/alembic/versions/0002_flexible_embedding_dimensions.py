from __future__ import annotations

import uuid

import sqlalchemy as sa

from alembic import op

revision = "0002_flexible_embedding_dimensions"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_embedding_vectors_hnsw")
    op.execute(
        "ALTER TABLE embedding_vectors "
        "DROP CONSTRAINT IF EXISTS embedding_vectors_dimension_check"
    )
    op.execute(
        "ALTER TABLE embedding_vectors "
        "ALTER COLUMN embedding TYPE vector USING embedding::vector"
    )
    _ensure_local_embedding_profiles()
    _backfill_knowledge_base_embedding_defaults()


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM embedding_vectors WHERE embedding_dimension <> 384) THEN
            RAISE EXCEPTION
              'Cannot downgrade to vector(384): non-384-dimensional embeddings exist. '
              'Create a backup and re-index or remove those profiles explicitly before downgrading.';
          END IF;
        END $$;
        """
    )
    op.execute(
        "ALTER TABLE embedding_vectors "
        "ALTER COLUMN embedding TYPE vector(384) USING embedding::vector(384)"
    )
    op.create_check_constraint(
        "embedding_vectors_dimension_check",
        "embedding_vectors",
        "embedding_dimension = 384",
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_embedding_vectors_hnsw "
        "ON embedding_vectors USING hnsw (embedding vector_cosine_ops)"
    )


def _ensure_local_embedding_profiles() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT o.id AS organization_id
            FROM organizations o
            WHERE o.deleted_at IS NULL
              AND NOT EXISTS (
                SELECT 1
                FROM embedding_profiles ep
                WHERE ep.organization_id = o.id
                  AND ep.deleted_at IS NULL
              )
            """
        )
    ).mappings()
    for row in rows:
        bind.execute(
            sa.text(
                """
                INSERT INTO embedding_profiles (
                  id,
                  organization_id,
                  provider,
                  name,
                  model_name,
                  embedding_dimension,
                  batch_size,
                  normalization,
                  is_active,
                  config
                )
                VALUES (
                  :id,
                  :organization_id,
                  'LOCAL',
                  'Local deterministic embedding',
                  'deterministic-local-384',
                  384,
                  64,
                  'l2',
                  true,
                  '{}'::jsonb
                )
                """
            ),
            {"id": uuid.uuid4(), "organization_id": row["organization_id"]},
        )


def _backfill_knowledge_base_embedding_defaults() -> None:
    op.execute(
        """
        WITH ranked_profiles AS (
          SELECT
            ev.knowledge_base_id,
            ev.embedding_profile_id,
            ROW_NUMBER() OVER (
              PARTITION BY ev.knowledge_base_id
              ORDER BY COUNT(*) DESC, MAX(ev.created_at) DESC
            ) AS rank
          FROM embedding_vectors ev
          JOIN embedding_profiles ep ON ep.id = ev.embedding_profile_id
          WHERE ep.deleted_at IS NULL
          GROUP BY ev.knowledge_base_id, ev.embedding_profile_id
        )
        UPDATE knowledge_bases kb
        SET default_embedding_profile_id = ranked_profiles.embedding_profile_id
        FROM ranked_profiles
        WHERE kb.id = ranked_profiles.knowledge_base_id
          AND ranked_profiles.rank = 1
          AND kb.default_embedding_profile_id IS NULL
        """
    )
    op.execute(
        """
        WITH active_profiles AS (
          SELECT DISTINCT ON (ep.organization_id)
            ep.organization_id,
            ep.id AS embedding_profile_id
          FROM embedding_profiles ep
          WHERE ep.deleted_at IS NULL
          ORDER BY ep.organization_id, ep.is_active DESC, ep.created_at ASC
        )
        UPDATE knowledge_bases kb
        SET default_embedding_profile_id = active_profiles.embedding_profile_id
        FROM active_profiles
        WHERE kb.organization_id = active_profiles.organization_id
          AND kb.default_embedding_profile_id IS NULL
        """
    )
