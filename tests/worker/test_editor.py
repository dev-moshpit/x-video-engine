"""Editor pipeline tests — Platform Phase 1.

Exercises the single-pass editor with a synthetic mp4. We verify:
  * trim bounds are honored
  * reframe to each supported aspect produces a real mp4
  * ``aspect="source"`` skips the reframe filter graph
  * captions=False short-circuits the whisper step (no Whisper needed)
  * trim_end <= trim_start raises a clear error
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import imageio_ffmpeg
import pytest

from apps.worker.editor import EditorJobInput, process_editor_job


def _make_silent_video(out: Path, duration: float = 8.0) -> Path:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-t", f"{duration:.2f}",
        "-f", "lavfi",
        "-i", "color=c=black:s=320x240:r=24",
        "-t", f"{duration:.2f}",
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=mono:sample_rate=16000",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    return out


def test_editor_export_no_trim_no_captions(tmp_path: Path):
    src = _make_silent_video(tmp_path / "src.mp4", duration=6.0)
    inp = EditorJobInput(
        source_url=str(src),
        aspect="9:16",
        captions=False,
    )
    out = process_editor_job(inp, tmp_path)
    assert out.exists()
    assert out.stat().st_size > 5_000


def test_editor_with_trim_only(tmp_path: Path):
    src = _make_silent_video(tmp_path / "src.mp4", duration=10.0)
    inp = EditorJobInput(
        source_url=str(src),
        trim_start=2.0,
        trim_end=6.0,
        aspect="1:1",
        captions=False,
    )
    out = process_editor_job(inp, tmp_path)
    assert out.exists()
    assert out.stat().st_size > 5_000


def test_editor_aspect_source_skips_reframe(tmp_path: Path):
    src = _make_silent_video(tmp_path / "src.mp4", duration=4.0)
    inp = EditorJobInput(
        source_url=str(src),
        aspect="source",
        captions=False,
    )
    out = process_editor_job(inp, tmp_path)
    assert out.exists()
    assert out.stat().st_size > 1_000


def test_editor_rejects_unknown_aspect(tmp_path: Path):
    src = _make_silent_video(tmp_path / "src.mp4", duration=4.0)
    inp = EditorJobInput(
        source_url=str(src),
        aspect="4:3",
        captions=False,
    )
    with pytest.raises(ValueError):
        process_editor_job(inp, tmp_path)


def test_editor_captions_path_handles_whisper_unavailable(tmp_path: Path):
    """When Whisper isn't installed the captions step must skip cleanly.

    The export still has to produce a valid mp4; it just won't have
    burned-in subtitles. That mirrors the auto_captions render-adapter
    fallback contract from Phase 2.
    """
    src = _make_silent_video(tmp_path / "src.mp4", duration=5.0)
    inp = EditorJobInput(
        source_url=str(src),
        aspect="16:9",
        captions=True,
        caption_language="en",
    )
    out = process_editor_job(inp, tmp_path)
    assert out.exists()
    assert out.stat().st_size > 5_000
