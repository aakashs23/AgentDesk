"""Per-IP/per-user rate limiting (TRD Section 10).

Phase 3 (auth) and Phase 4 (ticket creation) attach this to their routes:

    @router.post("/login", dependencies=[Depends(rate_limit(10))])
"""

import time
from collections import defaultdict

from fastapi import HTTPException, Request

# ponytail: in-memory sliding window — single-process only. Move the buckets to
# Redis if the backend ever runs multiple workers.


def rate_limit(limit: int, window_seconds: float = 60.0):
    hits: dict[str, list[float]] = defaultdict(list)

    async def dependency(request: Request) -> None:
        # Authenticated callers are keyed per-user (their bearer token), anonymous per-IP
        key = request.headers.get("authorization") or (
            request.client.host if request.client else "unknown"
        )
        now = time.monotonic()
        bucket = [t for t in hits[key] if now - t < window_seconds]
        if len(bucket) >= limit:
            raise HTTPException(status_code=429, detail="Too many requests")
        bucket.append(now)
        hits[key] = bucket

    return dependency
