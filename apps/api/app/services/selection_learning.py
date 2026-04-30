"""Selection-learning v2 — preference profile + per-template metrics
+ default recommendations + plan-quality estimator.

Phase 1 PR 13 shipped v1 (informational only): aggregated star/reject
counts per template/caption_style/voice. Phase 4 extended that with
per-template success/star/reject rates.

**Phase 8** adds:

  - ``hook_starts`` Counter: which hook *opening words* (first 3 words,
    lowercased) correlate with starred renders → used by the smart
    generator to bias toward proven openings.
  - ``duration_buckets``: 8-15s / 16-30s / 31-60s / 61-90s buckets so
    we know which length the operator's audience rewards.
  - ``compute_plan_score_boost(plan, profile)`` — pure helper used by
    /generate-smart to nudge the engine's heuristic score up/down based
    on user history. Bounded ±5 points so a baseline-quality plan with
    matching tropes can edge out a marginally higher-scoring outsider.

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

def _duration_bucket(seconds: float | int | None) -> str:
    if seconds is None:
        return "unknown"
    s = float(seconds)
    if s <= 15:
        return "8-15s"
    if s <= 30:
        return "16-30s"
    if s <= 60:
        return "31-60s"
    return "61-90s"


def _hook_start(text: str | None) -> str | None:
    """First 3 words of a hook string, lowercased + stripped."""
    if not text or not isinstance(text, str):
        return None
    words = [w.strip(".,!?:;\"'").lower() for w in text.split() if w.strip()]
    if not words:
        return None
    return " ".join(words[:3])


def compute_user_preferences(
    db: Session, user_id: uuid.UUID,
) -> dict:
    """Aggregate the user's starred + rejected renders.

    Returns a dict shape consumed by GET /api/me/preferences. The
    Phase 4 + Phase 8 additions are backward-compatible — older keys
    keep their semantics so the v1 frontend still works.
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

    template_renders: Counter[str] = Counter()
    template_completed: Counter[str] = Counter()
    template_failed: Counter[str] = Counter()
    template_starred: Counter[str] = Counter()
    template_rejected: Counter[str] = Counter()

    # Phase 8 — hook + duration tracking. We grab the duration directly
    # from ``template_input`` (every template that has one stores it
    # there) and use the project name as a proxy for the engine-emitted
    # hook on the SaaS side (the actual hook lives in the worker's
    # plan_json which we don't read from here for cost reasons).
    hook_starts: Counter[str] = Counter()
    durations: Counter[str] = Counter()

    for render, project in rows:
        tpl = project.template
        template_renders[tpl] += 1
        if render.stage == "complete":
            template_completed[tpl] += 1
        elif render.stage == "failed":
            template_failed[tpl] += 1

        ti = project.template_input or {}
        if render.starred is True:
            starred_count += 1
            templates[tpl] += 1
            template_starred[tpl] += 1
            cs = ti.get("caption_style")
            if isinstance(cs, str):
                caption_styles[cs] += 1
            vn = ti.get("voice_name")
            if isinstance(vn, str):
                voices[vn] += 1

            # Hook openers — derive from prompt for ai_story, title for
            # reddit_story / top_five, project name otherwise.
            hook_source = (
                ti.get("prompt")
                or ti.get("title")
                or ti.get("question")
                or project.name
            )
            hs = _hook_start(hook_source)
            if hs:
                hook_starts[hs] += 1

            dur = ti.get("duration") or ti.get("per_item_seconds")
            durations[_duration_bucket(dur)] += 1
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
        "per_template": per_template,
        # Phase 8 additions.
        "hook_starts": dict(hook_starts),
        "duration_buckets": dict(durations),
        "top_hook_start": _top(hook_starts),
        "top_duration_bucket": _top(durations),
    }


# ─── Recommendations ────────────────────────────────────────────────────

def recommend_defaults(
    db: Session, user_id: uuid.UUID, template: str,
) -> dict:
    """Recommend caption_style + voice + style for a (user, template)."""
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


# ─── Phase 8: plan score boost from history ─────────────────────────────

# Bounded so an outsider plan with a much better baseline score can
# still win. The engine's heuristic score is on a 0-100 scale — we
# nudge by at most ±5 points.
_BOOST_HOOK = 3.0
_BOOST_DURATION = 1.5
_BOOST_CAPTION = 0.5

def compute_plan_score_boost(
    plan: dict, profile: dict, *, template: str,
) -> tuple[float, list[str]]:
    """Return (delta, reasons) to add onto the engine's heuristic score.

    ``plan`` is one ``GeneratedPlan["video_plan"]`` (engine VideoPlan
    as dict). ``profile`` is :func:`compute_user_preferences` output.
    Reasons are short human-readable strings — we surface them in the
    /generate-smart response so the operator can see *why* a plan was
    chosen.

    The boost is purely additive and capped at +5/-2; we don't penalize
    novelty heavily because the user might want to break out of their
    existing patterns.
    """
    delta = 0.0
    reasons: list[str] = []

    # Hook opener match — biggest signal we have on the SaaS side.
    hook = plan.get("hook") if isinstance(plan, dict) else None
    hs = _hook_start(hook)
    starts: dict[str, int] = profile.get("hook_starts") or {}
    if hs and starts.get(hs, 0) >= 1:
        delta += _BOOST_HOOK
        reasons.append(
            f"hook opens like {starts[hs]} of your starred render(s)"
        )

    # Duration bucket match.
    total_dur = 0.0
    for s in plan.get("scenes", []) or []:
        if isinstance(s, dict) and isinstance(s.get("duration"), (int, float)):
            total_dur += float(s["duration"])
    bucket = _duration_bucket(total_dur or None)
    durs: dict[str, int] = profile.get("duration_buckets") or {}
    if bucket != "unknown" and durs.get(bucket, 0) >= 2:
        delta += _BOOST_DURATION
        reasons.append(
            f"length ({bucket}) matches your top-rated bucket"
        )

    # Caption style match — engine's plan stores it on the plan itself.
    plan_caption = plan.get("caption_style")
    user_top_caption = profile.get("top_caption_style")
    if (
        isinstance(plan_caption, str)
        and isinstance(user_top_caption, str)
        and plan_caption == user_top_caption
    ):
        delta += _BOOST_CAPTION
        reasons.append("caption_style matches your top pick")

    # Bound the boost so noise never dominates baseline quality.
    delta = max(-2.0, min(5.0, delta))
    return delta, reasons
