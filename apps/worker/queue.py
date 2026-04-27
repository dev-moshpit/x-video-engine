"""Worker-side Redis queue + DB status writer (PR 6).

Same Redis list key as ``apps/api/app/services/queue.py``. The worker
BLPOPs jobs off the queue and writes status updates back to Postgres
via SQLAlchemy core (raw ``UPDATE`` on the ``renders`` table) so it
doesn't have to import the api's ORM models — keeps the worker
independently deployable.

Status update happy path per job:
  PENDING (set by api)
    → RENDERING        (worker picks up)
    → COMPLETE         (final_mp4 produced; PR 7 adds final_mp4_url)
  or
    → FAILED           (any exception)

PR 7 inserts UPLOADING between RENDERING and COMPLETE.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import redis
from sqlalchemy import create_engine, text

from apps.worker.schemas import RenderJobRequest, RenderStage


logger = logging.getLogger(__name__)


REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
QUEUE_KEY = "saas:render:jobs"

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://saas:saas@localhost:5432/saas",
)


# ─── Redis client (test-swappable) ──────────────────────────────────────

_redis_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def set_redis(client: redis.Redis) -> None:
    global _redis_client
    _redis_client = client


# ─── DB engine (test-swappable) ─────────────────────────────────────────

def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool
        return {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    return {}


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            DATABASE_URL, future=True, **_engine_kwargs(DATABASE_URL)
        )
    return _engine


def set_engine(engine) -> None:
    global _engine
    _engine = engine


# ─── Queue ──────────────────────────────────────────────────────────────

def consume_one(timeout_sec: int = 5) -> Optional[RenderJobRequest]:
    """BLPOP one job off the queue. None on timeout."""
    res = get_redis().blpop([QUEUE_KEY], timeout=timeout_sec)
    if res is None:
        return None
    _key, raw = res
    return RenderJobRequest.model_validate_json(raw)


# ─── Status writes ──────────────────────────────────────────────────────

def update_render_status(
    job_id: str,
    *,
    stage: Optional[str] = None,
    progress: Optional[float] = None,
    final_mp4_url: Optional[str] = None,
    error: Optional[str] = None,
    set_completed_now: bool = False,
) -> None:
    """Update the ``renders`` row matching ``job_id`` (raw SQL, no ORM)."""
    sets: list[str] = []
    params: dict = {"job_id": job_id}
    if stage is not None:
        sets.append("stage = :stage")
        params["stage"] = stage
    if progress is not None:
        sets.append("progress = :progress")
        params["progress"] = float(progress)
    if final_mp4_url is not None:
        sets.append("final_mp4_url = :final_mp4_url")
        params["final_mp4_url"] = final_mp4_url
    if error is not None:
        sets.append("error = :error")
        params["error"] = error
    if set_completed_now:
        sets.append("completed_at = :completed_at")
        params["completed_at"] = datetime.now(timezone.utc)

    if not sets:
        return

    sql = f"UPDATE renders SET {', '.join(sets)} WHERE job_id = :job_id"
    with get_engine().begin() as conn:
        conn.execute(text(sql), params)


def mark_stage(job_id: str, stage: RenderStage, *, progress: float) -> None:
    is_terminal = stage in (RenderStage.COMPLETE, RenderStage.FAILED)
    update_render_status(
        job_id,
        stage=stage.value,
        progress=progress,
        set_completed_now=is_terminal,
    )
