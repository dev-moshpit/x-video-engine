"""Presenter queue producer — Platform Phase 1."""

from __future__ import annotations

import os
import uuid
from typing import Optional

import redis
from pydantic import BaseModel


REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
PRESENTER_QUEUE_KEY = "saas:presenter:jobs"


_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(REDIS_URL, decode_responses=True)
    return _client


def set_redis(client: redis.Redis) -> None:
    global _client
    _client = client


class PresenterJobRequest(BaseModel):
    job_id: str
    user_id: str
    provider_id: str
    script: str
    avatar_image_url: str
    voice: Optional[str] = None
    voice_rate: str = "+0%"
    aspect_ratio: str = "9:16"
    headline: Optional[str] = None
    ticker: Optional[str] = None


def enqueue_presenter(req: PresenterJobRequest) -> str:
    get_redis().rpush(PRESENTER_QUEUE_KEY, req.model_dump_json())
    return req.job_id


def make_presenter_job_id() -> str:
    return f"pres_{uuid.uuid4().hex[:16]}"
