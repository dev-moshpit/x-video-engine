"""Phase 9 — dashboard retention insights.

  GET /api/me/insights      one payload powering the dashboard "what
                            should I make today" surface

The endpoint composes signal already exposed elsewhere (preferences,
recommendations, render history) into one cheap call so the dashboard
can render in a single fetch.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.auth.deps import CurrentDbUser
from app.db.models import Project, Render
from app.db.session import DbSession
from app.schemas.templates import VALID_TEMPLATE_IDS, template_meta
from app.services.selection_learning import (
    compute_user_preferences,
    recommend_defaults,
)


router = APIRouter(prefix="/api/me/insights", tags=["insights"])


# ─── Suggestion catalog ─────────────────────────────────────────────────

# When the user has no history, we still want to give them a punchy
# starter. Five hand-picked starter prompts per template — keep these
# evergreen + viral-friendly so the dashboard never feels empty.
_STARTER_PROMPTS: dict[str, list[dict]] = {
    "ai_story": [
        {
            "label": "Discipline > motivation",
            "prompt": (
                "Make a cinematic motivational short about why "
                "discipline beats motivation. Intense, dawn footage, "
                "voice of a stoic narrator."
            ),
        },
        {
            "label": "First million",
            "prompt": (
                "Tell the story of someone making their first million "
                "online — fast cuts, late-night grind, dopamine vs "
                "fulfillment. Cinematic, neon-lit."
            ),
        },
        {
            "label": "Why time speeds up",
            "prompt": (
                "Explain why time feels faster as you age. Slow zooms, "
                "vintage film grain, philosophical voiceover."
            ),
        },
    ],
    "reddit_story": [
        {
            "label": "Petty revenge",
            "prompt": (
                "A r/pettyrevenge post about a roommate who kept "
                "stealing food — the OP's slow-burn revenge is dumb "
                "but satisfying."
            ),
        },
        {
            "label": "Wedding chaos",
            "prompt": (
                "A r/AmITheAsshole post where the bride banned phones "
                "from the wedding and the drama escalates fast."
            ),
        },
    ],
    "would_you_rather": [
        {
            "label": "Cursed superpowers",
            "prompt": (
                "Two cursed superpowers: never sleep again vs always "
                "have to sing your thoughts out loud."
            ),
        },
    ],
    "top_five": [
        {
            "label": "Top 5 cities",
            "prompt": (
                "Top 5 cities you must visit before 30 — Tokyo, "
                "Reykjavik, Cape Town, Cusco, Marrakech."
            ),
        },
    ],
    "fake_text": [
        {
            "label": "Wedding dress drama",
            "prompt": (
                "A bride's mom texts her the morning of the wedding "
                "that she 'doesn't approve' — five-message escalation."
            ),
        },
    ],
}


# ─── Schemas ────────────────────────────────────────────────────────────

class TemplatePerformance(BaseModel):
    template: str
    template_name: str
    starred: int
    rejected: int
    star_rate: float
    renders: int


class SuggestionItem(BaseModel):
    template: str
    label: str
    prompt: Optional[str] = None
    reason: str


class InsightsResponse(BaseModel):
    """Dashboard insights payload."""
    model_config = ConfigDict(from_attributes=False)

    is_new_user: bool
    total_renders: int
    renders_last_7_days: int
    completed_renders: int
    starred_renders: int

    best_template: Optional[TemplatePerformance] = None

    # "Try this today" — 3 to 5 items. For new users, it's the starter
    # prompts; for returning users we mix in their best template + a
    # fresh angle on it.
    suggestions: list[SuggestionItem] = Field(default_factory=list)

    # Pass-through of the most recent activity for the dashboard
    # "pick up where you left off" widget.
    last_active_template: Optional[str] = None
    last_active_at: Optional[datetime] = None


# ─── Endpoint ───────────────────────────────────────────────────────────

@router.get("", response_model=InsightsResponse)
def get_insights(
    user: CurrentDbUser, db: DbSession,
) -> InsightsResponse:
    profile = compute_user_preferences(db, user.id)

    # Render-level counts.
    total_renders: int = db.execute(
        select(func.count(Render.id))
        .join(Project, Project.id == Render.project_id)
        .where(Project.user_id == user.id)
    ).scalar_one()

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    renders_7d: int = db.execute(
        select(func.count(Render.id))
        .join(Project, Project.id == Render.project_id)
        .where(Project.user_id == user.id, Render.started_at >= week_ago)
    ).scalar_one()

    completed_renders: int = db.execute(
        select(func.count(Render.id))
        .join(Project, Project.id == Render.project_id)
        .where(Project.user_id == user.id, Render.stage == "complete")
    ).scalar_one()

    starred_renders = profile["starred_count"]

    # Best template — one with the highest star_rate (min 2 decisions).
    best: Optional[TemplatePerformance] = None
    for tpl, m in (profile.get("per_template") or {}).items():
        decided = m["starred"] + m["rejected"]
        if decided < 2:
            continue
        meta = template_meta(tpl)
        candidate = TemplatePerformance(
            template=tpl,
            template_name=meta.name if meta else tpl,
            starred=m["starred"],
            rejected=m["rejected"],
            star_rate=m["star_rate"],
            renders=m["renders"],
        )
        if best is None or candidate.star_rate > best.star_rate:
            best = candidate

    # Last active surface.
    last_render = db.execute(
        select(Render, Project)
        .join(Project, Project.id == Render.project_id)
        .where(Project.user_id == user.id)
        .order_by(Render.started_at.desc())
        .limit(1)
    ).first()
    last_template: Optional[str] = None
    last_at: Optional[datetime] = None
    if last_render:
        _, p = last_render
        last_template = p.template
        last_at = last_render[0].started_at

    # Build suggestions.
    suggestions: list[SuggestionItem] = []
    is_new = total_renders == 0

    if best is not None:
        rec = recommend_defaults(db, user.id, best.template)
        suggestions.append(SuggestionItem(
            template=best.template,
            label=f"Make another {best.template_name}",
            reason=(
                f"Your star-rate on {best.template_name} is "
                f"{int(best.star_rate * 100)}% — it's your best format."
            ),
            prompt=(
                f"caption_style={rec.get('caption_style')}; "
                f"voice={rec.get('voice_name')}"
                if (rec.get("caption_style") or rec.get("voice_name"))
                else None
            ),
        ))

    # Always seed in a fresh starter angle (rotates by user id hash so
    # the dashboard doesn't show the same one twice in a row to the
    # same person within a day).
    seeded_templates = list(_STARTER_PROMPTS.keys())
    seed_idx = (hash(str(user.id)) >> 4) % len(seeded_templates)
    starter_tpl = seeded_templates[seed_idx]
    for entry in _STARTER_PROMPTS[starter_tpl][:2]:
        meta = template_meta(starter_tpl)
        suggestions.append(SuggestionItem(
            template=starter_tpl,
            label=entry["label"],
            prompt=entry["prompt"],
            reason=(
                "Suggested starter — works for most channels."
                if is_new
                else f"Try a different angle in {meta.name if meta else starter_tpl}"
            ),
        ))

    # Cap at 5.
    suggestions = suggestions[:5]

    return InsightsResponse(
        is_new_user=is_new,
        total_renders=total_renders,
        renders_last_7_days=renders_7d,
        completed_renders=completed_renders,
        starred_renders=starred_renders,
        best_template=best,
        suggestions=suggestions,
        last_active_template=last_template,
        last_active_at=last_at,
    )
