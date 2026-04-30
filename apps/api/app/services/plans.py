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

Phase 11 — adds an in-process LRU plan cache keyed on
(template, template_input_hash, variations, seed). The engine call is
already deterministic, so the cache is a pure speedup and never returns
stale results across template_input edits — Project.updated_at flips
the input hash automatically.
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from threading import Lock
from typing import Optional

from xvideo.prompt_native import (
    audit_plan,
    generate_video_plan,
    score_plan,
)

from app.db.models import Project
from app.schemas.templates import template_supports_plan_preview


# ─── Plan cache ─────────────────────────────────────────────────────────

_CACHE_MAX = 128
_cache: OrderedDict[str, list[dict]] = OrderedDict()
_cache_lock = Lock()


def _cache_key(
    template: str,
    template_input: dict,
    variations: int,
    seed: Optional[int],
    score_and_filter: bool,
) -> str:
    payload = {
        "t": template,
        "i": template_input,
        "v": variations,
        "s": seed,
        "f": score_and_filter,
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> Optional[list[dict]]:
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    return None


def _cache_put(key: str, value: list[dict]) -> None:
    with _cache_lock:
        _cache[key] = value
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)


def clear_plan_cache() -> None:
    """Drop everything from the cache. Used in tests."""
    with _cache_lock:
        _cache.clear()


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

    Cached on (template, template_input, variations, seed, score) so
    a re-preview of the same form is essentially free. Editing the
    project's template_input naturally busts the cache through the
    hash key. Random seeds (``seed=None``) skip the cache to preserve
    fresh-each-time semantics.
    """
    use_cache = seed is not None
    cache_key: Optional[str] = None
    if use_cache:
        cache_key = _cache_key(
            project.template,
            project.template_input or {},
            variations,
            seed,
            score_and_filter,
        )
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    prompt, kwargs = _build_engine_call(project)
    if seed is not None:
        kwargs["seed"] = seed

    plans = generate_video_plan(
        prompt=prompt,
        variations=variations,
        score_and_filter=score_and_filter,
        **kwargs,
    )

    out = [
        {
            "video_plan": p.to_dict(),
            "score": score_plan(p).to_dict(),
            "warnings": audit_plan(p),
        }
        for p in plans
    ]
    if use_cache and cache_key:
        _cache_put(cache_key, out)
    return out
