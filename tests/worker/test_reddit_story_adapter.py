"""Reddit Story adapter test (PR 5).

Same mocking pattern as AI Story. Extra coverage: the synthetic
prompt is constructed from the Reddit fields and the default caption
style is ``kinetic_word``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from apps.worker.render_adapters import reddit_story
from apps.worker.template_inputs import RedditStoryInput


def _fake_artifacts(final_mp4: Path) -> MagicMock:
    a = MagicMock()
    a.final_mp4 = final_mp4
    return a


@patch("apps.worker.render_adapters.reddit_story.render_video_plan")
@patch("apps.worker.render_adapters.reddit_story.generate_video_plan")
def test_reddit_story_synthesizes_prompt_and_renders(
    mock_gen, mock_render_vp, tmp_path: Path,
):
    fake_plan = MagicMock()
    mock_gen.return_value = [fake_plan]
    fake_mp4 = tmp_path / "out.mp4"
    fake_mp4.write_bytes(b"x")
    mock_render_vp.return_value = _fake_artifacts(fake_mp4)

    inp = RedditStoryInput(
        subreddit="AskReddit",
        title="What's your weirdest neighbor story?",
        body="I lived next to a guy who only wore green for a whole year.",
        duration=25.0,
    )
    result = reddit_story.render(inp, tmp_path)
    assert result == fake_mp4

    _args, gen_kwargs = mock_gen.call_args
    prompt = gen_kwargs["prompt"]
    assert "r/AskReddit" in prompt
    assert "What's your weirdest neighbor story?" in prompt
    assert "wore green for a whole year" in prompt
    assert gen_kwargs["style"] == "story"
    assert gen_kwargs["aspect_ratio"] == "9:16"
    assert gen_kwargs["duration"] == 25.0


@patch("apps.worker.render_adapters.reddit_story.render_video_plan")
@patch("apps.worker.render_adapters.reddit_story.generate_video_plan")
def test_reddit_story_defaults_to_kinetic_word_caption_style(
    mock_gen, mock_render_vp, tmp_path: Path,
):
    mock_gen.return_value = [MagicMock()]
    fake_mp4 = tmp_path / "out.mp4"
    fake_mp4.write_bytes(b"x")
    mock_render_vp.return_value = _fake_artifacts(fake_mp4)

    inp = RedditStoryInput(
        subreddit="r", title="t", body="body of the story is long enough",
        # caption_style omitted on purpose
    )
    reddit_story.render(inp, tmp_path)

    _args, render_kwargs = mock_render_vp.call_args
    assert render_kwargs["caption_style"] == "kinetic_word"


@patch("apps.worker.render_adapters.reddit_story.render_video_plan")
@patch("apps.worker.render_adapters.reddit_story.generate_video_plan")
def test_reddit_story_honors_overridden_caption_style(
    mock_gen, mock_render_vp, tmp_path: Path,
):
    mock_gen.return_value = [MagicMock()]
    fake_mp4 = tmp_path / "out.mp4"
    fake_mp4.write_bytes(b"x")
    mock_render_vp.return_value = _fake_artifacts(fake_mp4)

    inp = RedditStoryInput(
        subreddit="r", title="t", body="body of the story is long enough",
        caption_style="impact_uppercase",
    )
    reddit_story.render(inp, tmp_path)
    _args, render_kwargs = mock_render_vp.call_args
    assert render_kwargs["caption_style"] == "impact_uppercase"
