"""Reddit Story Video adapter.

Synthesizes a storytelling prompt from (subreddit, title, body) and
runs it through the prompt-native pipeline at story tone. Caption
style defaults to ``kinetic_word`` for higher retention on
Reddit-style content.
"""

from __future__ import annotations

from pathlib import Path

from xvideo.prompt_native import generate_video_plan
from xvideo.prompt_native.plan_renderer_bridge import render_video_plan

from apps.worker.render_adapters._style_presets import get_preset
from apps.worker.template_inputs import RedditStoryInput


def build_prompt(input: RedditStoryInput) -> str:
    """Compose the synthetic engine prompt from a Reddit post.

    Exposed (not underscored) so the api's plan-preview path
    (``apps/api/app/services/plans.py``) can construct the same prompt
    on the cheap surface — keeping the preview consistent with what
    the worker actually renders.
    """
    byline = f"Posted by u/{input.username}. " if input.username else ""
    metrics = (
        f"Reddit metrics: {input.upvotes} upvotes and "
        f"{input.comments} comments. "
    )
    return (
        f"Tell this Reddit story dramatically as a faceless short. "
        f"Subreddit: r/{input.subreddit}. "
        f"{byline}"
        f"Title: {input.title}. "
        f"{metrics}"
        f"Body: {input.body}. "
        f"Tone: storytelling, suspenseful. Start with a Reddit-style card, "
        f"then pace the story with cliffhanger beats and kinetic captions."
    )


def render(input: RedditStoryInput, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    base_prompt = build_prompt(input)
    style_cue = "story"
    caption_style = input.caption_style or "kinetic_word"
    if input.style_preset:
        preset = get_preset(input.style_preset)
        base_prompt = (
            f"{base_prompt}\n\nStyle: {preset.positive_prefix}"
        )
        if preset.negative_prompt:
            base_prompt = f"{base_prompt}\nAvoid: {preset.negative_prompt}"
        style_cue = preset.id
        if not input.caption_style:
            caption_style = preset.default_caption_style
    plans = generate_video_plan(
        prompt=base_prompt,
        platform="shorts_clean",
        duration=input.duration,
        style=style_cue,
        seed=input.seed,
        variations=1,
        aspect_ratio="9:16",
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
    )
    if artifacts.final_mp4 is None:
        raise RuntimeError(
            "reddit_story render produced no final MP4 (finalize stage failed)"
        )
    return artifacts.final_mp4
