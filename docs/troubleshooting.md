# Troubleshooting

## OTP email does not arrive

Open Mailpit at `http://localhost:8025`. If `ALLOW_DEV_AUTH_CODES=true`, the API response also includes the code in local mode.

## Upload fails with CORS

Confirm `minio-init` ran successfully and that the browser is using `http://localhost:9000` presigned URLs.

## Pipeline stays queued

Check the worker logs:

```bash
docker compose logs -f worker
```

Also verify Redis is healthy.

## API cannot connect to storage

Check MinIO health and bucket creation:

```bash
docker compose logs minio minio-init
```

## Retrieval returns no answer

Confirm the document pipeline reached `COMPLETED` or `COMPLETED_WITH_WARNINGS`, the chat has the correct knowledge base selected, and the user has access to the document/category.
