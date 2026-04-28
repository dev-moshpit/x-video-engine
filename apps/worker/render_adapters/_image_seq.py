"""Convert a sequence of (PNG, duration) frames → MP4 via ffmpeg.

Phase 2 adapters that burn UI to images (fake_text, would_you_rather,
twitter, top_five) build a list of ``Frame(png_path, duration_sec)``
beats and call :func:`encode_frame_sequence` to mux them into a steady-fps
video. The encoder writes an ffmpeg ``concat`` demuxer file under the
work_dir so each frame holds for its own duration without re-encoding
per beat.

The output is the *visual* track — adapters compose it with TTS audio
and burned captions afterwards via the existing post-stack
(``render_prompt_native_final``) so the final-mux behavior matches what
the rest of the SaaS uses.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Frame:
    """One beat in a UI-driven adapter timeline."""
    image: Path
    duration_sec: float


def encode_frame_sequence(
    *,
    frames: list[Frame],
    out_path: Path,
    size: tuple[int, int],
    fps: int = 24,
) -> Path:
    """Concat ``frames`` into a steady-fps mp4 of total = sum(durations).

    Uses the ffmpeg concat demuxer + ``-vsync vfr`` so each PNG is held
    on screen for its own ``duration_sec``. Re-encodes to libx264 yuv420p
    at the target fps so downstream filters (overlay, captions) work.
    """
    if not frames:
        raise ValueError("encode_frame_sequence: frames list is empty")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    concat_file = out_path.with_suffix(".concat.txt")
    lines: list[str] = []
    for f in frames:
        if not f.image.exists():
            raise FileNotFoundError(f"frame image missing: {f.image}")
        # ffmpeg concat demuxer requires forward slashes + escaped quotes.
        lines.append(f"file '{f.image.as_posix()}'")
        lines.append(f"duration {max(f.duration_sec, 0.04):.3f}")
    # The concat demuxer needs the last image repeated without a duration
    # so the final beat doesn't get truncated.
    lines.append(f"file '{frames[-1].image.as_posix()}'")
    concat_file.write_text("\n".join(lines), encoding="utf-8")

    width, height = size
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-vf", f"scale={width}:{height}:flags=lanczos,fps={fps}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    logger.info("frame_seq: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg frame-seq encode failed (exit={proc.returncode}):\n"
            f"{proc.stderr[-2000:]}"
        )
    if not out_path.exists() or out_path.stat().st_size < 1_000:
        raise RuntimeError(
            f"frame-seq encode produced empty/tiny output: {out_path}"
        )
    return out_path


def total_duration(frames: list[Frame]) -> float:
    return sum(max(f.duration_sec, 0.04) for f in frames)
