"""Visual prompt engine — compose a render-ready SDXL prompt for one scene.

Per the prompt-native spec the format is::

    [subject], [environment], [action], [lighting],
    [camera/framing], [visual style], [mood],
    [quality tags], vertical 9:16 composition

Important: visual prompts must NEVER instruct the image model to render
captions or text. Captions are added later by ffmpeg as a subtitles track
(see ``caption_style_engine``). Mixing burned text into the keyframe
breaks both reproducibility and platform safety reviews.

This module wraps the existing director's ``_build_visual_prompt`` and
``_NEGATIVE_BASE`` so the same prompt body the runner sees is the one
exposed publicly. Adds a "render-ready" formatter ``compile_visual_prompt``
that exposes the spec's slot order verbatim for callers (LLM mode, custom
backends) that want to assemble a prompt from parts they already own.
"""

from __future__ import annotations

from xvideo.prompt_video_director import (
    _NEGATIVE_BASE as _DIRECTOR_NEGATIVE,
    _build_visual_prompt as _director_build_visual,
)
from xvideo.prompt_native.schema import Scene


GLOBAL_NEGATIVE_PROMPT: str = (
    "text, watermark, logo, bad anatomy, extra fingers, blurry, "
    "low quality, distorted face, unreadable letters, UI elements, "
    "subtitles inside image, random typography, " + _DIRECTOR_NEGATIVE
)


def compile_visual_prompt(
    *,
    subject: str,
    environment: str,
    action: str = "",
    lighting: str = "",
    camera: str = "",
    visual_style: str = "low poly stylized 3D",
    mood: str = "",
    quality_tags: str = "stylized minimalist, clean geometric edges, sharp polygon faces",
    aspect_hint: str = "vertical 9:16 composition",
) -> str:
    """Compose a single render-ready visual prompt in the spec's slot order.

    Empty slots are dropped (so we don't emit dangling commas). This is
    the function future LLM-mode planners should call instead of
    duplicating string-join logic.
    """
    parts = [
        subject,
        environment,
        action,
        lighting,
        camera,
        visual_style,
        mood,
        quality_tags,
        aspect_hint,
    ]
    return ", ".join(p.strip() for p in parts if p and p.strip())


def visual_prompt_for_scene(
    scene: Scene,
    visual_style: str,
    color_palette: str,
) -> str:
    """Re-build a Scene's visual prompt deterministically.

    Useful in tests and in the UI when the user edits an axis (e.g.
    palette) and wants to preview the new prompt without re-running the
    full director. Note: the director already stores the compiled prompt
    in ``scene.visual_prompt``; prefer reading that field unless you are
    explicitly recomputing.
    """
    return _director_build_visual(
        subject=scene.subject,
        environment=scene.environment,
        visual_style=visual_style,
        color_palette=color_palette,
        mood=scene.mood,
        camera_motion=scene.camera_motion,
    )


__all__ = [
    "GLOBAL_NEGATIVE_PROMPT",
    "compile_visual_prompt",
    "visual_prompt_for_scene",
]
