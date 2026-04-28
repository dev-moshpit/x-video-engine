"""Auto-Captions Phase 2 upload-path tests.

Exercises the new ``audio_url`` / ``video_url`` branch added in Phase 2.
We don't require faster-whisper to be installed for the test to pass —
when the import fails the adapter must fall back to the TTS-from-script
path. That fallback is the contract this test pins.

The "happy path" with real Whisper inference is intentionally out of
scope here; CI machines that ship with faster-whisper can extend this
file with a real-transcription test gated on ``pytest.importorskip``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import imageio_ffmpeg
import pytest

from apps.worker.render_adapters import auto_captions
from apps.worker.template_inputs import AutoCaptionsInput


def _make_silent_wav(out: Path, duration: float = 2.0) -> Path:
    """Synthesize a brief silent WAV via ffmpeg lavfi.

    Used to simulate an uploaded audio file without bringing real
    speech assets into the test fixtures.
    """
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=channel_layout=mono:sample_rate=16000",
        "-t", f"{duration:.2f}",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    return out


def test_audio_url_path_falls_back_when_whisper_unavailable(tmp_path: Path):
    """If faster-whisper isn't installed (or returns no words), the
    adapter must transparently use the TTS-from-script path."""
    audio = _make_silent_wav(tmp_path / "fake_upload.wav")

    inp = AutoCaptionsInput(
        script="The script the adapter falls back to when Whisper can't transcribe.",
        audio_url=str(audio),
        caption_style="bold_word",
        language="en",
        aspect="9:16",
    )
    final = auto_captions.render(inp, tmp_path)

    assert final.exists()
    assert final.stat().st_size > 30_000

    # Either the Whisper path produced auto_captions.mp4 directly OR the
    # script fallback ran and wrote auto_captions_voice.mp3 + bg + ass.
    # Both end with a real mp4 — the contract is "you always get one".
    has_voice = (tmp_path / "auto_captions_voice.mp3").exists()
    has_bg = (tmp_path / "auto_captions_bg.mp4").exists()
    assert has_voice and has_bg


def test_unreachable_video_url_falls_back_silently(tmp_path: Path):
    """A 404 video URL should not crash — adapter falls back to script."""
    inp = AutoCaptionsInput(
        script="Fallback when the upload URL doesn't resolve to a real file.",
        video_url="http://localhost:1/no-such-host.mp4",
        caption_style="bold_word",
        language="en",
        aspect="9:16",
    )
    final = auto_captions.render(inp, tmp_path)
    assert final.exists()
    assert final.stat().st_size > 30_000
