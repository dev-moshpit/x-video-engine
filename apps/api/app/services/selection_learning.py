"""Selection-learning v1 (PR 13).

Reads the operator's star/reject feedback (PR 12) and produces a
per-user preference profile — counts of which templates, caption
styles, and voices the user has explicitly starred.

This is the *informational* v1: the profile is exposed via
GET /api/me/preferences but does NOT (yet) bias plan generation.
Phase 1.5+ will use the same profile to bump similar variations in
the scorer's re-ranking step.

The matching engine-side module (``xvideo/prompt_native/selection_learning.py``
in the post-v1 internal-track plan) reads the legacy local gallery
instead of this Postgres table; the two sources can converge later if
we want to merge SaaS and CLI feedback into one signal.
"""

from __future__ import annotations

import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Project, Render


def compute_user_preferences(
    db: Session, user_id: uuid.UUID,
) -> dict:
    """Aggregate the user's starred + rejected renders.

    Returns a dict with:
      - ``starred_count``    int — total starred renders
      - ``rejected_count``   int — total rejected renders
      - ``templates``        {template_id: count} of starred renders
      - ``caption_styles``   {style: count} from starred renders'
                              ``template_input.caption_style``
      - ``voices``           {voice_name: count} similarly
      - ``top_template``     str | None — most-starred template
      - ``top_caption_style`` str | None
      - ``top_voice``        str | None

    Empty maps + None tops if the user has no decisions yet.
    """
    rows = db.execute(
        select(Render, Project)
        .join(Project, Project.id == Render.project_id)
        .where(Project.user_id == user_id)
        .where(Render.starred.isnot(None))
    ).all()

    starred_count = 0
    rejected_count = 0
    templates: Counter[str] = Counter()
    caption_styles: Counter[str] = Counter()
    voices: Counter[str] = Counter()

    for render, project in rows:
        if render.starred is True:
            starred_count += 1
            templates[project.template] += 1
            ti = project.template_input or {}
            cs = ti.get("caption_style")
            if isinstance(cs, str):
                caption_styles[cs] += 1
            vn = ti.get("voice_name")
            if isinstance(vn, str):
                voices[vn] += 1
        elif render.starred is False:
            rejected_count += 1

    def _top(c: Counter[str]) -> str | None:
        if not c:
            return None
        # ``most_common(1)`` returns [(key, count)]
        return c.most_common(1)[0][0]

    return {
        "starred_count": starred_count,
        "rejected_count": rejected_count,
        "templates": dict(templates),
        "caption_styles": dict(caption_styles),
        "voices": dict(voices),
        "top_template": _top(templates),
        "top_caption_style": _top(caption_styles),
        "top_voice": _top(voices),
    }
