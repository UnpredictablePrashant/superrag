# Testing

Backend unit tests focus on deterministic, security-sensitive behavior:

- OTP hashing.
- Cleanup and redaction.
- Quality analysis.
- Chunking strategies.
- Deterministic embeddings.
- RRF/reranking fallback.
- ETA calculation.
- S3 key generation.

Frontend tests use Vitest and Testing Library for rendering and state behavior. E2E tests use Playwright and expect the full Docker Compose stack.

Commands:

```bash
docker compose exec api pytest
docker compose exec web npm run test
npm run e2e
```
