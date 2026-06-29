# Architecture

RAG Console is split into:

- `apps/web`: Next.js App Router console.
- `services/api`: FastAPI REST API, SQLAlchemy models, Alembic migrations, and Celery task definitions.
- `services/worker`: Compose service boundary for Celery workers using the API package.
- `packages/shared-types`: shared TypeScript domain types.
- `packages/ui`: accessible React primitives used by the console.
- `infrastructure/terraform`: AWS starter configuration.

## Request Flow

1. Browser authenticates with email OTP.
2. API sets an HTTP-only session cookie containing user, organization, and role claims.
3. API dependencies validate the session and membership for every organization-scoped route.
4. Uploads use presigned MinIO/S3 URLs. The API stores metadata and later verifies the object.
5. Pipeline creation writes `pipeline_runs` and `pipeline_run_documents`, then enqueues Celery.
6. The worker extracts, analyzes, cleans, chunks, embeds, and indexes content.
7. Chat runs authorization filters, hybrid retrieval, RRF, reranking fallback, context assembly, then returns grounded citations.

## Data Safety

Original S3 objects are immutable. Cleanup, redaction, and manual edits are derived records. Logs avoid raw document content.
