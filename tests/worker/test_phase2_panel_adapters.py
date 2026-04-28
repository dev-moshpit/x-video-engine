"""Integration tests for the panel-driven Phase 2 adapters.

Covers Would You Rather, Twitter, Top 5, and Roblox Rant. All four go
through the shared overlay helper (PNG sequence → mp4 → TTS → mux), so
one combined test file keeps the fixtures simple. Each test uses real
edge-tts + ffmpeg — slower than mocked tests but cheap enough for CI
(no GPU, no SDXL).

Marked ``slow`` so a future ``-m 'not slow'`` run can skip the suite
during quick fix-then-rerun loops.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.worker.render_adapters import (
    roblox_rant,
    top_five,
    twitter,
    would_you_rather,
)
from apps.worker.template_inputs import (
    RobloxRantInput,
    TopFiveInput,
    TopFiveItem,
    TwitterInput,
    WouldYouRatherInput,
)


@pytest.mark.slow
def test_would_you_rather_renders(tmp_path: Path):
    inp = WouldYouRatherInput(
        question="Would you rather have invisibility or flight?",
        option_a="Invisibility",
        option_b="Flight",
        timer_seconds=3,
        reveal_percent_a=40,
        aspect="9:16",
    )
    final = would_you_rather.render(inp, tmp_path)
    assert final.exists()
    assert final.stat().st_size > 30_000
    # Per-beat panels.
    assert (tmp_path / "wyr_frames" / "reveal.png").exists()


@pytest.mark.slow
def test_twitter_single_tweet_renders(tmp_path: Path):
    inp = TwitterInput(
        handle="elonmusk",
        display_name="Elon Musk",
        text="Twitter is now X. Same bird, different cage.",
        likes=12_000, retweets=800, replies=2_500, views=450_000,
        verified=True, dark_mode=True,
        aspect="9:16",
    )
    final = twitter.render(inp, tmp_path)
    assert final.exists()
    assert final.stat().st_size > 30_000
    assert (tmp_path / "twitter_frames" / "tweet_00.png").exists()


@pytest.mark.slow
def test_twitter_thread_renders_multiple_panels(tmp_path: Path):
    inp = TwitterInput(
        handle="naval",
        display_name="Naval",
        text="Reading is faster than listening. Thinking is faster than reading.",
        thread=[
            "If you can't read, listen.",
            "If you can't think, ask.",
        ],
        likes=5_000, retweets=200, replies=80, views=120_000,
        verified=True, dark_mode=False,
        aspect="9:16",
    )
    final = twitter.render(inp, tmp_path)
    assert final.exists()
    panels = sorted((tmp_path / "twitter_frames").glob("tweet_*.png"))
    assert len(panels) == 3


@pytest.mark.slow
def test_top_five_renders_countdown(tmp_path: Path):
    inp = TopFiveInput(
        title="Top 3 cities",
        items=[
            TopFiveItem(title="Tokyo", description="neon dreams"),
            TopFiveItem(title="Reykjavik", description="aurora borealis"),
            TopFiveItem(title="Cape Town", description="mountains meet sea"),
        ],
        per_item_seconds=3.0,
        aspect="9:16",
    )
    final = top_five.render(inp, tmp_path)
    assert final.exists()
    assert final.stat().st_size > 30_000
    # One panel per ranked item.
    panels = sorted((tmp_path / "top_five_frames").glob("rank_*.png"))
    assert len(panels) == 3


@pytest.mark.slow
def test_roblox_rant_falls_back_to_solid_when_no_bg(tmp_path: Path):
    """Without a usable background_url, roblox_rant uses the solid-bg path."""
    inp = RobloxRantInput(
        script=(
            "Listen up. The new update destroyed everything we loved. "
            "It is over. We are done."
        ),
        speech_rate="+10%",
        aspect="9:16",
    )
    final = roblox_rant.render(inp, tmp_path)
    assert final.exists()
    assert final.stat().st_size > 30_000
    assert (tmp_path / "roblox_rant_voice.mp3").exists()
