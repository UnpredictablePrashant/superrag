# RAG Console

RAG Console is a production-minded multi-tenant Enterprise RAG SaaS starter. It includes a Next.js console, FastAPI backend, PostgreSQL with pgvector, Kafka-backed ingestion dispatch, Redis/Celery workers, backend-mediated MinIO/S3 uploads, Mailpit OTP email, deterministic local embeddings, hybrid retrieval, citations, Docker Compose, tests, and AWS Terraform starter files.

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Web: http://localhost:3000
- API docs: http://localhost:8000/docs
- Mailpit: http://localhost:8025
- MinIO console: http://localhost:9001

For local OTP, the API returns a development code when `ALLOW_DEV_AUTH_CODES=true`; Mailpit also receives the email.

## Useful Commands

```bash
docker compose down
docker compose exec api alembic upgrade head
docker compose exec api pytest
docker compose exec web npm run test
docker compose exec web npm run lint
```

## Deployment

GitHub Actions deployment to a single EC2 instance at `https://rag.atharvaai.com` is available in `.github/workflows/deploy-ec2.yml`. See `docs/ec2-deployment.md` for the required EC2 setup, GitHub secrets, repository variables, and production env file format.

## What Is Implemented

- Passwordless email OTP auth with expiry, resend cooldown, attempts, session cookies, logout, onboarding, invitations, and role checks.
- Organization-scoped data model for users, members, providers, knowledge bases, categories, documents, versions, profiles, chunks, vectors, pipeline runs, chat, notifications, audit logs, and usage metrics.
- Backend-mediated S3/MinIO uploads with immutable originals, checksum calculation, duplicate detection, version metadata, and soft delete.
- Kafka-backed pipeline dispatch with a dedicated pipeline worker, queued-run recovery, extraction, quality reports, cleanup profiles, review pauses, chunking profiles, deterministic embeddings, pgvector storage, notifications, retries, cancellation flags, and SSE pipeline progress.
- Hybrid retrieval using pgvector similarity, PostgreSQL full-text search, Reciprocal Rank Fusion, local reranking fallback, context assembly, citations, and tenant/access filters.
- Chat UI with sessions, streaming display, citation drawer, selected knowledge base, retrieval controls, and debug toggle.
- Settings pages for providers, capability registry, profiles, notifications, security posture, and audit logs.
- Telegram bot ingestion/querying, external MCP connector setup, and exposing this RAG workspace as an MCP server are documented in `docs/telegram.md` and `docs/mcp-connectors.md`.
- Relationship Intelligence workspace for investment-banking client, investor, contact, interaction, deal, evidence, and action-item views is documented in `docs/relationship-intelligence.md`.
- Terraform starter for S3, KMS, CloudWatch, and placeholders for ECS/Fargate, RDS pgvector, ElastiCache, ALB, and SES.

## Architecture Decisions

- The local embedding provider is deterministic and 384-dimensional so tests and demos do not require paid API keys.
- Provider credentials are encrypted at rest with Fernet locally and the code is KMS-ready for production.
- Retrieval filters by organization and document/category access rules before context assembly.
- Original files remain immutable in S3/MinIO; extraction, cleanup, redaction, and manual edits create derived content records.
- The worker shares the API domain package to avoid model drift while still running as a separate Compose service.

## Known Limitations

- The Terraform is a starter, not a complete VPC/ECS/RDS production deployment.
- OCR and malware scanning are represented as ready extension points; scanned PDFs are flagged for review.
- The deterministic answer generator is intentionally simple. Configure production chat providers before real customer use.
- pgvector storage is fixed to 384 dimensions in this starter table. New dimensions should be added through a controlled index-version migration.
- Row-level security is enabled in the migration, but application-level authorization carries the current enforcement. Add database RLS policies before production.

See `docs/` for deeper setup, architecture, schema, security, deployment, testing, and troubleshooting notes.
