"""AI Story Video adapter — prompt-native happy path.

Calls ``generate_video_plan`` with the user's prompt, then renders the
top-scored plan via ``render_video_plan``. Heavy: SDXL + parallax + TTS
+ ffmpeg. This is the only Phase 1 entry that actually exercises the
GPU pipeline (with reddit_story).
"""

from __future__ import annotations

from pathlib import Path

from xvideo.prompt_native import generate_video_plan
from xvideo.prompt_native.plan_renderer_bridge import render_video_plan

from apps.worker.template_inputs import AIStoryInput


def render(input: AIStoryInput, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    plans = generate_video_plan(
        prompt=input.prompt,
        platform="shorts_clean",
        duration=input.duration,
        style=input.style,
        seed=input.seed,
        variations=1,
        aspect_ratio=input.aspect,
        score_and_filter=True,
    )
    artifacts = render_video_plan(
        plan=plans[0],
        output_root=work_dir,
        finalize=True,
        want_voice=True,
        want_captions=True,
        want_hook=True,
        voice_name=input.voice_name,
        caption_style=input.caption_style,
    )
    if artifacts.final_mp4 is None:
        raise RuntimeError(
            "ai_story render produced no final MP4 (finalize stage failed)"
        )
    return artifacts.final_mp4
