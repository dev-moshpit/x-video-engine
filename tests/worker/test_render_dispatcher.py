"""Dispatcher + worker/api schema parity (PR 5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from apps.worker.render_adapters import ADAPTERS, render_for_template
from apps.worker.template_inputs import (
    AIStoryInput,
    AutoCaptionsInput,
    FakeTextInput,
    RedditStoryInput,
    RobloxRantInput,
    SplitVideoInput,
    TopFiveInput,
    TwitterInput,
    VoiceoverInput,
    WouldYouRatherInput,
)


_PHASE1 = {"ai_story", "auto_captions", "reddit_story", "voiceover"}
_PHASE2 = {
    "fake_text", "would_you_rather", "split_video",
    "twitter", "top_five", "roblox_rant",
}


def test_adapters_registry_has_all_phase1_and_phase2_templates():
    assert set(ADAPTERS) == _PHASE1 | _PHASE2


def test_each_entry_has_input_model_and_module():
    for tid, entry in ADAPTERS.items():
        assert issubclass(entry.input_model, object)
        assert hasattr(entry.module, "render"), (
            f"adapter '{tid}' module is missing render() function"
        )


def test_render_for_unknown_template_raises_valueerror(tmp_path: Path):
    with pytest.raises(ValueError, match="unknown template"):
        render_for_template("totally_made_up_template", {}, tmp_path)


def test_invalid_input_raises_validation_error_before_render(tmp_path: Path):
    """Bad input is rejected by Pydantic before the heavy render fn runs."""
    with pytest.raises(ValidationError):
        render_for_template("ai_story", {"prompt": "x"}, tmp_path)  # too short


# ─── Schema parity with apps/api ────────────────────────────────────────
#
# The four input models above are *copies* of the api's models for
# decoupling (worker can deploy to a separate machine without the api
# package). This test fails loudly if the two copies drift in shape.

def test_input_schema_parity_with_api():
    # Import lazily to avoid pulling api modules at collection time.
    import sys
    from pathlib import Path as _Path
    _api_root = _Path(__file__).resolve().parents[2] / "apps" / "api"
    if str(_api_root) not in sys.path:
        sys.path.insert(0, str(_api_root))

    from app.schemas.templates import (  # noqa: E402
        AIStoryInput as APIAIStory,
        AutoCaptionsInput as APIAutoCaptions,
        FakeTextInput as APIFakeText,
        RedditStoryInput as APIReddit,
        RobloxRantInput as APIRobloxRant,
        SplitVideoInput as APISplitVideo,
        TopFiveInput as APITopFive,
        TwitterInput as APITwitter,
        VoiceoverInput as APIVoiceover,
        WouldYouRatherInput as APIWYR,
    )

    pairs = [
        (AIStoryInput, APIAIStory),
        (RedditStoryInput, APIReddit),
        (VoiceoverInput, APIVoiceover),
        (AutoCaptionsInput, APIAutoCaptions),
        (FakeTextInput, APIFakeText),
        (WouldYouRatherInput, APIWYR),
        (SplitVideoInput, APISplitVideo),
        (TwitterInput, APITwitter),
        (TopFiveInput, APITopFive),
        (RobloxRantInput, APIRobloxRant),
    ]
    for worker_model, api_model in pairs:
        assert (
            worker_model.model_json_schema() == api_model.model_json_schema()
        ), (
            f"schema drift: worker {worker_model.__name__} differs from "
            f"api {api_model.__name__} — sync them"
        )
