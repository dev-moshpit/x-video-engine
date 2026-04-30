"""Publishing-target queue producer — Platform Phase 1."""

from __future__ import annotations

import os
import uuid
from typing import Optional

import redis
from pydantic import BaseModel


REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
PUBLISH_QUEUE_KEY = "saas:publish:jobs"


_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(REDIS_URL, decode_responses=True)
    return _client


def set_redis(client: redis.Redis) -> None:
    global _client
    _client = client


class PublishingJobRequest(BaseModel):
    job_id: str
    user_id: str
    provider_id: str
    video_url: str
    title: str
    description: str = ""
    tags: list[str] = []
    privacy: str = "private"


def enqueue_publishing(req: PublishingJobRequest) -> str:
    get_redis().rpush(PUBLISH_QUEUE_KEY, req.model_dump_json())
    return req.job_id


def make_publishing_job_id() -> str:
    return f"pub_{uuid.uuid4().hex[:16]}"
