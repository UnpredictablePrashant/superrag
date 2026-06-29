# Local Development

1. Copy `.env.example` to `.env`.
2. Run `docker compose up --build`.
3. Sign in at `http://localhost:3000`.
4. Use the dev OTP shown in the UI or check Mailpit at `http://localhost:8025`.
5. Create an organization and a knowledge base.
6. Upload `sample-data/employee-handbook.md`.
7. Start ingestion and open the pipeline detail page.
8. Ask a chat question such as `What is the leave policy?`.

Embedding data migrations:

- To migrate an already-indexed document set to a new embedding profile without deleting existing chunks or vectors, create a pipeline run with `retrieval_index_config: {"migration_mode": "embedding_backfill"}` and the target `embedding_profile_id`.
- The backfill mode only embeds existing chunks that are missing vectors for the target profile. It preserves old vectors and switches the knowledge base default embedding profile only after the run completes successfully.

Local services:

- PostgreSQL/pgvector: `localhost:5432`
- Redis: `localhost:6379`
- MinIO: `localhost:9000`, console `localhost:9001`
- Mailpit: SMTP `localhost:1025`, UI `localhost:8025`
