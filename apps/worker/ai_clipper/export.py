"""Cut a single moment into a finished short clip.

Single ffmpeg pass per clip. The pipeline:

  1. Trim ``[start, end]`` from the source.
  2. Optionally crop+pad+scale to a target aspect (9:16 / 1:1 / 16:9).
  3. Optionally burn ASS subtitles built from the moment's word timings.
  4. Re-encode to libx264 / aac and emit a new mp4 in ``work_dir``.

We use a single filter graph instead of chaining mp4s on disk because:
  - chained passes triple the encode cost,
  - ASS burn-in needs sub-shifted timings; doing it on the trimmed stream
    is easier than against the source absolute time.

ffmpeg's ``-ss`` before ``-i`` is fast-seek (key-frame snap, can be off
by a frame); ``-ss`` after ``-i`` is exact-seek (slower but accurate).
We seek twice — fast before to skip past most of the file, then accurate
after to land on the exact frame.
"""

from __future__ import annotations

import logging
import subprocess
import urllib.request
import uuid
from pathlib import Path
from typing import Optional

import imageio_ffmpeg

from apps.worker.ai_clipper.segment import Moment


logger = logging.getLogger(__name__)


_ASPECT_TARGETS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}


def _download(url: str, dst: Path) -> None:
    """Resolve ``url`` to ``dst`` (http(s) → urlretrieve, local → copy)."""
    if url.startswith(("http://", "https://")):
        urllib.request.urlretrieve(url, dst)
        return
    src = Path(url)
    if src.exists():
        dst.write_bytes(src.read_bytes())
        return
    raise FileNotFoundError(f"could not resolve clip source: {url}")


def _ass_timecode(seconds: float) -> str:
    """Format seconds → ``H:MM:SS.cc`` (centiseconds, ASS-friendly)."""
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds - h * 3600 - m * 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _moment_to_ass(
    moment: Moment,
    *,
    width: int,
    height: int,
) -> str:
    """Build a small ASS subtitle file timed to the *clipped* stream.

    Word timings in ``moment`` are absolute to the source — we shift
    by ``moment.start`` so 0.0 in the ASS = the first frame of the clip.
    Each whisper segment becomes one centered caption line.

    Style is intentionally simple — heavy bold + drop shadow on a
    semi-transparent box. The Phase 7 caption-engine roadmap layers
    karaoke / emoji emphasis on top.
    """
    font_size = max(36, height // 22)
    out_lines: list[str] = []
    out_lines.append("[Script Info]")
    out_lines.append("ScriptType: v4.00+")
    out_lines.append(f"PlayResX: {width}")
    out_lines.append(f"PlayResY: {height}")
    out_lines.append("ScaledBorderAndShadow: yes")
    out_lines.append("")
    out_lines.append("[V4+ Styles]")
    out_lines.append(
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding"
    )
    # White text, black outline, drop shadow. Alignment 2 = bottom center.
    out_lines.append(
        f"Style: Caption,Arial,{font_size},&H00FFFFFF,&H00FFFFFF,"
        f"&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,80,80,"
        f"{int(height * 0.18)},1"
    )
    out_lines.append("")
    out_lines.append("[Events]")
    out_lines.append(
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text"
    )

    base = moment.start
    for seg in moment.segments:
        start = max(0.0, seg.start - base)
        end = max(start + 0.05, seg.end - base)
        text = (seg.text or "").replace("\n", " ").strip()
        if not text:
            continue
        # ASS escapes commas and newlines in the Text field
        text = text.replace("{", "(").replace("}", ")")
        out_lines.append(
            f"Dialogue: 0,{_ass_timecode(start)},{_ass_timecode(end)},"
            f"Caption,,0,0,0,,{text}"
        )

    return "\n".join(out_lines) + "\n"


def export_one_clip(
    *,
    src_url: str,
    moment: Moment,
    work_dir: Path,
    aspect: str = "9:16",
    burn_captions: bool = True,
    crf: int = 20,
) -> Path:
    """Cut + reframe + caption ``moment`` into a fresh mp4.

    Args:
        src_url: URL or local path to the source video / audio. Audio-
          only sources still produce an mp4 — we synthesize a black
          background for the picture stream.
        moment: One ``Moment`` from ``segment.find_moments``.
        work_dir: Scratch dir for temp files; the output is also
          written here.
        aspect: One of ``"9:16"``, ``"1:1"``, ``"16:9"``.
        burn_captions: When True, render an ASS file from the moment's
          per-segment text and burn it into the video.
        crf: x264 quality knob — lower = better quality, larger file.

    Returns:
        Path to the finished mp4. File is at least a few KB on success.
    """
    if aspect not in _ASPECT_TARGETS:
        raise ValueError(
            f"unsupported aspect {aspect!r}; want {list(_ASPECT_TARGETS)}"
        )
    if moment.duration <= 0:
        raise ValueError(f"moment duration must be > 0 ({moment.moment_id})")

    work_dir.mkdir(parents=True, exist_ok=True)
    width, height = _ASPECT_TARGETS[aspect]

    src_local = work_dir / f"clipsrc_{uuid.uuid4().hex[:8]}.mp4"
    _download(src_url, src_local)

    out = work_dir / (
        f"clip_{moment.moment_id}_{aspect.replace(':', 'x')}.mp4"
    )

    target_ar = width / height
    vf_parts = [
        # Centered crop to target aspect, then scale to canonical pixels.
        f"crop='min(iw,ih*{target_ar:.6f})':'min(ih,iw/{target_ar:.6f})'",
        f"scale={width}:{height}",
        "setsar=1",
    ]

    ass_path: Optional[Path] = None
    if burn_captions and moment.segments:
        ass_path = work_dir / f"clip_{moment.moment_id}.ass"
        ass_path.write_text(
            _moment_to_ass(moment, width=width, height=height),
            encoding="utf-8",
        )
        # ffmpeg subtitles filter expects forward slashes + escaped colons.
        ass_arg = str(ass_path).replace("\\", "/").replace(":", r"\:")
        vf_parts.append(f"subtitles='{ass_arg}'")

    vf = ",".join(vf_parts)

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        # Fast seek to a few seconds before the cut, then accurate seek.
        "-ss", f"{max(0.0, moment.start - 2.0):.3f}",
        "-i", str(src_local),
        "-ss", f"{min(2.0, moment.start):.3f}",
        "-t", f"{moment.duration:.3f}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out),
    ]
    logger.info("export_one_clip: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg clip export failed (exit={proc.returncode}):\n"
            f"{proc.stderr[-1500:]}"
        )
    if not out.exists() or out.stat().st_size < 1_000:
        raise RuntimeError(
            f"clip export produced empty/missing file: {out}"
        )
    return out
