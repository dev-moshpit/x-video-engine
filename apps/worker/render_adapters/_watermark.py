"""Free-tier watermark — Phase 3.

Burns a small "Made with x-video-engine" tag in the bottom-right
corner of the rendered mp4 when the operator is on the free tier.
Called by the worker's main loop *after* the adapter returns its
final mp4 and *before* the R2 upload.

Implemented as a single ffmpeg pass with ``drawtext`` (no PIL
overlay) so the round-trip is one re-encode, not two. ffmpeg's
drawtext can be picky about font paths on Windows — we reuse the
:func:`apps.worker.render_adapters._font.load_font` probe so the same
font that renders our chat panels also renders the watermark.

If ``tier`` is anything other than ``"free"``, this function is a
no-op and returns the input path unchanged.
"""

from __future__ import annotations

import logging
import platform
import subprocess
from pathlib import Path

import imageio_ffmpeg

from apps.worker.render_adapters._font import _candidate_paths


logger = logging.getLogger(__name__)


_WATERMARK_TEXT = "Made with x-video-engine"


def _stage_font(work_dir: Path) -> str | None:
    """Stage a TTF in ``work_dir`` so the path has no special chars.

    ffmpeg's drawtext filter is fragile about the ``fontfile`` value —
    even with backslash-escaped colons, the Windows ``C:`` prefix
    routinely breaks the parser. Copying the font next to the working
    file gives us a path under ``work_dir`` (which the worker controls)
    so we know it never contains characters that confuse drawtext.

    Returns the staged path as a posix string, or None if no system
    font was found.
    """
    for cand in _candidate_paths(want_bold=True):
        src = Path(cand)
        if not src.exists():
            continue
        dst = work_dir / "_watermark_font.ttf"
        if not dst.exists():
            try:
                dst.write_bytes(src.read_bytes())
            except Exception:
                continue
        return dst.as_posix()
    return None


def _escape_filter_value(value: str) -> str:
    """Escape a value for use inside an ffmpeg filter argument."""
    return (
        value.replace("\\", "\\\\")
             .replace(":", "\\:")
             .replace("'", "\\'")
    )


def maybe_watermark(
    *, src: Path, tier: str, work_dir: Path,
) -> Path:
    """Return a watermarked mp4 for ``free``-tier renders, else ``src``.

    Writes the new mp4 alongside ``src`` with a ``.watermarked.mp4``
    suffix so the original artifact is preserved (useful for upgrade
    flows where we want to re-emit the un-watermarked copy).
    """
    if tier != "free":
        return src

    out = work_dir / f"{src.stem}.watermarked.mp4"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    # Font handling: imageio-ffmpeg's bundled binary doesn't ship with
    # fontconfig configured, and the drawtext fontfile= option is too
    # fragile around Windows paths-with-spaces / drive-letter colons to
    # be worth threading through. The built-in default font (used when
    # no fontfile is passed) is plenty readable for a watermark.
    drawtext_parts = [
        f"text={_escape_filter_value(_WATERMARK_TEXT)}",
        "fontcolor=white@0.85",
        "fontsize=h*0.03",
        "borderw=2",
        "bordercolor=black@0.7",
        "x=w-tw-h*0.025",
        "y=h-th-h*0.025",
        "box=1",
        "boxcolor=black@0.35",
        "boxborderw=8",
    ]

    drawtext = ":".join(drawtext_parts)
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-i", str(src),
        "-vf", f"drawtext={drawtext}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(out),
    ]
    logger.info("watermark: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # Don't break the render over a failed watermark — log loudly,
        # return the original. Worse to ship no video than to ship one
        # without the watermark.
        logger.error(
            "watermark step failed (exit=%s): %s",
            proc.returncode, proc.stderr[-1500:],
        )
        return src
    if not out.exists() or out.stat().st_size < 1_000:
        logger.error("watermark output missing/tiny: %s", out)
        return src
    return out
