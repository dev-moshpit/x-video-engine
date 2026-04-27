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

from apps.worker.template_inputs import RedditStoryInput


def build_prompt(input: RedditStoryInput) -> str:
    """Compose the synthetic engine prompt from a Reddit post.

    Exposed (not underscored) so the api's plan-preview path
    (``apps/api/app/services/plans.py``) can construct the same prompt
    on the cheap surface — keeping the preview consistent with what
    the worker actually renders.
    """
    return (
        f"Tell this Reddit story dramatically as a faceless short. "
        f"Subreddit: r/{input.subreddit}. "
        f"Title: {input.title}. "
        f"Body: {input.body}. "
        f"Tone: storytelling, suspenseful."
    )


def render(input: RedditStoryInput, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    plans = generate_video_plan(
        prompt=build_prompt(input),
        platform="shorts_clean",
        duration=input.duration,
        style="story",
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
        caption_style=input.caption_style or "kinetic_word",
    )
    if artifacts.final_mp4 is None:
        raise RuntimeError(
            "reddit_story render produced no final MP4 (finalize stage failed)"
        )
    return artifacts.final_mp4
