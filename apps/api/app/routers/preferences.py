"""Per-user preference profile (PR 13).

GET /api/me/preferences  →  aggregated star/reject feedback for the
authenticated user. Read-only; the underlying signal is the
``renders.starred`` column written by PR 12's feedback endpoints.

The frontend can use this to surface "you usually star X" hints on
the create-project form. Phase 1.5+ will wire the same signal into
the scorer's re-ranking step so future plan variations get nudged
toward the user's pattern.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.auth.deps import CurrentDbUser
from app.db.session import DbSession
from app.services.selection_learning import compute_user_preferences


router = APIRouter(prefix="/api/me", tags=["preferences"])


class PreferenceProfile(BaseModel):
    starred_count: int = Field(0, ge=0)
    rejected_count: int = Field(0, ge=0)
    templates: dict[str, int] = Field(default_factory=dict)
    caption_styles: dict[str, int] = Field(default_factory=dict)
    voices: dict[str, int] = Field(default_factory=dict)
    top_template: Optional[str] = None
    top_caption_style: Optional[str] = None
    top_voice: Optional[str] = None


@router.get("/preferences", response_model=PreferenceProfile)
def get_preferences(
    user: CurrentDbUser, db: DbSession,
) -> PreferenceProfile:
    return PreferenceProfile(**compute_user_preferences(db, user.id))
