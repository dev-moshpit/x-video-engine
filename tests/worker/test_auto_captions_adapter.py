"""Auto-Captions adapter test (PR 5) — real edge-tts + ffmpeg.

Same shared pipeline as voiceover, just exercised through the
auto_captions module to guard against the dispatcher mis-wiring it.
"""

from __future__ import annotations

from pathlib import Path

from apps.worker.render_adapters import auto_captions
from apps.worker.template_inputs import AutoCaptionsInput


def test_auto_captions_renders_real_mp4(tmp_path: Path):
    inp = AutoCaptionsInput(
        script=(
            "Auto-captions test. Each word should land on screen "
            "as I speak, big and bold over a flat background."
        ),
        caption_style="bold_word",
        language="en",
        aspect="9:16",
    )
    final = auto_captions.render(inp, tmp_path)

    assert final.exists()
    assert final.stat().st_size > 30_000
    assert (tmp_path / "auto_captions_voice.mp3").exists()
    assert (tmp_path / "auto_captions_captions.ass").exists()
    assert (tmp_path / "auto_captions_bg.mp4").exists()
