# Troubleshooting

## OTP email does not arrive

Open Mailpit at `http://localhost:8025`. If `ALLOW_DEV_AUTH_CODES=true`, the API response also includes the code in local mode.

## Upload fails with CORS

Confirm the web app is calling the API upload route (`/api/uploads`) rather than a direct S3 URL. If the API returns a storage error, check MinIO/S3 credentials, bucket creation, and network access from the backend.

## Pipeline stays queued

Check the worker logs:

```bash
docker compose logs -f pipeline-worker
```

Also verify Kafka is healthy and the pipeline topic is available:

```bash
docker compose logs kafka
docker compose exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:19092 --list
```

If Kafka is disabled, pipeline dispatch falls back to Celery; check `docker compose logs -f worker` and Redis health.

## API cannot connect to storage

Check MinIO health and bucket creation:

```bash
docker compose logs minio minio-init
```

## Retrieval returns no answer

Confirm the document pipeline reached `COMPLETED` or `COMPLETED_WITH_WARNINGS`, the chat has the correct knowledge base selected, and the user has access to the document/category.
