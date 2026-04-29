"""AI Story Video adapter — prompt-native happy path.

Calls ``generate_video_plan`` with the user's prompt, then renders the
top-scored plan via ``render_video_plan``. Heavy: SDXL + parallax + TTS
+ ffmpeg. This is the only Phase 1 entry that actually exercises the
GPU pipeline (with reddit_story).

Style presets and pacing are wired in here at the *adapter* layer so
xvideo/ stays untouched: when ``style_preset`` is set we look it up in
``_style_presets`` and prepend its ``positive_prefix`` to the user's
prompt; the preset's caption-style and camera-motion defaults fill any
slots the operator left blank.
"""

from __future__ import annotations

from pathlib import Path

from xvideo.prompt_native import generate_video_plan
from xvideo.prompt_native.plan_renderer_bridge import render_video_plan

from apps.worker.render_adapters._style_presets import get_preset
from apps.worker.template_inputs import AIStoryInput


def _compose_prompt(input: AIStoryInput) -> tuple[str, str | None, str | None]:
    """Apply the operator's style preset to the prompt + caption defaults.

    Returns ``(prompt, style_cue, caption_style)``:
      - ``prompt`` is the user's prompt with the preset's
        ``positive_prefix`` appended (engine joins additional context
        rather than discarding the user's wording).
      - ``style_cue`` is the engine's free-form ``style`` slot — falls
        back to the operator's ``style`` field, otherwise the preset
        name when one was selected.
      - ``caption_style`` honours the operator first, then the preset's
        default, then ``None`` so the engine picks per-format.
    """
    if not input.style_preset:
        return input.prompt, input.style, input.caption_style
    preset = get_preset(input.style_preset)
    prompt = f"{input.prompt.strip()}\n\nStyle: {preset.positive_prefix}"
    if preset.negative_prompt:
        prompt = f"{prompt}\nAvoid: {preset.negative_prompt}"
    style_cue = input.style or preset.id
    caption_style = input.caption_style or preset.default_caption_style
    return prompt, style_cue, caption_style


def render(input: AIStoryInput, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    prompt, style_cue, caption_style = _compose_prompt(input)
    plans = generate_video_plan(
        prompt=prompt,
        platform="shorts_clean",
        duration=input.duration,
        style=style_cue,
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
        caption_style=caption_style,
        music_bed=input.music_bed,
    )
    if artifacts.final_mp4 is None:
        raise RuntimeError(
            "ai_story render produced no final MP4 (finalize stage failed)"
        )
    return artifacts.final_mp4
