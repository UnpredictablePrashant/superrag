from __future__ import annotations

from collections import defaultdict, deque
from time import time

from fastapi import HTTPException, status

from app.core.config import settings

_buckets: dict[str, deque[float]] = defaultdict(deque)


def enforce_rate_limit(key: str, limit: int | None = None, window_seconds: int = 60) -> None:
    limit = limit or settings.rate_limit_per_minute
    now = time()
    bucket = _buckets[key]
    while bucket and bucket[0] <= now - window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please wait and try again.",
        )
    bucket.append(now)
