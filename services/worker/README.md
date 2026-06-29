The worker service uses the same Python image as `services/api` and starts Celery with:

```bash
celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --include=app.workers.tasks
```

Keeping the worker code in `services/api/app/workers` avoids duplicate domain models while preserving the requested monorepo service boundary.
