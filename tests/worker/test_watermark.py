"""Watermark step — Phase 3.

Verifies:
  - Free tier produces a *new* mp4 with the watermark suffix.
  - Paid tier returns the source path unchanged (no re-encode).

Generates the test mp4 via ``ffmpeg lavfi`` directly so the test
doesn't depend on edge-tts network access.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import imageio_ffmpeg

from apps.worker.render_adapters._watermark import maybe_watermark


def _make_short_render(tmp_path: Path) -> Path:
    """Synthesize a 2-second 9:16 mp4 with silent audio via ffmpeg lavfi."""
    out = tmp_path / "voiceover.mp4"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-f", "lavfi", "-i", "color=c=0x0b0b0f:s=576x1024:d=2:r=24",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=24000",
        "-t", "2",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "32k",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    assert out.exists() and out.stat().st_size > 1_000
    return out


def test_paid_tier_skips_watermark_and_returns_input(tmp_path: Path):
    src = _make_short_render(tmp_path)
    out = maybe_watermark(src=src, tier="pro", work_dir=tmp_path)
    assert out == src
    # No new mp4 created.
    assert not (tmp_path / f"{src.stem}.watermarked.mp4").exists()


def test_free_tier_burns_a_new_mp4(tmp_path: Path):
    src = _make_short_render(tmp_path)
    out = maybe_watermark(src=src, tier="free", work_dir=tmp_path)
    assert out != src
    assert out.exists()
    assert out.stat().st_size > 5_000
    assert out.name.endswith(".watermarked.mp4")
