# Database Schema

The Alembic migration creates normalized PostgreSQL tables for:

`users`, `organizations`, `organization_members`, `organization_invitations`, `otp_codes`, `sessions`, `provider_connections`, `model_profiles`, `knowledge_bases`, `categories`, `documents`, `document_versions`, `document_access_rules`, `document_quality_reports`, `derived_document_content`, `cleanup_profiles`, `chunking_profiles`, `embedding_profiles`, `chunks`, `embedding_vectors`, `pipeline_runs`, `pipeline_run_documents`, `pipeline_tasks`, `chat_sessions`, `chat_messages`, `retrieval_events`, `notifications`, `notification_preferences`, `audit_logs`, and `usage_metrics`.

Important constraints:

- UUID primary keys.
- Organization ID on tenant records.
- Soft deletion on mutable business objects.
- pgvector extension and HNSW index for `embedding_vectors.embedding`.
- GIN full-text index over chunk text.
- Unique constraints for memberships, invitations, document versions, and vector profile/chunk pairs.

RLS is enabled by the migration. Production deployments should add explicit RLS policies that mirror the application authorization model.
