"""Aspect-ratio reframe via FFmpeg — Phase 13.5.

Given a finished mp4 url and a target aspect, run a single ffmpeg
pass to crop+pad+scale to the canonical resolution for that aspect.
Used by the export-variant worker job; never called from the render
pipeline itself.

We treat the source as already-rendered (final output) — there is no
SDXL re-run, no plan re-execution, just a video remux. ``captions``
toggling is a no-op at this layer because the existing renders bake
captions into pixels; the field is propagated for future work that
re-runs caption compositing (Phase 14+).
"""

from __future__ import annotations

import logging
import subprocess
import urllib.request
import uuid
from pathlib import Path
from typing import Tuple

import imageio_ffmpeg


logger = logging.getLogger(__name__)


_TARGETS: dict[str, Tuple[int, int]] = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}

VALID_ASPECTS = tuple(_TARGETS.keys())


def _download(url: str, dst: Path) -> None:
    if url.startswith(("http://", "https://")):
        urllib.request.urlretrieve(url, dst)
        return
    src = Path(url)
    if src.exists():
        dst.write_bytes(src.read_bytes())
        return
    raise FileNotFoundError(f"could not resolve source: {url}")


def reframe_to_aspect(
    *,
    src_url: str,
    aspect: str,
    work_dir: Path,
) -> Path:
    """Reframe ``src_url`` (URL or local path) to the canonical size.

    The filter graph crops the largest centered region matching the
    target aspect and rescales to the canonical resolution. Audio is
    copied through.
    """
    if aspect not in _TARGETS:
        raise ValueError(f"unsupported aspect: {aspect}")

    work_dir.mkdir(parents=True, exist_ok=True)
    src_local = work_dir / f"src_{uuid.uuid4().hex[:8]}.mp4"
    _download(src_url, src_local)

    width, height = _TARGETS[aspect]
    out = work_dir / f"variant_{aspect.replace(':', 'x')}_{uuid.uuid4().hex[:8]}.mp4"

    # Filter graph:
    #   1. crop centered to the target aspect (max area that fits)
    #   2. scale to canonical pixels
    #   3. setsar=1 to avoid display-aspect surprises
    target_ar = width / height
    vf = (
        # ih*target_ar comes out wider than iw → fall back to ih.
        f"crop='min(iw,ih*{target_ar:.6f})':'min(ih,iw/{target_ar:.6f})',"
        f"scale={width}:{height},setsar=1"
    )

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-i", str(src_local),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(out),
    ]
    logger.info("reframe: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg reframe failed (exit={proc.returncode}): "
            f"{proc.stderr[-1500:]}"
        )
    if not out.exists() or out.stat().st_size < 1_000:
        raise RuntimeError("reframe output missing or tiny")
    return out
