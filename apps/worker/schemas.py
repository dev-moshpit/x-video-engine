"""Render-job wire schemas — worker copy.

Copied (not imported) from ``apps/api/app/schemas/render.py`` to keep
the worker independently deployable. Drift test in
``tests/worker/test_queue_consumer.py`` ensures parity.
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
    job_id: str
    user_id: str
    project_id: str
    template: str
    template_input: dict
    plan_overrides: dict = {}
    # Phase 3: tier-driven post-processing.
    tier: str = "free"
    # Phase 6: per-user brand identity tokens.
    brand_kit: dict = {}


class RenderJobStatus(BaseModel):
    """In-flight status snapshot — what /api/renders/{id} returns."""
    job_id: str
    stage: RenderStage
    progress: float
    final_mp4_url: Optional[str] = None
    error: Optional[str] = None
