"""Redis queue producer (PR 6).

The api never consumes — that's the worker's job. This module just
pushes ``RenderJobRequest`` payloads onto a Redis list and exposes a
test hook to swap the client for ``fakeredis``.

Frontend polls ``GET /api/renders/{id}`` for status updates rather
than streaming. SSE / pub-sub may come later if poll volume ever
becomes a problem (PR 14+).
"""

from __future__ import annotations

import os
from typing import Optional

import redis

from app.schemas.render import RenderJobRequest


REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
QUEUE_KEY = "saas:render:jobs"


_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(REDIS_URL, decode_responses=True)
    return _client


def set_redis(client: redis.Redis) -> None:
    """Test hook: swap in a fakeredis client."""
    global _client
    _client = client


def enqueue_render(req: RenderJobRequest) -> str:
    """Push a render job to the queue. Returns the job_id."""
    get_redis().rpush(QUEUE_KEY, req.model_dump_json())
    return req.job_id
