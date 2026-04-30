"""AI Clipper queue producer + helpers — Platform Phase 1.

Two distinct queues so analyze and export can be scaled independently:

  saas:clipper:analyze   long-form → moments (heavy: faster-whisper)
  saas:clipper:export    one moment → mp4 (cheap: ffmpeg only)

The api never consumes — that's the worker's job.
"""

from __future__ import annotations

import os
import uuid
from typing import Optional

import redis
from pydantic import BaseModel


REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
ANALYZE_QUEUE_KEY = "saas:clipper:analyze"
EXPORT_QUEUE_KEY = "saas:clipper:export"


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


# ─── Wire payloads ─────────────────────────────────────────────────────


class ClipAnalyzeRequest(BaseModel):
    """Push payload for the analyze queue."""
    job_id: str
    user_id: str
    source_url: str
    source_kind: str = "video"
    language: str = "auto"


class ClipExportRequest(BaseModel):
    """Push payload for the export queue."""
    artifact_id: str
    job_id: str
    user_id: str
    source_url: str
    moment: dict          # serialized Moment (start, end, segments...)
    aspect: str
    captions: bool


def enqueue_analyze(req: ClipAnalyzeRequest) -> str:
    get_redis().rpush(ANALYZE_QUEUE_KEY, req.model_dump_json())
    return req.job_id


def enqueue_export(req: ClipExportRequest) -> str:
    get_redis().rpush(EXPORT_QUEUE_KEY, req.model_dump_json())
    return req.artifact_id


def make_job_id() -> str:
    return f"clip_{uuid.uuid4().hex[:16]}"
