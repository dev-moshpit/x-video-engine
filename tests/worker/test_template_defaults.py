from __future__ import annotations

from apps.worker.template_inputs import (
    FakeTextInput,
    FakeTextMessage,
    RobloxRantInput,
    TopFiveInput,
    TopFiveItem,
    TwitterInput,
    VoiceoverInput,
    WouldYouRatherInput,
)


def test_caption_style_defaults_match_product_policy():
    assert VoiceoverInput(script="This is a clean voiceover script.").caption_style == "clean_subtitle"
    assert RobloxRantInput(script="This update is wild and everyone needs to hear it.").caption_style == "impact_uppercase"
    # WYR has its own captions on-panel (the question + both options +
    # timer); burning impact_uppercase ASS captions on top of the timer
    # produced overlap in QA. Default is now no captions; operators can
    # opt in via caption_style.
    assert WouldYouRatherInput(
        question="Would you rather be invisible or fly forever?",
        option_a="Be invisible",
        option_b="Fly forever",
    ).caption_style is None


def test_fake_text_media_fields_are_schema_supported():
    inp = FakeTextInput(
        style="ios",
        theme="dark",
        chat_title="Alex",
        messages=[FakeTextMessage(sender="them", text="Are you there?")],
        background_color="#123456",
        background_url="https://cdn.example/bg.mp4",
        avatar_url="https://cdn.example/avatar.jpg",
        show_timestamps=True,
    )
    assert inp.background_url
    assert inp.avatar_url
    assert inp.show_timestamps is True


def test_panel_templates_support_library_background_url():
    assert WouldYouRatherInput(
        question="Would you rather be invisible or fly forever?",
        option_a="Be invisible",
        option_b="Fly forever",
        background_url="https://cdn.example/gameplay.mp4",
    ).background_url
    assert TwitterInput(
        handle="x",
        display_name="X",
        text="This needs a moving background.",
        background_url="https://cdn.example/bg.mp4",
    ).background_url
    assert TopFiveInput(
        title="Top 3 hooks",
        items=[
            TopFiveItem(title="First"),
            TopFiveItem(title="Second"),
            TopFiveItem(title="Third"),
        ],
        background_url="https://cdn.example/bg.mp4",
    ).background_url
