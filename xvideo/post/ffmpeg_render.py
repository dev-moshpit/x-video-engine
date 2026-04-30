"""Final MP4 compositor.

Inputs  : background video, voiceover audio, SRT captions, hook text.
Outputs : final 9:16 MP4 (H.264/AAC), burned captions + hook overlay.

Runs the bundled ffmpeg binary (imageio-ffmpeg) so we don't depend on a
system install. Windows path escaping for filter arguments is handled
explicitly — colons in drive letters are the main booby trap.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg

logger = logging.getLogger(__name__)


# One clean viral caption style: bold white, black stroke, bottom-center.
# NOTE: libass measures MarginV in its own coord space (not video pixels),
# so keep this modest; ~40 places captions at ~75% down a 9:16 frame.
DEFAULT_SUBTITLE_STYLE = (
    "FontName=Arial,"
    "FontSize=22,"
    "Bold=-1,"
    "PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,"
    "BorderStyle=1,"
    "Outline=3,"
    "Shadow=1,"
    "Alignment=2,"                     # bottom-center
    "MarginV=40"
)


@dataclass
class RenderOptions:
    hook_text: str = ""
    hook_start_sec: float = 0.3
    hook_end_sec: float = 2.5
    hook_font_size: int = 52
    subtitle_style: str = DEFAULT_SUBTITLE_STYLE
    # Final duration clamp. None = min(video_dur, voice_dur) via -shortest.
    target_duration_sec: float | None = None
    # Optional explicit font file for drawtext (Windows needs this reliably).
    fontfile: str = "C:/Windows/Fonts/arialbd.ttf"


def _escape_for_filter(path: Path | str) -> str:
    """Escape a path so it's safe inside an ffmpeg filter argument.

    Forward slashes throughout, colon after the drive letter escaped so
    ffmpeg's filter parser doesn't treat it as a key=value separator.
    Returns the path WITHOUT wrapping quotes; caller should wrap in `'...'`
    when inserting into the filter graph.
    """
    s = str(path).replace("\\", "/")
    # Escape the drive-letter colon: D:/foo -> D\:/foo
    if len(s) >= 2 and s[1] == ":":
        s = s[0] + r"\:" + s[2:]
    return s


def _hook_drawtext(opts: RenderOptions, hook_text_file: Path) -> str:
    """Build the drawtext filter for the hook overlay."""
    fontfile = _escape_for_filter(opts.fontfile)
    textfile = _escape_for_filter(hook_text_file)
    enable = f"between(t,{opts.hook_start_sec},{opts.hook_end_sec})"
    return (
        f"drawtext=fontfile='{fontfile}':"
        f"textfile='{textfile}':"
        f"fontsize={opts.hook_font_size}:"
        f"fontcolor=white:"
        f"borderw=4:bordercolor=black:"
        f"x=(w-text_w)/2:y=h*0.18:"
        f"enable='{enable}'"
    )


def _subtitles_filter(captions_path: Path, style: str) -> str:
    """Build the `subtitles=` filter for either an SRT or ASS input.

    For ASS files we pass through the file's own styles (skip force_style)
    — that's what enables per-word styling, PlayRes, etc. For SRT we apply
    the default one-line-at-a-time style.
    """
    path = _escape_for_filter(captions_path)
    if str(captions_path).lower().endswith(".ass"):
        return f"subtitles='{path}'"
    return f"subtitles='{path}':force_style='{style}'"


def render_final(
    bg_video: Path,
    voice_audio: Path,
    captions_path: Path,
    out_path: Path,
    opts: RenderOptions | None = None,
) -> Path:
    """Composite a finished short and return the output path.

    `captions_path` may be an .srt or .ass file. For .ass the file's own
    styles win (used for word-level captioning). For .srt we apply the
    one-line bottom-centered default style.

    If hook_text is empty, the drawtext overlay is skipped. Audio comes
    from the voice track only (no bg-video audio mix in MVP); silence is
    padded if voice < video and video is truncated by -shortest otherwise.
    """
    opts = opts or RenderOptions()
    bg_video = Path(bg_video)
    voice_audio = Path(voice_audio)
    captions_path = Path(captions_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Hook text file so we don't have to escape commas/colons in the filter arg.
    hook_file: Path | None = None
    if opts.hook_text.strip():
        hook_file = out_path.with_suffix(".hook.txt")
        hook_file.write_text(opts.hook_text.strip(), encoding="utf-8")

    # Video filter chain
    video_chain = [_subtitles_filter(captions_path, opts.subtitle_style)]
    if hook_file is not None:
        video_chain.append(_hook_drawtext(opts, hook_file))
    vf = ",".join(video_chain)

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd: list[str] = [
        ffmpeg, "-hide_banner", "-y",
        "-i", str(bg_video),
        "-i", str(voice_audio),
        "-vf", vf,
        "-af", "apad",                            # pad voice with silence
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k",
    ]
    if opts.target_duration_sec is not None:
        cmd += ["-t", f"{opts.target_duration_sec:.2f}"]
    else:
        cmd += ["-shortest"]
    cmd.append(str(out_path))

    logger.info("ffmpeg: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # Last 2KB of stderr is usually enough to diagnose.
        raise RuntimeError(
            f"ffmpeg failed (exit={proc.returncode}):\n{proc.stderr[-2000:]}"
        )

    if hook_file is not None and hook_file.exists():
        try:
            hook_file.unlink()
        except Exception:
            pass

    if not out_path.exists() or out_path.stat().st_size < 10_000:
        raise RuntimeError(f"ffmpeg produced empty/invalid output: {out_path}")

    return out_path


def probe_duration(media_path: Path) -> float:
    """Return a media file's duration in seconds (parses ffmpeg stderr)."""
    import re
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(media_path)],
        capture_output=True, text=True,
    )
    m = re.search(r"Duration:\s+(\d+):(\d+):([\d.]+)", proc.stderr)
    if not m:
        return 0.0
    h, mm, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mm * 60 + s
