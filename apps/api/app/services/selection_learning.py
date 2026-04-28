"""Selection-learning v2 — preference profile + per-template metrics
+ default recommendations.

Phase 1 PR 13 shipped v1 (informational only): aggregated star/reject
counts per template/caption_style/voice. Phase 4 extends that with:

  - per-template success/star/reject rates (so the dashboard can show
    which templates the operator gets the most value from)
  - recommend_defaults(template) — best caption_style + voice + style
    cue for the user-template pair, falling back to global signal
    when the user has no decisions in that template

The module stays read-only: it never writes to the DB. The signal it
reads is the ``renders.starred`` column written by the feedback
endpoints, plus ``renders.stage`` for success/failure rates.

This is the SaaS-side learner. The engine-internal track in
``xvideo/prompt_native/selection_learning.py`` reads the legacy local
gallery; the two sources are independent on purpose so a missing
SaaS user doesn't break the CLI flow.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Project, Render


# ─── Aggregated profile ─────────────────────────────────────────────────

def compute_user_preferences(
    db: Session, user_id: uuid.UUID,
) -> dict:
    """Aggregate the user's starred + rejected renders.

    Returns a dict shape consumed by GET /api/me/preferences. The
    Phase 4 additions (``per_template`` and the rate fields) are
    backward-compatible — the old keys still exist with the same
    semantics, so the Phase 1 frontend keeps working.
    """
    rows = db.execute(
        select(Render, Project)
        .join(Project, Project.id == Render.project_id)
        .where(Project.user_id == user_id)
    ).all()

    starred_count = 0
    rejected_count = 0
    templates: Counter[str] = Counter()
    caption_styles: Counter[str] = Counter()
    voices: Counter[str] = Counter()

    # Phase 4 — per-template success/star/reject metrics.
    template_renders: Counter[str] = Counter()
    template_completed: Counter[str] = Counter()
    template_failed: Counter[str] = Counter()
    template_starred: Counter[str] = Counter()
    template_rejected: Counter[str] = Counter()

    for render, project in rows:
        tpl = project.template
        template_renders[tpl] += 1
        if render.stage == "complete":
            template_completed[tpl] += 1
        elif render.stage == "failed":
            template_failed[tpl] += 1

        if render.starred is True:
            starred_count += 1
            templates[tpl] += 1
            template_starred[tpl] += 1
            ti = project.template_input or {}
            cs = ti.get("caption_style")
            if isinstance(cs, str):
                caption_styles[cs] += 1
            vn = ti.get("voice_name")
            if isinstance(vn, str):
                voices[vn] += 1
        elif render.starred is False:
            rejected_count += 1
            template_rejected[tpl] += 1

    def _top(c: Counter[str]) -> Optional[str]:
        if not c:
            return None
        return c.most_common(1)[0][0]

    def _safe_rate(num: int, denom: int) -> float:
        return round(num / denom, 3) if denom > 0 else 0.0

    per_template: dict[str, dict] = {}
    for tpl in template_renders:
        renders_n = template_renders[tpl]
        decided = template_starred[tpl] + template_rejected[tpl]
        per_template[tpl] = {
            "renders": renders_n,
            "completed": template_completed[tpl],
            "failed": template_failed[tpl],
            "starred": template_starred[tpl],
            "rejected": template_rejected[tpl],
            "success_rate": _safe_rate(template_completed[tpl], renders_n),
            "star_rate": _safe_rate(template_starred[tpl], decided),
        }

    return {
        "starred_count": starred_count,
        "rejected_count": rejected_count,
        "templates": dict(templates),
        "caption_styles": dict(caption_styles),
        "voices": dict(voices),
        "top_template": _top(templates),
        "top_caption_style": _top(caption_styles),
        "top_voice": _top(voices),
        # Phase 4 additions.
        "per_template": per_template,
    }


# ─── Recommendations ────────────────────────────────────────────────────

def recommend_defaults(
    db: Session, user_id: uuid.UUID, template: str,
) -> dict:
    """Recommend caption_style + voice + style for a (user, template).

    Strategy:
      1. Look at the user's STARRED renders for *this template* — if
         they have a clear winner there, use it.
      2. Else fall back to their cross-template starred winner.
      3. Else return None for that field — caller uses the template's
         own default.

    Returns a dict ``{caption_style, voice_name, style, reason}``
    where ``reason`` is a short human-readable string the frontend
    can show ("from your starred reddit_story renders") so the
    operator understands where the suggestion comes from.
    """
    # Pull all starred renders for this user.
    rows = db.execute(
        select(Render, Project)
        .join(Project, Project.id == Render.project_id)
        .where(Project.user_id == user_id)
        .where(Render.starred.is_(True))
    ).all()

    by_field_template: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    by_field_global: dict[str, Counter[str]] = defaultdict(Counter)

    for render, project in rows:
        ti = project.template_input or {}
        for field in ("caption_style", "voice_name", "style"):
            v = ti.get(field)
            if isinstance(v, str) and v.strip():
                by_field_template[field][project.template][v] += 1
                by_field_global[field][v] += 1

    def _pick(field: str) -> tuple[Optional[str], Optional[str]]:
        """Returns (value, reason). Both None when no signal."""
        per_t = by_field_template[field].get(template)
        if per_t:
            top = per_t.most_common(1)[0]
            if top[1] >= 1:
                return top[0], (
                    f"from your {top[1]} starred {template} render(s)"
                )
        cross = by_field_global[field]
        if cross:
            top = cross.most_common(1)[0]
            if top[1] >= 2:
                return top[0], (
                    f"from your {top[1]} starred render(s) across all templates"
                )
        return None, None

    cs, cs_reason = _pick("caption_style")
    vo, vo_reason = _pick("voice_name")
    st, st_reason = _pick("style")

    return {
        "template": template,
        "caption_style": cs,
        "voice_name": vo,
        "style": st,
        "reasons": {
            **({"caption_style": cs_reason} if cs_reason else {}),
            **({"voice_name": vo_reason} if vo_reason else {}),
            **({"style": st_reason} if st_reason else {}),
        },
    }
