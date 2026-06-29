# Local Development

1. Copy `.env.example` to `.env`.
2. Run `docker compose up --build`.
3. Sign in at `http://localhost:3000`.
4. Use the dev OTP shown in the UI or check Mailpit at `http://localhost:8025`.
5. Create an organization and a knowledge base.
6. Upload `sample-data/employee-handbook.md`.
7. Start ingestion and open the pipeline detail page.
8. Ask a chat question such as `What is the leave policy?`.

Local services:

- PostgreSQL/pgvector: `localhost:5432`
- Redis: `localhost:6379`
- MinIO: `localhost:9000`, console `localhost:9001`
- Mailpit: SMTP `localhost:1025`, UI `localhost:8025`
