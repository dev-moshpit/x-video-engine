"""Per-user preference profile + Phase 4 recommendations.

  GET  /api/me/preferences            aggregated feedback + per-template
                                      success/star rates
  GET  /api/me/recommendations/{tpl}  best caption_style + voice + style
                                      for the (user, template) pair

Read-only; underlying signal is ``renders.starred`` + ``renders.stage``.
Used by the frontend to pre-fill the create-project form with the
operator's high-success defaults and to highlight "winning" template
variations.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.auth.deps import CurrentDbUser
from app.db.session import DbSession
from app.services.selection_learning import (
    compute_user_preferences,
    recommend_defaults,
)


router = APIRouter(prefix="/api/me", tags=["preferences"])


class TemplateMetrics(BaseModel):
    renders: int = 0
    completed: int = 0
    failed: int = 0
    starred: int = 0
    rejected: int = 0
    success_rate: float = 0.0
    star_rate: float = 0.0


class PreferenceProfile(BaseModel):
    starred_count: int = Field(0, ge=0)
    rejected_count: int = Field(0, ge=0)
    templates: dict[str, int] = Field(default_factory=dict)
    caption_styles: dict[str, int] = Field(default_factory=dict)
    voices: dict[str, int] = Field(default_factory=dict)
    top_template: Optional[str] = None
    top_caption_style: Optional[str] = None
    top_voice: Optional[str] = None
    # Phase 4 — per-template breakdown.
    per_template: dict[str, TemplateMetrics] = Field(default_factory=dict)


class Recommendations(BaseModel):
    template: str
    caption_style: Optional[str] = None
    voice_name: Optional[str] = None
    style: Optional[str] = None
    reasons: dict[str, str] = Field(default_factory=dict)


@router.get("/preferences", response_model=PreferenceProfile)
def get_preferences(
    user: CurrentDbUser, db: DbSession,
) -> PreferenceProfile:
    return PreferenceProfile(**compute_user_preferences(db, user.id))


@router.get(
    "/recommendations/{template}",
    response_model=Recommendations,
)
def get_recommendations(
    template: str, user: CurrentDbUser, db: DbSession,
) -> Recommendations:
    return Recommendations(**recommend_defaults(db, user.id, template))
