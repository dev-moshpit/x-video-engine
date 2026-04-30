"""Motion engine — map scene emotion / beat to camera motion.

The parallax animator in ``worker_runtime/sdxl_parallax`` understands a
small motion vocabulary (zoom range + pan fraction). The director picks a
named camera motion per scene; this module is the *translation layer*
between that director-level vocabulary and the renderer-level motion
profile.

The translation already exists in ``camera_motion_to_motion_profile``;
this module re-exports it and adds:

- ``recommend_motion_for_emotion`` — for callers that want to drive
  motion from emotion rather than from RNG (e.g. an LLM planner that
  knows "this is the reveal beat" and wants a "dramatic final push").
- ``MotionPlan`` typed result for sidecar provenance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from xvideo.prompt_video_director import (
    _MOTION_TO_PROFILE as _DIRECTOR_MOTION_TO_PROFILE,
    camera_motion_to_motion_profile,
)
from xvideo.prompt_native.schema import Scene, VideoPlan


CAMERA_MOTIONS: list[str] = list(_DIRECTOR_MOTION_TO_PROFILE.keys())
MOTION_PROFILES: list[str] = sorted(set(_DIRECTOR_MOTION_TO_PROFILE.values()))


# Emotion → camera motion suggestion. Keep these short, concrete lookups —
# the spec calls out "intense hook → fast push-in", "reflective → slow
# drift", "reveal → zoom out", "final sting → static hold or hard push".
_EMOTION_TO_MOTION: dict[str, str] = {
    "hook":       "slow push-in",
    "intense":    "slow push-in",
    "build":      "drift right",
    "reveal":     "slow pull-back",
    "reflective": "drift left",
    "still":      "static hold",
    "tension":    "rising tilt",
    "final":      "static hold",
    "cta":        "static hold",
    "calm":       "slow push-in",
    "dramatic":   "orbit",
    "energetic":  "orbit",
}


@dataclass
class MotionPlan:
    """Per-scene motion choice + the resolved renderer profile."""
    scene_id: str
    camera_motion: str
    motion_profile: str  # calm | medium | energetic
    duration_seconds: float


def recommend_motion_for_emotion(emotion: str, fallback: str = "drift right") -> str:
    """Return a camera motion that *fits* an emotion label."""
    e = (emotion or "").lower().strip()
    return _EMOTION_TO_MOTION.get(e, fallback)


def motion_plan_for_video(plan: VideoPlan) -> list[MotionPlan]:
    """Return a typed motion plan, one entry per scene.

    Always uses the camera motion the director chose. Callers wanting to
    *override* should mutate the Scene before passing it to the renderer.
    """
    out: list[MotionPlan] = []
    for s in plan.scenes:
        out.append(MotionPlan(
            scene_id=s.scene_id,
            camera_motion=s.camera_motion,
            motion_profile=camera_motion_to_motion_profile(s.camera_motion),
            duration_seconds=s.duration,
        ))
    return out


__all__ = [
    "CAMERA_MOTIONS",
    "MOTION_PROFILES",
    "MotionPlan",
    "camera_motion_to_motion_profile",
    "recommend_motion_for_emotion",
    "motion_plan_for_video",
]
