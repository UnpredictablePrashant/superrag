# Architecture

RAG Console is split into:

- `apps/web`: Next.js App Router console.
- `services/api`: FastAPI REST API, SQLAlchemy models, Alembic migrations, Kafka dispatch, and Celery task definitions.
- `services/worker`: Compose service boundary for Celery workers using the API package.
- `pipeline-worker`: Kafka consumer for durable pipeline-run processing.
- `packages/shared-types`: shared TypeScript domain types.
- `packages/ui`: accessible React primitives used by the console.
- `infrastructure/terraform`: AWS starter configuration.

## Request Flow

1. Browser authenticates with email OTP.
2. API sets an HTTP-only session cookie containing user, organization, and role claims.
3. API dependencies validate the session and membership for every organization-scoped route.
4. Uploads post multipart form data to the API; the backend writes immutable originals to MinIO/S3 and records checksum metadata.
5. Pipeline creation writes `pipeline_runs` and `pipeline_run_documents`, then publishes a durable Kafka event.
6. The Kafka pipeline worker extracts, analyzes, cleans, chunks, embeds, and indexes content. Offsets are committed after processing; queued DB runs are recovered on worker startup.
7. Chat runs authorization filters, hybrid retrieval, RRF, reranking fallback, context assembly, then returns grounded citations.

## Data Safety

Original S3 objects are immutable. Cleanup, redaction, and manual edits are derived records. Logs avoid raw document content.
