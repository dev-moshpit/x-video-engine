"""Layout helpers shared by panel renderers.

Encapsulates three things every template needs:

  - **Safe zones** — top/bottom margins reserved for caption strips so
    panel content never bumps into burned ASS text.
  - **Auto-fit text** — wrap a string to a bounding box, shrinking the
    font in steps until it fits ``max_lines`` lines.
  - **Polished primitives** — rounded card with optional shadow,
    text-with-outline (readable on any bg), gradient backdrop.

These were previously inlined under ad-hoc helpers in
``_panels.py``. Pulling them out here lets every adapter use the
same visual grammar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont


# ─── Geometry ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SafeZone:
    """Reserved-from-caption-engine zone in pixels.

    ``top`` is the pixel offset reserved for status-bar / phone-frame
    UI elements; ``bottom`` is the pixel offset reserved for burned
    captions. Panels should keep all critical content between
    ``top`` and ``height - bottom``.
    """

    width: int
    height: int
    top: int
    bottom: int

    @property
    def safe_top(self) -> int:
        return self.top

    @property
    def safe_bottom(self) -> int:
        return self.height - self.bottom

    @property
    def safe_height(self) -> int:
        return self.height - self.top - self.bottom


def safe_zone_for(
    size: tuple[int, int],
    template_kind: str = "default",
) -> SafeZone:
    """Resolve safe-zone margins per template kind.

    The numbers below come from QA on a 576x1024 9:16 frame and the
    actual MarginV values used by ``caption_style_engine`` styles.
    """
    width, height = size
    if template_kind == "fake_text":
        # Phone-frame panel hugs the edges but the chat content sits
        # inside its own status bar; captions must stay below the
        # bottom dock.
        top = int(height * 0.04)
        bottom = int(height * 0.10)
    elif template_kind == "twitter":
        top = int(height * 0.08)
        bottom = int(height * 0.10)
    elif template_kind == "wyr":
        top = int(height * 0.04)
        bottom = int(height * 0.04)
    elif template_kind == "top_five":
        top = int(height * 0.07)
        bottom = int(height * 0.12)
    else:
        top = int(height * 0.06)
        bottom = int(height * 0.10)
    return SafeZone(width=width, height=height, top=top, bottom=bottom)


# ─── Color helpers ──────────────────────────────────────────────────────

def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def readable_fg(bg: tuple[int, int, int]) -> tuple[int, int, int]:
    """Pick a near-black or near-white text color for the given bg."""
    r, g, b = bg
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return (24, 24, 28) if lum > 160 else (245, 245, 247)


def shade(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    """``factor < 1`` darkens, ``factor > 1`` lightens. Clamps to 0-255."""
    return tuple(max(0, min(255, int(c * factor))) for c in rgb)


# ─── Text wrapping ──────────────────────────────────────────────────────

def wrap_to_width(
    text: str,
    *,
    font: ImageFont.ImageFont,
    max_w: int,
    draw: ImageDraw.ImageDraw,
) -> list[str]:
    """Greedy word-wrap to ``max_w``. Returns lines (>= 1)."""
    if not text:
        return [""]
    words = text.split()
    if not words:
        return [""]
    out: list[str] = []
    cur = words[0]
    for w in words[1:]:
        cand = f"{cur} {w}"
        if draw.textlength(cand, font=font) <= max_w:
            cur = cand
        else:
            out.append(cur)
            cur = w
    out.append(cur)
    return out


def auto_fit_text(
    text: str,
    *,
    draw: ImageDraw.ImageDraw,
    font_factory: Callable[[int], ImageFont.ImageFont],
    start_size: int,
    min_size: int,
    max_w: int,
    max_h: int,
    max_lines: int,
    line_height_ratio: float = 1.18,
) -> tuple[ImageFont.ImageFont, list[str], int]:
    """Pick the largest font from ``font_factory`` that fits ``text`` in the box.

    Shrinks in 2-px steps from ``start_size`` down to ``min_size``.
    Returns ``(font, lines, line_height)``.
    """
    size = max(start_size, min_size)
    while size >= min_size:
        font = font_factory(size)
        lines = wrap_to_width(text, font=font, max_w=max_w, draw=draw)
        line_h = int(size * line_height_ratio)
        block_h = len(lines) * line_h
        if len(lines) <= max_lines and block_h <= max_h:
            return font, lines, line_h
        size -= 2
    # Last resort — use min_size and clip to max_lines
    font = font_factory(min_size)
    lines = wrap_to_width(text, font=font, max_w=max_w, draw=draw)
    line_h = int(min_size * line_height_ratio)
    return font, lines[:max_lines], line_h


# ─── Drawing primitives ─────────────────────────────────────────────────

def rounded_card(
    base: Image.Image,
    *,
    bbox: tuple[int, int, int, int],
    fill: tuple[int, int, int],
    radius: int,
    shadow: bool = True,
    shadow_offset: tuple[int, int] = (0, 8),
    shadow_blur: int = 18,
    shadow_color: tuple[int, int, int, int] = (0, 0, 0, 110),
) -> None:
    """Draw a rounded card with an optional drop-shadow on ``base``.

    ``base`` must be an RGB or RGBA Pillow image; the function paints
    in place. Shadow is rendered as a separate alpha layer so the
    blur is real, not just a darker rectangle.
    """
    x0, y0, x1, y1 = bbox
    if shadow:
        # Blur a black rounded rect of the same shape, offset, paste
        # below the card.
        sw = x1 - x0 + shadow_blur * 2
        sh = y1 - y0 + shadow_blur * 2
        layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.rounded_rectangle(
            (shadow_blur, shadow_blur, shadow_blur + (x1 - x0), shadow_blur + (y1 - y0)),
            radius=radius,
            fill=shadow_color,
        )
        layer = layer.filter(ImageFilter.GaussianBlur(shadow_blur / 2))
        # Composite — base may be RGB; convert temporarily
        rgba = base.convert("RGBA")
        rgba.alpha_composite(
            layer,
            dest=(x0 - shadow_blur + shadow_offset[0], y0 - shadow_blur + shadow_offset[1]),
        )
        # paste the result back into base in-place
        base.paste(rgba.convert(base.mode))
    ImageDraw.Draw(base).rounded_rectangle(
        (x0, y0, x1, y1),
        radius=radius,
        fill=fill,
    )


def text_with_outline(
    draw: ImageDraw.ImageDraw,
    *,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    stroke_fill: tuple[int, int, int] = (0, 0, 0),
    stroke_width: int = 2,
) -> None:
    """Draw text with a black stroke for readability on busy backgrounds."""
    draw.text(
        xy, text, font=font, fill=fill,
        stroke_width=stroke_width, stroke_fill=stroke_fill,
    )


def draw_centered_in_bbox(
    draw: ImageDraw.ImageDraw,
    *,
    text: str,
    font: ImageFont.ImageFont,
    bbox: tuple[int, int, int, int],
    fill: tuple[int, int, int],
    line_h: int,
) -> None:
    """Wrap + draw ``text`` centered inside ``bbox``."""
    x0, y0, x1, y1 = bbox
    lines = wrap_to_width(text, font=font, max_w=x1 - x0, draw=draw)
    block_h = len(lines) * line_h
    y = y0 + max(0, ((y1 - y0) - block_h) // 2)
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text((x0 + ((x1 - x0) - w) // 2, y), line, font=font, fill=fill)
        y += line_h


# ─── Caption-zone reservation ───────────────────────────────────────────

@dataclass(frozen=True)
class CaptionPlacement:
    """Where a caption strip will sit, in pixel coordinates.

    Adapters use this to leave room for the burned ASS captions so
    panel content + captions don't overlap. ``y_baseline`` is the
    bottom of the caption block; ``height`` is the visual reserve
    above it.
    """

    style_id: str
    y_baseline: int
    height: int


def caption_placement(
    style: Optional[str], size: tuple[int, int],
) -> Optional[CaptionPlacement]:
    """Resolve caption placement from a style id, in our PlayResY=h frame."""
    if not style:
        return None
    width, height = size
    # MarginV percentages are mirrored from xvideo's caption_style_engine.
    margin = {
        "bold_word":          0.24,
        "kinetic_word":       0.22,
        "clean_subtitle":     0.06,
        "impact_uppercase":   0.30,
        "minimal_lower_third":0.05,
        "karaoke_3word":      0.22,
    }.get(style)
    height_ratio = {
        "bold_word":          0.10,
        "kinetic_word":       0.10,
        "clean_subtitle":     0.06,
        "impact_uppercase":   0.13,
        "minimal_lower_third":0.05,
        "karaoke_3word":      0.10,
    }.get(style, 0.10)
    if margin is None:
        return None
    y_baseline = height - int(height * margin)
    return CaptionPlacement(
        style_id=style,
        y_baseline=y_baseline,
        height=int(height * height_ratio),
    )
