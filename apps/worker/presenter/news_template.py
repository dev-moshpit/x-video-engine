"""News-style lower-third + ticker overlay — Platform Phase 1.

Draw a translucent banner across the bottom third of the frame with a
headline + (optional) scrolling ticker. We render the banner once via
Pillow and overlay it through ffmpeg so the rest of the pipeline stays
single-pass.

The design is intentionally generic — we don't clone any specific
broadcaster's branding. Brand kits land here in a follow-up.
"""

from __future__ import annotations

import logging
import subprocess
import uuid
from pathlib import Path
from typing import Optional

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont


logger = logging.getLogger(__name__)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Try common system fonts; fall back to PIL's default bitmap font."""
    candidates = [
        "C:/Windows/Fonts/Arialbd.ttf",       # Windows
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVu-Sans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render_banner(
    *,
    width: int,
    height: int,
    headline: str,
    ticker: Optional[str],
    out_path: Path,
) -> Path:
    """Render the lower-third banner to a PNG with alpha."""
    banner = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(banner)

    panel_h = max(120, int(height * 0.22))
    panel_top = height - panel_h - max(40, int(height * 0.05))

    # Translucent dark panel
    draw.rectangle(
        [(0, panel_top), (width, panel_top + panel_h)],
        fill=(12, 16, 22, 220),
    )
    # Accent bar on the left
    accent_w = max(8, int(width * 0.012))
    draw.rectangle(
        [(0, panel_top), (accent_w, panel_top + panel_h)],
        fill=(225, 50, 50, 255),
    )

    headline_font = _load_font(int(panel_h * 0.36))
    pad_x = accent_w + max(20, int(width * 0.02))
    pad_y = max(12, int(panel_h * 0.10))
    draw.text(
        (pad_x, panel_top + pad_y),
        headline.upper()[:140],
        font=headline_font,
        fill=(255, 255, 255, 255),
    )

    if ticker:
        ticker_h = int(panel_h * 0.30)
        ticker_top = panel_top + panel_h - ticker_h
        draw.rectangle(
            [(0, ticker_top), (width, ticker_top + ticker_h)],
            fill=(225, 50, 50, 230),
        )
        ticker_font = _load_font(int(ticker_h * 0.55))
        draw.text(
            (pad_x, ticker_top + max(2, int(ticker_h * 0.18))),
            ticker[:200],
            font=ticker_font,
            fill=(255, 255, 255, 255),
        )

    banner.save(out_path)
    return out_path


def apply_news_template(
    *,
    src_video: Path,
    work_dir: Path,
    headline: str,
    ticker: Optional[str] = None,
    aspect: str = "9:16",
) -> Path:
    """Overlay a news-style lower-third on ``src_video``.

    The output is reframed to the canonical resolution for ``aspect``
    so callers don't need a separate reframe pass. ``headline`` is
    rendered once into a transparent PNG; ffmpeg overlays it via the
    ``overlay`` filter.
    """
    targets = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}
    if aspect not in targets:
        raise ValueError(f"unsupported aspect: {aspect}")
    width, height = targets[aspect]
    work_dir.mkdir(parents=True, exist_ok=True)

    banner = _render_banner(
        width=width, height=height,
        headline=headline,
        ticker=ticker,
        out_path=work_dir / f"banner_{uuid.uuid4().hex[:8]}.png",
    )

    out = work_dir / f"presenter_news_{uuid.uuid4().hex[:8]}.mp4"
    target_ar = width / height
    vf = (
        f"[0:v]crop='min(iw,ih*{target_ar:.6f})':'min(ih,iw/{target_ar:.6f})',"
        f"scale={width}:{height},setsar=1[v];"
        f"[v][1:v]overlay=0:0[outv]"
    )

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-hide_banner", "-y",
        "-i", str(src_video),
        "-i", str(banner),
        "-filter_complex", vf,
        "-map", "[outv]",
        "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out),
    ]
    logger.info("news_template: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"news template overlay failed (exit={proc.returncode}): "
            f"{proc.stderr[-1500:]}"
        )
    if not out.exists() or out.stat().st_size < 1_000:
        raise RuntimeError("news template produced empty mp4")
    return out
