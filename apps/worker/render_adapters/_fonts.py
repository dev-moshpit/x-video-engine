"""Font registry + glyph-aware rendering for worker panels.

Pillow loads ONE truetype face per ``ImageFont`` instance. Any glyph
the chosen face doesn't carry renders as the font's ``.notdef`` (an
empty rectangle). For Latin text under arialbd / Liberation Sans this
is fine — but when a panel pulls in an emoji or a Unicode arrow, the
single-font fallback breaks.

This module:

  - probes the host for usable ``text``, ``bold``, and ``emoji`` font
    files (Windows / macOS / Linux paths)
  - exposes a typed ``FontRole`` -> face cache so panel code can ask
    for ``role="display_bold"`` instead of pixel sizes
  - provides ``draw_text_safe`` which splits a string into runs of
    glyphs the chosen face supports vs runs the emoji fallback handles
    and draws each run in the right face.

We deliberately never bundle our own TTFs here — licensing risk is
real on a multi-tenant SaaS. The fallback chain is conservative and
caches the negative result for missing emoji fonts so worker boot
stays cheap.
"""

from __future__ import annotations

import logging
import platform
import warnings
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from PIL import ImageDraw, ImageFont


logger = logging.getLogger(__name__)


FontRole = Literal[
    "display_bold",   # huge headlines / impact captions
    "display_regular",
    "body_bold",      # tweet card name, panel titles
    "body_regular",   # tweet text, item titles
    "meta_bold",      # metric counts
    "meta_regular",   # handle, timestamps
]


# Face hierarchy per platform — first hit wins.
_WINDOWS_TEXT = [
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
]
_WINDOWS_BOLD = [
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\calibrib.ttf",
]
_WINDOWS_EMOJI = [
    r"C:\Windows\Fonts\seguiemj.ttf",
]

_LINUX_TEXT = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
]
_LINUX_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
_LINUX_EMOJI = [
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf",
]

_MACOS_TEXT = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/Library/Fonts/Arial.ttf",
]
_MACOS_BOLD = [
    "/System/Library/Fonts/HelveticaNeue.ttc",   # bold variant inside .ttc
    "/Library/Fonts/Arial Bold.ttf",
]
_MACOS_EMOJI = [
    "/System/Library/Fonts/Apple Color Emoji.ttc",
]


def _candidates(kind: Literal["text", "bold", "emoji"]) -> list[str]:
    sysname = platform.system()
    if sysname == "Windows":
        return {"text": _WINDOWS_TEXT, "bold": _WINDOWS_BOLD, "emoji": _WINDOWS_EMOJI}[kind]
    if sysname == "Darwin":
        return {"text": _MACOS_TEXT, "bold": _MACOS_BOLD, "emoji": _MACOS_EMOJI}[kind]
    return {"text": _LINUX_TEXT, "bold": _LINUX_BOLD, "emoji": _LINUX_EMOJI}[kind]


@lru_cache(maxsize=4)
def _resolve_face_path(kind: Literal["text", "bold", "emoji"]) -> Optional[str]:
    """First existing path for the kind, else None (emoji is best-effort)."""
    for p in _candidates(kind):
        if Path(p).exists():
            return p
    if kind == "emoji":
        return None  # ok — we just won't draw emoji glyphs
    return None


# Public role → (kind, default size) mapping. Sizes are at the
# canonical 480-px-wide reference frame; callers scale by the actual
# frame width.
_ROLE_DEFAULTS: dict[FontRole, tuple[Literal["text", "bold", "emoji"], int]] = {
    "display_bold":    ("bold", 220),
    "display_regular": ("text", 220),
    "body_bold":       ("bold", 32),
    "body_regular":    ("text", 32),
    "meta_bold":       ("bold", 18),
    "meta_regular":    ("text", 18),
}


@lru_cache(maxsize=128)
def _load(face_path: Optional[str], size: int) -> ImageFont.ImageFont:
    if face_path is None:
        # last-resort bitmap font; never crashes
        return ImageFont.load_default()
    try:
        return ImageFont.truetype(face_path, size=size)
    except Exception as exc:
        logger.warning("font load failed for %s @ %d: %s", face_path, size, exc)
        return ImageFont.load_default()


def get_font(
    role: FontRole = "body_regular",
    *,
    size: Optional[int] = None,
    scale: float = 1.0,
) -> ImageFont.ImageFont:
    """Return a Pillow font for the given semantic role.

    ``scale`` is the frame-width / 480 ratio that callers use to keep
    panels visually consistent across 9:16 / 16:9 / 1:1.
    """
    kind, default_px = _ROLE_DEFAULTS[role]
    px = int((size if size is not None else default_px) * scale)
    px = max(8, px)
    return _load(_resolve_face_path(kind), px)


def get_emoji_font(size: int) -> Optional[ImageFont.ImageFont]:
    """Return an emoji font face if the host carries one, else None."""
    p = _resolve_face_path("emoji")
    if p is None:
        return None
    return _load(p, size)


# Backward-compat shim — _font.py historically exposed ``load_font``.
def load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    """Backward-compatible factory used by older panel code."""
    return _load(_resolve_face_path("bold" if bold else "text"), size)


# ─── Glyph-aware text drawing ───────────────────────────────────────────


def _font_supports(font: ImageFont.ImageFont, ch: str) -> bool:
    """Best-effort check whether ``font`` carries the codepoint."""
    cmap = getattr(getattr(font, "font", None), "getbestcmap", None)
    if callable(cmap):
        try:
            return ord(ch) in cmap()
        except Exception:
            pass
    # PIL's bitmap fallback has no cmap — assume it supports basic ASCII.
    if isinstance(font, type(ImageFont.load_default())):
        return ord(ch) < 128
    # Truetype without getbestcmap — assume yes; .notdef will still draw
    # something, but at least we don't lose Latin glyphs.
    return True


def _split_runs(text: str, primary: ImageFont.ImageFont, fallback: Optional[ImageFont.ImageFont]):
    """Yield (run_text, font) pairs alternating primary / fallback by glyph support."""
    if not text:
        return
    if fallback is None:
        yield text, primary
        return
    cur = []
    cur_font = primary if _font_supports(primary, text[0]) else fallback
    for ch in text:
        wanted = primary if _font_supports(primary, ch) else fallback
        if wanted is cur_font:
            cur.append(ch)
        else:
            yield "".join(cur), cur_font
            cur = [ch]
            cur_font = wanted
    if cur:
        yield "".join(cur), cur_font


def text_length_safe(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    primary: ImageFont.ImageFont,
    emoji: Optional[ImageFont.ImageFont] = None,
) -> float:
    return sum(
        draw.textlength(run, font=font)
        for run, font in _split_runs(text, primary, emoji)
    )


def draw_text_safe(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    primary: ImageFont.ImageFont,
    emoji: Optional[ImageFont.ImageFont] = None,
    fill,
    stroke_width: int = 0,
    stroke_fill=None,
) -> float:
    """Draw ``text`` with per-glyph font fallback. Returns total width drawn.

    Splits ``text`` into runs that the primary face supports vs runs
    the emoji fallback supports and draws each run with the right
    face. When the emoji font is missing, runs that would have used it
    are silently dropped (better than ``.notdef`` rectangles).
    """
    x, y = xy
    drawn = 0.0
    for run, font in _split_runs(text, primary, emoji):
        if font is emoji and emoji is None:
            continue  # silently drop unsupported runs
        if stroke_width and stroke_fill is not None:
            draw.text((int(x + drawn), y), run, font=font, fill=fill,
                      stroke_width=stroke_width, stroke_fill=stroke_fill)
        else:
            draw.text((int(x + drawn), y), run, font=font, fill=fill)
        drawn += draw.textlength(run, font=font)
    return drawn


def has_emoji_font() -> bool:
    """True when the host has a usable emoji TTF cached."""
    return _resolve_face_path("emoji") is not None
