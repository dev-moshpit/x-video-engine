"""Fake Text adapter tests.

Covers two paths:

  - Silent render (no narration, no voice) — fastest, validates the
    Pillow chat-frame renderer + the ffmpeg image-sequence encoder.
    No edge-tts dependency on the Phase 2 happy path means CI stays
    deterministic on machines without network access to Microsoft.
  - Voiced render (narrate=True) — exercises the TTS-aligned timing
    + post-stack final mux.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.worker.render_adapters import fake_text
from apps.worker.template_inputs import FakeTextInput, FakeTextMessage


def _sample_messages() -> list[FakeTextMessage]:
    return [
        FakeTextMessage(sender="them", text="Hey are you up?",
                        typing_ms=600, hold_ms=900),
        FakeTextMessage(sender="me", text="Yeah what's up?",
                        typing_ms=600, hold_ms=900),
        FakeTextMessage(sender="them", text="I need a favor.",
                        typing_ms=800, hold_ms=1200),
    ]


def test_fake_text_silent_render_produces_mp4(tmp_path: Path):
    inp = FakeTextInput(
        style="ios", theme="dark",
        chat_title="Mom", aspect="9:16",
        narrate=False, voice_name=None, caption_style=None,
        messages=_sample_messages(),
    )
    final = fake_text.render(inp, tmp_path)

    assert final.exists()
    # Silent chat video is purely image concat — should still be > 5 KB
    # for a ~5s clip at 9:16 with three messages.
    assert final.stat().st_size > 5_000
    # Per-beat PNG frames + the concat-encoded chat mp4 should both exist.
    assert (tmp_path / "fake_text_chat.mp4").exists()
    assert (tmp_path / "chat_frames").is_dir()
    assert any((tmp_path / "chat_frames").glob("frame_*.png"))


def test_fake_text_renders_each_style(tmp_path: Path):
    """Every (style, theme) pair must produce a valid PNG without crashing."""
    msgs = _sample_messages()
    for i, style in enumerate(["ios", "whatsapp", "instagram", "tinder"]):
        for theme in ["light", "dark"]:
            sub = tmp_path / f"{style}_{theme}"
            inp = FakeTextInput(
                style=style, theme=theme,  # type: ignore[arg-type]
                chat_title="Test", aspect="9:16",
                narrate=False, messages=msgs,
            )
            final = fake_text.render(inp, sub)
            assert final.exists(), f"{style}/{theme} produced no mp4"
            assert final.stat().st_size > 1_000


@pytest.mark.slow
def test_fake_text_voiced_render(tmp_path: Path):
    inp = FakeTextInput(
        style="whatsapp", theme="light",
        chat_title="Sarah", aspect="9:16",
        narrate=True, caption_style="bold_word",
        messages=_sample_messages(),
    )
    final = fake_text.render(inp, tmp_path)

    assert final.exists()
    assert (tmp_path / "fake_text_voice.mp3").exists()
    assert (tmp_path / "fake_text_chat.mp4").exists()
    # Voiced final has TTS audio + captions — should be heavier than silent.
    assert final.stat().st_size > 30_000
