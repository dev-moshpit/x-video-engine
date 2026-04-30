"""Video-generation queue producer — Platform Phase 1."""

from __future__ import annotations

import os
import uuid
from typing import Optional

import redis
from pydantic import BaseModel


REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
GENERATION_QUEUE_KEY = "saas:videogen:jobs"


_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(REDIS_URL, decode_responses=True)
    return _client


def set_redis(client: redis.Redis) -> None:
    global _client
    _client = client


class GenerationJobRequest(BaseModel):
    job_id: str
    user_id: str
    provider_id: str
    prompt: str
    image_url: Optional[str] = None
    duration_seconds: float = 4.0
    fps: int = 24
    aspect_ratio: str = "9:16"
    seed: Optional[int] = None
    extra: dict = {}


def enqueue_generation(req: GenerationJobRequest) -> str:
    get_redis().rpush(GENERATION_QUEUE_KEY, req.model_dump_json())
    return req.job_id


def make_generation_job_id() -> str:
    return f"vg_{uuid.uuid4().hex[:16]}"
