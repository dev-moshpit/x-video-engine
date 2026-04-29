"""Pillow panel renderers shared by Phase 2 viral templates.

Each function renders one full-frame PNG. Callers compose a timeline
of these (with per-beat durations) and feed it to
:mod:`apps.worker.render_adapters._overlay` for muxing.

Kept in one module so the visual language stays consistent across the
viral templates (rounded corners, padding scale, headline weights) —
when the design changes, it changes once here.

Layout primitives (auto-fit, rounded card with shadow, safe-zone
helpers) live in :mod:`apps.worker.render_adapters._layout` so they
can be reused by future template renderers without copy/paste.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw

from apps.worker.render_adapters._context import get_brand_color
from apps.worker.render_adapters._font import load_font
from apps.worker.render_adapters._fonts import (
    draw_text_safe,
    get_emoji_font,
    has_emoji_font,
    text_length_safe,
)
from apps.worker.render_adapters._layout import (
    auto_fit_text,
    draw_centered_in_bbox,
    hex_to_rgb,
    readable_fg,
    rounded_card,
    safe_zone_for,
    shade,
    text_with_outline,
    wrap_to_width,
)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Backwards-compatible alias kept for external callers."""
    return hex_to_rgb(hex_color)


def _readable_fg(bg: tuple[int, int, int]) -> tuple[int, int, int]:
    return readable_fg(bg)


def _wrap(text: str, font, max_w: int, draw: ImageDraw.ImageDraw) -> list[str]:
    return wrap_to_width(text, font=font, max_w=max_w, draw=draw)


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    *,
    text: str,
    font,
    bbox: tuple[int, int, int, int],
    fill: tuple[int, int, int],
    line_h: int,
) -> None:
    draw_centered_in_bbox(
        draw, text=text, font=font, bbox=bbox, fill=fill, line_h=line_h,
    )


# ─── Would You Rather ───────────────────────────────────────────────────

def render_wyr_panel(
    *,
    question: str,
    option_a: str,
    option_b: str,
    color_a: str,
    color_b: str,
    timer_label: str,
    pct_a: int | None,
    pct_b: int | None,
    size: tuple[int, int],
    out_path: Path,
) -> Path:
    """Render the WYR layout: question on top, two stacked option panels.

    ``timer_label`` is rendered between option A and B (e.g. "5", "OR").
    When ``pct_a`` / ``pct_b`` are non-None the percentage is overlaid on
    each panel — that's the reveal beat.
    """
    width, height = size
    scale = width / 480.0
    img = Image.new("RGB", size, color=(15, 15, 18))
    draw = ImageDraw.Draw(img)

    pad = int(28 * scale)
    title_font = load_font(int(36 * scale), bold=True)
    opt_font = load_font(int(40 * scale), bold=True)
    timer_font = load_font(int(48 * scale), bold=True)
    pct_font = load_font(int(56 * scale), bold=True)
    line_h_title = int(44 * scale)
    line_h_opt = int(48 * scale)

    title_h = int(160 * scale)
    timer_h = int(70 * scale)
    panel_h = (height - title_h - timer_h - pad * 2) // 2

    # Title block.
    _draw_centered(
        draw,
        text=question,
        font=title_font,
        bbox=(pad, pad, width - pad, pad + title_h),
        fill=(245, 245, 245),
        line_h=line_h_title,
    )

    # Panel A.
    a_bg = _hex_to_rgb(color_a)
    a_fg = _readable_fg(a_bg)
    a_top = pad + title_h
    draw.rounded_rectangle(
        (pad, a_top, width - pad, a_top + panel_h),
        radius=int(28 * scale), fill=a_bg,
    )
    _draw_centered(
        draw,
        text=option_a,
        font=opt_font,
        bbox=(pad * 2, a_top + pad, width - pad * 2, a_top + panel_h - pad),
        fill=a_fg,
        line_h=line_h_opt,
    )
    if pct_a is not None:
        pct_text = f"{pct_a}%"
        w = draw.textlength(pct_text, font=pct_font)
        draw.text(
            (width - pad * 2 - w, a_top + pad),
            pct_text, font=pct_font, fill=a_fg,
        )

    # Timer label between panels.
    timer_top = a_top + panel_h
    _draw_centered(
        draw,
        text=timer_label,
        font=timer_font,
        bbox=(pad, timer_top, width - pad, timer_top + timer_h),
        fill=(245, 245, 245),
        line_h=int(60 * scale),
    )

    # Panel B.
    b_bg = _hex_to_rgb(color_b)
    b_fg = _readable_fg(b_bg)
    b_top = timer_top + timer_h
    draw.rounded_rectangle(
        (pad, b_top, width - pad, b_top + panel_h),
        radius=int(28 * scale), fill=b_bg,
    )
    _draw_centered(
        draw,
        text=option_b,
        font=opt_font,
        bbox=(pad * 2, b_top + pad, width - pad * 2, b_top + panel_h - pad),
        fill=b_fg,
        line_h=line_h_opt,
    )
    if pct_b is not None:
        pct_text = f"{pct_b}%"
        w = draw.textlength(pct_text, font=pct_font)
        draw.text(
            (width - pad * 2 - w, b_top + pad),
            pct_text, font=pct_font, fill=b_fg,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG")
    return out_path


# ─── Twitter / X ────────────────────────────────────────────────────────

def _format_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def render_tweet_card(
    *,
    handle: str,
    display_name: str,
    text: str,
    likes: int,
    retweets: int,
    replies: int,
    views: int,
    verified: bool,
    dark_mode: bool,
    background_color: str,
    size: tuple[int, int],
    out_path: Path,
) -> Path:
    """Render a tweet card centered over a solid background."""
    width, height = size
    scale = width / 480.0
    safe = safe_zone_for(size, "twitter")
    # Phase 6 brand kit:
    #   - page bg uses accent_color when set, else the per-call value
    #   - the verified-check accent + avatar circle use brand_color
    bg = _hex_to_rgb(get_brand_color("accent_color", background_color))
    img = Image.new("RGB", size, color=bg)
    draw = ImageDraw.Draw(img)

    # Card colors per dark/light mode (tweet itself, not page bg).
    if dark_mode:
        card_bg = (21, 32, 43)
        text_fg = (217, 217, 217)
        meta_fg = (113, 118, 123)
    else:
        card_bg = (255, 255, 255)
        text_fg = (15, 20, 25)
        meta_fg = (83, 100, 113)
    accent = _hex_to_rgb(get_brand_color("brand_color", "#1da1f2"))

    # Card geometry — centered, ~85% of width, height auto-computed.
    card_pad = int(28 * scale)
    card_w = int(width * 0.86)
    card_x = (width - card_w) // 2

    name_font = load_font(int(28 * scale), bold=True)
    handle_font = load_font(int(24 * scale))
    text_font = load_font(int(32 * scale))
    meta_font = load_font(int(18 * scale), bold=True)
    emoji_font = get_emoji_font(int(18 * scale))

    # Wrap tweet text once for height calc.
    text_box_w = card_w - card_pad * 2
    lines = _wrap(text, text_font, text_box_w, draw)
    line_h = int(40 * scale)
    text_h = len(lines) * line_h

    header_h = int(80 * scale)
    metrics_h = int(60 * scale)
    card_h = card_pad + header_h + card_pad // 2 + text_h + card_pad + metrics_h

    # Center the card vertically within the safe zone (between status
    # bar reserve and burned caption reserve) so it never collides
    # with the caption strip.
    card_y = safe.safe_top + max(0, (safe.safe_height - card_h) // 2)
    rounded_card(
        img,
        bbox=(card_x, card_y, card_x + card_w, card_y + card_h),
        fill=card_bg,
        radius=int(20 * scale),
        shadow=True,
        shadow_offset=(0, int(10 * scale)),
        shadow_blur=int(22 * scale),
    )
    # rounded_card pastes its shadow composite back via ``Image.paste``
    # which can break the existing ImageDraw binding on the original
    # buffer; rebind so subsequent draw calls land on the same image.
    draw = ImageDraw.Draw(img)

    # Avatar circle (placeholder — accent ring + initial).
    avatar_size = int(70 * scale)
    av_x = card_x + card_pad
    av_y = card_y + card_pad
    draw.ellipse(
        (av_x, av_y, av_x + avatar_size, av_y + avatar_size),
        fill=accent,
    )
    initial = (display_name[:1] or handle[:1] or "?").upper()
    init_font = load_font(int(36 * scale), bold=True)
    iw = draw.textlength(initial, font=init_font)
    draw.text(
        (av_x + (avatar_size - iw) // 2, av_y + int(8 * scale)),
        initial, font=init_font, fill=(255, 255, 255),
    )

    # Name + handle.
    name_x = av_x + avatar_size + int(16 * scale)
    draw.text((name_x, av_y + int(4 * scale)), display_name,
              font=name_font, fill=text_fg)
    if verified:
        nw = draw.textlength(display_name, font=name_font)
        check_x = name_x + int(nw) + int(10 * scale)
        check_y = av_y + int(10 * scale)
        radius = int(14 * scale)
        cx = check_x + radius
        cy = check_y + radius
        draw.ellipse(
            (check_x, check_y, check_x + radius * 2, check_y + radius * 2),
            fill=accent,
        )
        # Polyline checkmark — Pillow falls back to .notdef for many
        # Unicode glyphs on Linux workers, so we draw the shape instead
        # of relying on the system font having ✓.
        check_w = max(2, int(3 * scale))
        draw.line(
            [
                (cx - radius // 2, cy + radius // 8),
                (cx - radius // 6, cy + radius // 2),
                (cx + radius // 2, cy - radius // 3),
            ],
            fill=(255, 255, 255),
            width=check_w,
        )
    handle_y = av_y + int(40 * scale)
    draw.text((name_x, handle_y), f"@{handle}",
              font=handle_font, fill=meta_fg)

    # Tweet text.
    text_y = card_y + card_pad + header_h + card_pad // 2
    for line in lines:
        draw.text((card_x + card_pad, text_y), line,
                  font=text_font, fill=text_fg)
        text_y += line_h

    # Metrics row. Avoids the 1F4AC/1F501/2764/1F4CA emoji codepoints
    # because Pillow loads a single TTF and falls back to .notdef for
    # any glyph the system Arial / Liberation Sans doesn't carry — the
    # screen would render as four empty boxes on a Linux worker. ♥ is in
    # the BMP and present in every common system font we fall back to.
    metrics_y = card_y + card_h - metrics_h + int(8 * scale)
    parts = [
        f"{_format_count(replies)} reply",
        f"{_format_count(retweets)} RT",
        f"{_format_count(likes)} ♥",
        f"{_format_count(views)} views",
    ]
    cell_w = (card_w - card_pad * 2) // 4
    for i, p in enumerate(parts):
        # Glyph-aware text — the emoji fallback only kicks in for runs
        # the primary face is missing (♥ is in Arial Bold so the
        # current label set never triggers it; future labels with real
        # emoji will route automatically).
        x = card_x + card_pad + i * cell_w
        draw_text_safe(
            draw, (x, metrics_y), p,
            primary=meta_font, emoji=emoji_font,
            fill=meta_fg,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG")
    return out_path


# ─── Top 5 / countdown ──────────────────────────────────────────────────

def render_top_five_panel(
    *,
    rank: int,
    rank_total: int,
    list_title: str,
    item_title: str,
    item_description: str | None,
    background_color: str,
    size: tuple[int, int],
    out_path: Path,
) -> Path:
    """Render one beat of a Top-N countdown.

    The brand kit (Phase 6) overrides:
      - background ←  ``accent_color`` if set
      - rank/title accent ←  ``brand_color`` if set
    Falls back to the per-call ``background_color`` + the default
    yellow accent when no kit is active.
    """
    width, height = size
    scale = width / 480.0
    safe = safe_zone_for(size, "top_five")
    bg = _hex_to_rgb(get_brand_color("accent_color", background_color))
    fg = _readable_fg(bg)
    accent = _hex_to_rgb(get_brand_color("brand_color", "#ffc400"))

    img = Image.new("RGB", size, color=bg)
    draw = ImageDraw.Draw(img)

    pad = int(36 * scale)
    rank_font = load_font(int(220 * scale), bold=True)
    item_font = load_font(int(46 * scale), bold=True)
    desc_font = load_font(int(28 * scale))

    # Header — list title (small, top). Auto-fit shrinks the font in
    # 2-px steps and wraps to up to two lines so long titles like
    # "Top 3 productivity hacks that actually work" aren't clipped at
    # the right edge.
    title_y = max(pad, safe.safe_top)
    title_max_h = int(80 * scale)
    title_font, title_lines, title_line_h = auto_fit_text(
        list_title.upper(),
        draw=draw,
        font_factory=lambda px: load_font(px, bold=True),
        start_size=int(30 * scale),
        min_size=int(18 * scale),
        max_w=width - pad * 2,
        max_h=title_max_h,
        max_lines=2,
        line_height_ratio=1.18,
    )
    for line in title_lines:
        draw.text((pad, title_y), line, font=title_font, fill=accent)
        title_y += title_line_h

    # Big rank number ("#3", "#2", "#1") centered slightly above midline.
    rank_text = f"#{rank}"
    rw = draw.textlength(rank_text, font=rank_font)
    rank_y = int(height * 0.18)
    draw.text(((width - rw) // 2, rank_y), rank_text,
              font=rank_font, fill=accent)

    # Item title under the rank.
    item_box_top = rank_y + int(240 * scale)
    item_lines = _wrap(item_title, item_font, width - pad * 2, draw)
    line_h_item = int(54 * scale)
    y = item_box_top
    for line in item_lines:
        w = draw.textlength(line, font=item_font)
        draw.text(((width - w) // 2, y), line, font=item_font, fill=fg)
        y += line_h_item

    # Description block (optional).
    if item_description:
        y += int(20 * scale)
        desc_lines = _wrap(item_description, desc_font, width - pad * 2, draw)
        line_h_desc = int(36 * scale)
        for line in desc_lines:
            w = draw.textlength(line, font=desc_font)
            draw.text(((width - w) // 2, y), line, font=desc_font, fill=fg)
            y += line_h_desc

    # Footer — "1 of 5" indicator.
    footer = f"{rank} of {rank_total}"
    footer_font = load_font(int(24 * scale), bold=True)
    fw = draw.textlength(footer, font=footer_font)
    draw.text(((width - fw) // 2, height - pad - int(28 * scale)),
              footer, font=footer_font, fill=accent)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG")
    return out_path


# ─── Solid color panel (used by roblox_rant when no bg upload) ─────────

def render_solid_panel(
    *, color: str, size: tuple[int, int], out_path: Path,
) -> Path:
    img = Image.new("RGB", size, color=_hex_to_rgb(color))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG")
    return out_path
