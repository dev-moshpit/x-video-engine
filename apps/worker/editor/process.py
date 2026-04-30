"""Editor job processor — Platform Phase 1.

One function: ``process_editor_job(input, work_dir) → mp4 path``.

Steps (all optional except the final ffmpeg pass):

  1. Trim — fast-seek + accurate-seek to ``[trim_start, trim_end]``.
  2. Auto-captions — faster-whisper on the trimmed audio, emit ASS.
  3. Single ffmpeg pass: crop+scale to target aspect, optionally
     burn the ASS subtitle stream into the video.

If trim is not requested, we still run the final ffmpeg pass against
the source — the user might just want resize + captions. If neither
captions nor a different aspect were requested, we still re-encode
to ensure a clean mp4 (no faststart, no caption overlay surprises).
"""

from __future__ import annotations

import logging
import subprocess
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import imageio_ffmpeg


logger = logging.getLogger(__name__)


_ASPECT_TARGETS: dict[str, tuple[int, int]] = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
    "source": (0, 0),  # keep input dimensions; flagged below
}


@dataclass
class EditorJobInput:
    """All knobs the user can flip on the editor.

    Times are absolute seconds. ``aspect="source"`` means "don't reframe".
    """
    source_url: str
    trim_start: Optional[float] = None
    trim_end: Optional[float] = None
    aspect: str = "9:16"
    captions: bool = True
    caption_language: str = "auto"
    music_url: Optional[str] = None  # reserved — unused in MVP
    crf: int = 20


def _download(url: str, dst: Path) -> None:
    if url.startswith(("http://", "https://")):
        urllib.request.urlretrieve(url, dst)
        return
    src = Path(url)
    if src.exists():
        dst.write_bytes(src.read_bytes())
        return
    raise FileNotFoundError(f"editor source missing: {url}")


def _trim_source(
    *, src: Path, start: Optional[float], end: Optional[float], work_dir: Path,
) -> tuple[Path, float, float]:
    """Trim ``src`` to ``[start, end]``.

    Returns ``(out_path, abs_start, abs_end)``. If neither bound was
    provided we just return the source unchanged with start=0, end=
    inferred from probe (or 0 if not probed). The pipeline doesn't
    strictly need ``end``; it's used for the captions step.
    """
    if start is None and end is None:
        return src, 0.0, _probe_duration(src)

    start = max(0.0, float(start or 0.0))
    end = end if end is not None else _probe_duration(src)
    end = max(start + 0.1, float(end))

    out = work_dir / f"trim_{uuid.uuid4().hex[:8]}.mp4"
    duration = end - start

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-ss", f"{max(0.0, start - 2.0):.3f}",
        "-i", str(src),
        "-ss", f"{min(2.0, start):.3f}",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"trim failed (exit={proc.returncode}): {proc.stderr[-1500:]}"
        )
    return out, start, end


def _probe_duration(media: Path) -> float:
    """Best-effort duration probe via ffprobe (bundled with imageio-ffmpeg).

    Falls back to 0.0 if ffprobe isn't bundled — only used to set a
    sensible end bound when the user didn't specify one. Any callers
    that need correct duration should pass ``trim_end`` explicitly.
    """
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    # imageio-ffmpeg ships ffmpeg only; ffprobe may or may not be present.
    # Use the ffmpeg "-i ... -" trick: ffmpeg writes Duration: ... to
    # stderr and we parse it.
    proc = subprocess.run(
        [ffmpeg, "-i", str(media)],
        capture_output=True, text=True,
    )
    txt = proc.stderr or ""
    import re
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", txt)
    if not m:
        return 0.0
    h, mn, s = m.groups()
    return int(h) * 3600 + int(mn) * 60 + float(s)


def _ass_for_words(
    words, *, width: int, height: int, abs_start: float,
) -> str:
    """Build a small ASS file from a list of TranscriptWord-like records.

    Times are shifted by ``abs_start`` so 0.0 in the output matches
    the start of the trimmed clip.
    """
    def fmt_t(t: float) -> str:
        t = max(0.0, t)
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = t - h * 3600 - m * 60
        return f"{h}:{m:02d}:{s:05.2f}"

    font_size = max(36, height // 22)
    out = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
         "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
         "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
         "Alignment, MarginL, MarginR, MarginV, Encoding"),
        (f"Style: Caption,Arial,{font_size},&H00FFFFFF,&H00FFFFFF,"
         f"&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,80,80,"
         f"{int(height * 0.18)},1"),
        "",
        "[Events]",
        ("Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
         "MarginV, Effect, Text"),
    ]

    # Group consecutive 4-7 words into one displayed line.
    line_size = 5
    for i in range(0, len(words), line_size):
        group = words[i:i + line_size]
        if not group:
            continue
        start = max(0.0, group[0].start - abs_start)
        end = max(start + 0.05, group[-1].end - abs_start)
        text = " ".join(w.text for w in group).strip()
        if not text:
            continue
        text = text.replace("{", "(").replace("}", ")")
        out.append(
            f"Dialogue: 0,{fmt_t(start)},{fmt_t(end)},Caption,,0,0,0,,{text}"
        )
    return "\n".join(out) + "\n"


def _generate_captions_ass(
    *,
    media: Path,
    work_dir: Path,
    language: str,
    abs_start: float,
    width: int,
    height: int,
) -> Optional[Path]:
    """Run faster-whisper on ``media`` and emit an ASS file.

    Returns None if Whisper isn't installed — callers treat that as
    "no captions" rather than failing the export. The user can set
    ``captions=false`` if they don't want auto-captions; the import
    error is purely a dep-availability issue, not a caller bug.
    """
    try:
        from apps.worker.ai_clipper.transcribe import (
            WhisperUnavailable,
            transcribe_full,
        )
    except ImportError:
        return None

    try:
        transcript = transcribe_full(
            media=media, work_dir=work_dir, language=language,
        )
    except WhisperUnavailable:
        return None

    words = transcript.all_words
    if not words:
        return None

    ass = _ass_for_words(words, width=width, height=height, abs_start=abs_start)
    out = work_dir / "editor_captions.ass"
    out.write_text(ass, encoding="utf-8")
    return out


def process_editor_job(
    inp: EditorJobInput, work_dir: Path,
) -> Path:
    """Run the editor pipeline end-to-end. Returns the final mp4 path."""
    if inp.aspect not in _ASPECT_TARGETS:
        raise ValueError(
            f"unsupported aspect {inp.aspect!r}; want {list(_ASPECT_TARGETS)}"
        )

    work_dir.mkdir(parents=True, exist_ok=True)

    # Resolve source.
    src = work_dir / f"editor_src_{uuid.uuid4().hex[:8]}.mp4"
    _download(inp.source_url, src)

    # Trim if requested.
    trimmed, abs_start, abs_end = _trim_source(
        src=src, start=inp.trim_start, end=inp.trim_end, work_dir=work_dir,
    )

    # Decide target dimensions.
    if inp.aspect == "source":
        width, height = 0, 0
    else:
        width, height = _ASPECT_TARGETS[inp.aspect]

    # Generate captions (optional).
    ass_path: Optional[Path] = None
    if inp.captions:
        # Use stand-in 1080x1920 dims for caption layout if we're not
        # reframing; the burn-in still works against the source.
        cap_w = width or 1080
        cap_h = height or 1920
        # Captions are timed against the trimmed stream (start at 0.0
        # within the trimmed clip), so pass abs_start=trim_start for
        # the shift inside _ass_for_words.
        ass_path = _generate_captions_ass(
            media=trimmed,
            work_dir=work_dir,
            language=inp.caption_language,
            abs_start=abs_start,
            width=cap_w,
            height=cap_h,
        )

    # Final pass: reframe + (optional) burn captions.
    out = work_dir / f"editor_out_{uuid.uuid4().hex[:8]}.mp4"
    vf_parts: list[str] = []
    if inp.aspect != "source":
        target_ar = width / height
        vf_parts += [
            f"crop='min(iw,ih*{target_ar:.6f})':'min(ih,iw/{target_ar:.6f})'",
            f"scale={width}:{height}",
            "setsar=1",
        ]
    if ass_path is not None:
        ass_arg = str(ass_path).replace("\\", "/").replace(":", r"\:")
        vf_parts.append(f"subtitles='{ass_arg}'")

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-i", str(trimmed),
    ]
    if vf_parts:
        cmd += ["-vf", ",".join(vf_parts)]
    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", str(inp.crf),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out),
    ]
    logger.info("editor final pass: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"editor export failed (exit={proc.returncode}): "
            f"{proc.stderr[-1500:]}"
        )
    if not out.exists() or out.stat().st_size < 1_000:
        raise RuntimeError("editor export produced empty/missing file")
    return out
