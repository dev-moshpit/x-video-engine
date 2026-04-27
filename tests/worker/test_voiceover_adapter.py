"""Voiceover adapter test (PR 5) — real edge-tts + ffmpeg.

This is an integration test of the post-stack happy path. Slower
than the mocked adapter tests (~5–10 s for TTS + ffmpeg), but it
exercises the actual renderer end-to-end without GPU.
"""

from __future__ import annotations

from pathlib import Path

from apps.worker.render_adapters import voiceover
from apps.worker.template_inputs import VoiceoverInput


def test_voiceover_renders_real_mp4(tmp_path: Path):
    inp = VoiceoverInput(
        script=(
            "Hello world. This is a short test of the voiceover adapter. "
            "Captions should appear over a solid black background."
        ),
        background_color="#0b0b0f",
        aspect="9:16",
    )
    final = voiceover.render(inp, tmp_path)

    assert final.exists()
    # A valid 9:16 short with TTS + captions + bg should be at least
    # 30 KB. Typical real output is 100 KB+.
    assert final.stat().st_size > 30_000

    # All intermediate artifacts written next to the final.
    assert (tmp_path / "voiceover_voice.mp3").exists()
    assert (tmp_path / "voiceover_captions.ass").exists()
    assert (tmp_path / "voiceover_bg.mp4").exists()


def test_voiceover_honors_aspect_and_color(tmp_path: Path):
    inp = VoiceoverInput(
        script=(
            "Square aspect ratio test for the voiceover adapter render path."
        ),
        background_color="#102030",
        aspect="1:1",
    )
    final = voiceover.render(inp, tmp_path)
    assert final.exists()
    # bg mp4 should also be present and non-trivial
    assert (tmp_path / "voiceover_bg.mp4").stat().st_size > 1_000
