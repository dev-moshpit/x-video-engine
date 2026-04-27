"""Plan-only generation — calls into ``xvideo.prompt_native`` synchronously.

Cheap, deterministic, sub-second, no GPU. The api hits this for the
preview pane on /create/[template] before the user pays for a real
render. Maps a ``Project`` (template + ``template_input`` dict) onto
the engine's prompt + kwargs.

Only ``ai_story`` and ``reddit_story`` currently produce a VideoPlan.
The other Phase 1 templates (``voiceover``, ``auto_captions``) skip the
plan stage and go straight from form to render — the worker's adapter
handles them with the post stack directly. ``template_supports_plan``
is the canonical check.
"""

from __future__ import annotations

from typing import Optional

from xvideo.prompt_native import (
    audit_plan,
    generate_video_plan,
    score_plan,
)

from app.db.models import Project
from app.schemas.templates import template_supports_plan_preview


def template_supports_plan(template: str) -> bool:
    return template_supports_plan_preview(template)


def _build_engine_call(project: Project) -> tuple[str, dict]:
    """Translate ``project.template`` + ``template_input`` to engine args.

    Returns ``(prompt, kwargs)`` for ``generate_video_plan``.
    """
    template = project.template
    inp = project.template_input or {}

    if template == "ai_story":
        prompt = inp.get("prompt", "").strip()
        return prompt, {
            "duration": inp.get("duration", 20.0),
            "aspect_ratio": inp.get("aspect", "9:16"),
            "style": inp.get("style"),
            "seed": inp.get("seed"),
        }

    if template == "reddit_story":
        synthetic_prompt = (
            f"Tell this Reddit story dramatically as a faceless short. "
            f"Subreddit: r/{inp.get('subreddit', 'AskReddit')}. "
            f"Title: {inp.get('title', '')}. "
            f"Body: {inp.get('body', '')}. "
            f"Tone: storytelling, suspenseful."
        )
        return synthetic_prompt, {
            "duration": inp.get("duration", 30.0),
            "aspect_ratio": "9:16",
            "style": "story",
            "seed": inp.get("seed"),
        }

    raise ValueError(
        f"template '{template}' has no plan preview — call /render directly"
    )


def plans_for_project(
    project: Project,
    *,
    variations: int = 1,
    seed: Optional[int] = None,
    score_and_filter: bool = True,
) -> list[dict]:
    """Generate VideoPlans + scores + warnings for a project.

    Returns a list of dicts shaped for ``GeneratedPlan``:
    ``{"video_plan": dict, "score": dict, "warnings": list[str]}``.

    Raises ValueError if the template has no plan preview.
    """
    prompt, kwargs = _build_engine_call(project)
    if seed is not None:
        kwargs["seed"] = seed

    plans = generate_video_plan(
        prompt=prompt,
        variations=variations,
        score_and_filter=score_and_filter,
        **kwargs,
    )

    return [
        {
            "video_plan": p.to_dict(),
            "score": score_plan(p).to_dict(),
            "warnings": audit_plan(p),
        }
        for p in plans
    ]
