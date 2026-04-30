"""Scene engine — split a concept arc into 4-8 scene beats.

The director already does this internally (``_build_scenes`` in
``prompt_video_director``). This module re-exposes the scene-level helpers
so callers can:

- read the resolved scene plan from a VideoPlan (``scenes_from_plan``)
- compute the recommended scene count for a duration/pacing pair
  (``recommended_scene_count``) without touching the director — handy in
  the UI when deciding "this is going to be 5 scenes" before generation.

The actual subject/environment/camera_motion picks live in the director
because they depend on the theme RNG. Re-implementing them here would
double the surface area for inevitable drift.
"""

from __future__ import annotations

from xvideo.prompt_video_director import (
    _scene_count_for as _director_scene_count_for,
    _scene_durations as _director_scene_durations,
)
from xvideo.prompt_native.schema import Scene, VideoPlan


def recommended_scene_count(duration_seconds: float, pacing: str = "medium") -> int:
    """Return the scene count the director would pick for a (duration, pacing).

    Per the spec: 4-8 scenes for short-form video, 5 typical for 15-20s.
    Faster pacing → more scenes for the same duration.
    """
    return _director_scene_count_for(duration_seconds, pacing)


def recommended_scene_durations(total_seconds: float, n_scenes: int) -> list[float]:
    """Distribute a total duration across n scenes with mild variation.

    First and last scenes get slightly more time so the hook holds and the
    CTA lands. Mirrors the director's logic exactly.
    """
    return _director_scene_durations(total_seconds, n_scenes)


def scenes_from_plan(plan: VideoPlan) -> list[Scene]:
    """Trivial accessor — kept for API symmetry with ``script_from_plan``."""
    return list(plan.scenes)


__all__ = [
    "Scene",
    "recommended_scene_count",
    "recommended_scene_durations",
    "scenes_from_plan",
]
