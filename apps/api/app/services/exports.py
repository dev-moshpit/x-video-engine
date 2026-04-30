"""Export-variant queue producer — Phase 13.5.

A separate Redis list (``saas:export:jobs``) so export jobs don't
backpressure the main render queue. The worker side lives in
``apps/worker/queue.py::consume_export_one`` (added in tandem).
"""

from __future__ import annotations

import os
from typing import Optional

import redis
from pydantic import BaseModel


REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
EXPORT_QUEUE_KEY = "saas:export:jobs"


_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(REDIS_URL, decode_responses=True)
    return _client


def set_redis(client: redis.Redis) -> None:
    global _client
    _client = client


class ExportJobRequest(BaseModel):
    """Payload pushed onto the export queue.

    The worker reads ``src_url`` directly (R2 / MinIO public URL) so it
    doesn't need DB access to find the source. ``artifact_id`` is the
    DB row the worker updates with status / final url when done.
    """
    artifact_id: str
    render_id: str
    user_id: str
    job_id: str
    src_url: str
    aspect: str
    captions: bool


def enqueue_export(req: ExportJobRequest) -> str:
    get_redis().rpush(EXPORT_QUEUE_KEY, req.model_dump_json())
    return req.artifact_id
