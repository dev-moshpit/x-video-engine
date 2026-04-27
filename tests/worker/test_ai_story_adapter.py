"""AI Story adapter test (PR 5).

The heavy renderer (``render_video_plan``) needs SDXL and a GPU, so we
mock it. We assert:
  - ``generate_video_plan`` is called with the right kwargs derived
    from the typed AIStoryInput
  - ``render_video_plan`` is called with the first plan + finalize=True
  - The adapter returns the path the renderer set on ``final_mp4``
  - If the renderer fails to produce a final mp4 (returns artifacts
    with ``final_mp4=None``), the adapter raises RuntimeError
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.worker.render_adapters import ai_story
from apps.worker.template_inputs import AIStoryInput


def _fake_artifacts(final_mp4: Path | None) -> MagicMock:
    artifacts = MagicMock()
    artifacts.final_mp4 = final_mp4
    return artifacts


@patch("apps.worker.render_adapters.ai_story.render_video_plan")
@patch("apps.worker.render_adapters.ai_story.generate_video_plan")
def test_ai_story_renders_and_returns_final_mp4(
    mock_gen, mock_render_vp, tmp_path: Path,
):
    fake_plan = MagicMock()
    fake_plan.title = "fake"
    mock_gen.return_value = [fake_plan]

    fake_mp4 = tmp_path / "out.mp4"
    fake_mp4.write_bytes(b"fake mp4 bytes")
    mock_render_vp.return_value = _fake_artifacts(fake_mp4)

    result = ai_story.render(
        AIStoryInput(
            prompt="Make a motivational video about discipline.",
            duration=18.0,
            aspect="9:16",
            style="intense",
            seed=4242,
            voice_name="en-US-GuyNeural",
            caption_style="bold_word",
        ),
        tmp_path,
    )

    assert result == fake_mp4

    # generate_video_plan was called with the typed input's fields
    _args, gen_kwargs = mock_gen.call_args
    assert gen_kwargs["prompt"] == "Make a motivational video about discipline."
    assert gen_kwargs["duration"] == 18.0
    assert gen_kwargs["aspect_ratio"] == "9:16"
    assert gen_kwargs["style"] == "intense"
    assert gen_kwargs["seed"] == 4242
    assert gen_kwargs["variations"] == 1
    assert gen_kwargs["score_and_filter"] is True

    # render_video_plan got the plan + the post-stage knobs
    _args, render_kwargs = mock_render_vp.call_args
    assert render_kwargs["plan"] is fake_plan
    assert render_kwargs["finalize"] is True
    assert render_kwargs["want_voice"] is True
    assert render_kwargs["want_captions"] is True
    assert render_kwargs["want_hook"] is True
    assert render_kwargs["voice_name"] == "en-US-GuyNeural"
    assert render_kwargs["caption_style"] == "bold_word"


@patch("apps.worker.render_adapters.ai_story.render_video_plan")
@patch("apps.worker.render_adapters.ai_story.generate_video_plan")
def test_ai_story_raises_when_renderer_returns_no_mp4(
    mock_gen, mock_render_vp, tmp_path: Path,
):
    mock_gen.return_value = [MagicMock()]
    mock_render_vp.return_value = _fake_artifacts(None)

    with pytest.raises(RuntimeError, match="no final MP4"):
        ai_story.render(
            AIStoryInput(prompt="Make a real video about discipline."),
            tmp_path,
        )
