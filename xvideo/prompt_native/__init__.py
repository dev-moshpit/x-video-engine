"""Prompt-native video generation — primary path of the LowPoly Shorts Engine.

    NEW PROMPT = NEW ORIGINAL VIDEO EVERY TIME.

This package is the public surface for prompt-native generation. A single
free-form user prompt becomes a complete `VideoPlan` (concept, hook, scene
plan, voiceover, captions, motion plan, render jobs) — and that plan
becomes a finished 9:16 MP4 through the existing post-production stack.

Module map
----------
- ``schema``                : VideoPlan / Scene / RenderJob dataclasses.
- ``director``              : ``generate_video_plan(prompt, …)`` — the
                              creative director. Combinatorial, seeded, no LLM.
- ``variation_engine``      : variation seed math + per-prompt profile.
- ``script_engine``         : hook / VO / CTA composition (no LLM).
- ``scene_engine``          : 4-8 scene arc → Scene[] (subject/env/mood/cam).
- ``visual_prompt_engine``  : Scene → render-ready SDXL prompt + negative.
- ``motion_engine``         : camera_motion → parallax motion profile.
- ``caption_style_engine``  : 6 caption styles (bold_word, kinetic_word,
                              clean_subtitle, impact_uppercase,
                              minimal_lower_third, karaoke_3word).
- ``safety_filters``        : prompt sanitation + plan content guards.
- ``scoring``               : heuristic plan QA (hook strength, scene variety,
                              caption punch) + regenerate gate.
- ``plan_renderer_bridge``  : VideoPlan → background scene clips → final MP4.

Architecture
------------
The pack-routed flow (``xvideo.prompt_planner`` + ``content_packs/*``) is
**still available** as legacy / fallback / regression coverage, but no
longer the primary surface. The CLI default planner is ``prompt_native``;
the UI's primary button generates a fresh original video.

The implementation deliberately does **not** depend on an LLM at runtime.
A combinatorial concept graph (archetype × setting × moment × tension ×
resolution × camera lens × visual style × palette) seeded by
``prompt_hash + variation_id`` produces a different video every call to
the same prompt. Pin ``--seed`` to reproduce a specific plan exactly.
"""

from __future__ import annotations

# Public schema + core API are re-exported from the implementation modules
# so that callers can write::
#
#     from xvideo.prompt_native import generate_video_plan, VideoPlan
#
# regardless of where the actual code lives.

from xvideo.prompt_native.schema import (
    RenderJob,
    Scene,
    VideoPlan,
    plan_to_render_jobs,
)
from xvideo.prompt_native.director import (
    available_themes,
    detect_theme,
    generate_variations,
    generate_video_plan,
)
from xvideo.prompt_native.variation_engine import (
    build_variation_profile,
    create_variation_id,
    generate_variation_seed,
    mutate_concept,
    mutate_script_angle,
    mutate_visual_world,
)
from xvideo.prompt_native.scoring import (
    PlanScore,
    score_plan,
    plan_meets_thresholds,
    DEFAULT_THRESHOLDS,
)
from xvideo.prompt_native.caption_style_engine import (
    CAPTION_STYLES,
    default_caption_style_for,
    build_caption_file,
)
from xvideo.prompt_native.safety_filters import (
    sanitize_user_prompt,
    sanitize_visual_prompt,
    audit_plan,
)
from xvideo.prompt_native.plan_renderer_bridge import (
    render_video_plan,
    plan_to_render_jobs as bridge_plan_to_render_jobs,  # alias for symmetry
)

ENGINE_VERSION = "prompt_native/1.0"

__all__ = [
    # schema
    "VideoPlan",
    "Scene",
    "RenderJob",
    "plan_to_render_jobs",
    # director
    "generate_video_plan",
    "generate_variations",
    "available_themes",
    "detect_theme",
    # variations
    "generate_variation_seed",
    "create_variation_id",
    "build_variation_profile",
    "mutate_concept",
    "mutate_visual_world",
    "mutate_script_angle",
    # scoring
    "score_plan",
    "plan_meets_thresholds",
    "DEFAULT_THRESHOLDS",
    "PlanScore",
    # caption styles
    "CAPTION_STYLES",
    "default_caption_style_for",
    "build_caption_file",
    # safety
    "sanitize_user_prompt",
    "sanitize_visual_prompt",
    "audit_plan",
    # bridge
    "render_video_plan",
    "ENGINE_VERSION",
]
