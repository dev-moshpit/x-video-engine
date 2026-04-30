"""Editor queue producer — Platform Phase 1."""

from __future__ import annotations

import os
import uuid
from typing import Optional

import redis
from pydantic import BaseModel


REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
EDITOR_QUEUE_KEY = "saas:editor:jobs"


_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(REDIS_URL, decode_responses=True)
    return _client


def set_redis(client: redis.Redis) -> None:
    """Test hook — install fakeredis."""
    global _client
    _client = client


class EditorJobRequest(BaseModel):
    """Push payload for the editor queue."""
    job_id: str
    user_id: str
    source_url: str
    trim_start: Optional[float] = None
    trim_end: Optional[float] = None
    aspect: str = "9:16"
    captions: bool = True
    caption_language: str = "auto"


def enqueue_editor(req: EditorJobRequest) -> str:
    get_redis().rpush(EDITOR_QUEUE_KEY, req.model_dump_json())
    return req.job_id


def make_editor_job_id() -> str:
    return f"edit_{uuid.uuid4().hex[:16]}"
