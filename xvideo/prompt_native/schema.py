"""Prompt-native plan schema.

The single source of truth for what a generated video *is*. Every
downstream stage (scene render, voiceover, captions, ffmpeg compose,
sidecar metadata) reads a ``VideoPlan`` and never the original prompt.

The dataclasses here re-export the existing ``Scene`` and ``VideoPlan``
from ``xvideo.prompt_video_director`` so legacy imports keep working,
and add the ``RenderJob`` shape called for in the prompt-native spec.
``RenderJob`` is a render-side projection of a ``Scene`` — same fields
the parallax + SDXL backend expects, no creative state — so the bridge
can build them in one place and any future renderer can consume them
without a back-channel into the director's internals.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# The Scene + VideoPlan dataclasses already live in prompt_video_director —
# we re-export them so xvideo.prompt_native.schema is the canonical import
# path, but no code is duplicated.
from xvideo.prompt_video_director import (  # noqa: F401  (re-export)
    Scene,
    VideoPlan,
)


@dataclass
class RenderJob:
    """One rendering unit — projection of a Scene for the backend.

    ``RenderJob`` is what a renderer (SDXL+parallax today, future
    motion-model tomorrow) needs to produce one scene clip. It strips the
    creative-state from a Scene and adds resolution + the resolved seed +
    output path.

    The bridge (``plan_to_render_jobs``) is the only producer.
    """
    scene_id: str
    prompt: str
    negative_prompt: str
    seed: int
    width: int
    height: int
    duration_seconds: float
    camera_motion: str
    output_path: str

    def to_dict(self) -> dict:
        return asdict(self)


# Spec-friendly aspect→size map. Vertical first (Shorts/TikTok/Reels).
_ASPECT_SIZES: dict[str, tuple[int, int]] = {
    "9:16": (576, 1024),
    "16:9": (1024, 576),
    "1:1":  (768, 768),
}


def aspect_to_size(aspect: str) -> tuple[int, int]:
    """Resolve ``"9:16" -> (576, 1024)``. Defaults to square for unknowns."""
    return _ASPECT_SIZES.get(aspect, (768, 768))


def plan_to_render_jobs(
    plan: VideoPlan,
    output_dir: str | Path,
) -> list[RenderJob]:
    """Project a ``VideoPlan`` into one ``RenderJob`` per scene.

    The renderer-facing seed is intentionally derived as ``plan.seed +
    scene_index`` so each scene gets a stable but distinct keyframe
    while staying reproducible from the plan's seed alone — the same
    derivation used by the existing ``prompt_video_runner`` so adding the
    bridge does not change rendered output.
    """
    width, height = aspect_to_size(plan.aspect_ratio)
    out_dir = Path(output_dir)
    jobs: list[RenderJob] = []
    for i, scene in enumerate(plan.scenes):
        clip_id = f"{scene.scene_id}_v{plan.variation_id}"
        jobs.append(RenderJob(
            scene_id=scene.scene_id,
            prompt=scene.visual_prompt,
            negative_prompt=plan.negative_prompt,
            seed=plan.seed + i,
            width=width,
            height=height,
            duration_seconds=scene.duration,
            camera_motion=scene.camera_motion,
            output_path=str(out_dir / f"{clip_id}.mp4"),
        ))
    return jobs


__all__ = [
    "Scene",
    "VideoPlan",
    "RenderJob",
    "aspect_to_size",
    "plan_to_render_jobs",
]
