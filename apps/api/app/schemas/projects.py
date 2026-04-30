"""API request/response models for Project CRUD + plan preview."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ─── Project ────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    template: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=200)
    template_input: dict = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    template_input: Optional[dict] = None


class ProjectResponse(BaseModel):
    """Lightweight project record — used in list views."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    template: str
    name: str
    template_input: dict
    created_at: datetime
    updated_at: datetime


class RenderSummary(BaseModel):
    """Embedded in ProjectDetailResponse — concise per-render fields."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: str
    stage: str
    progress: float
    final_mp4_url: Optional[str] = None
    error: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    starred: Optional[bool] = None


class ProjectDetailResponse(ProjectResponse):
    renders: list[RenderSummary] = Field(default_factory=list)


# ─── Plan preview ───────────────────────────────────────────────────────

class PlanRequest(BaseModel):
    variations: int = Field(1, ge=1, le=5)
    seed: Optional[int] = None
    score_and_filter: bool = True


class GeneratedPlan(BaseModel):
    """One VideoPlan + its score + soft audit warnings.

    ``video_plan`` is the full ``xvideo.prompt_native.VideoPlan.to_dict()``
    structure — frontend renders it as the preview pane (hook / concept /
    scenes / VO / CTA). ``score`` is the heuristic ``PlanScore.to_dict()``.
    ``warnings`` is non-blocking copy from ``audit_plan``.
    """
    video_plan: dict
    score: dict
    warnings: list[str] = Field(default_factory=list)


class PlanResponse(BaseModel):
    plans: list[GeneratedPlan]
    # Phase 4: index into ``plans`` of the highest-scoring variation,
    # or None when the list is empty. Frontend uses it to highlight
    # the recommended pick when the operator generated >1 variation.
    recommended_index: Optional[int] = None


# ─── Phase 8: smart generate ────────────────────────────────────────────

class SmartGenerateRequest(BaseModel):
    """Smart generation: pick the best of N plans then enqueue render(s)."""
    candidates: int = Field(3, ge=1, le=5)
    render_top: int = Field(1, ge=0, le=3)
    seed: Optional[int] = None


class SmartGenerateResponse(BaseModel):
    """Best-pick plan(s) + reasoning + the renders that were enqueued.

    ``rendered`` is empty when ``render_top == 0`` (preview-only mode).
    The frontend uses ``reasoning`` to show *why* the plan won so the
    user trusts the auto-pick.
    """
    plans: list[GeneratedPlan]
    best_index: int
    best_plan: GeneratedPlan
    reasoning: list[str] = Field(default_factory=list)
    boosted_score: float = 0.0
    rendered: list[RenderSummary] = Field(default_factory=list)
