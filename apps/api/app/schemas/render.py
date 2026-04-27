"""Render-job wire schemas (PR 6).

This is the contract between ``apps/api`` (producer) and
``apps/worker`` (consumer). The same shapes get *copied* to
``apps/worker/schemas.py`` so the worker stays deployable to a
separate machine — same precedent as ``worker_runtime/schemas.py``.

A drift test in ``tests/worker/test_queue_consumer.py`` compares the
two copies and fails loudly if they diverge.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class RenderStage(str, Enum):
    PENDING = "pending"
    SCRIPTING = "scripting"
    RENDERING = "rendering"
    POSTPROCESS = "postprocess"
    UPLOADING = "uploading"
    COMPLETE = "complete"
    FAILED = "failed"


TERMINAL_STAGES = {RenderStage.COMPLETE, RenderStage.FAILED}


class RenderJobRequest(BaseModel):
    """Payload pushed onto the Redis queue for the worker."""
    job_id: str            # short uuid hex (16 chars)
    user_id: str           # Clerk user_id
    project_id: str        # uuid as string for JSON-safe transport
    template: str
    template_input: dict
    plan_overrides: dict = {}   # currently unused; future per-job overrides


class RenderJobStatus(BaseModel):
    """In-flight status snapshot — what /api/renders/{id} returns."""
    job_id: str
    stage: RenderStage
    progress: float
    final_mp4_url: Optional[str] = None
    error: Optional[str] = None
