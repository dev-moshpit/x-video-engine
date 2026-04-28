"""Chat-frame rendering for the Fake Text generator.

Renders iOS / WhatsApp / Instagram / Tinder-style chat screens to PNG
via Pillow. Two responsibilities:

  1. ``ChatStyle`` — color/spacing tokens per platform + theme.
  2. ``render_chat_frame`` — given a list of (sender, text) messages
     and an optional "typing" beat at the end, draw the screen with
     rounded message bubbles, a header bar, and (optionally) a typing
     indicator. Returns nothing — writes PNG to ``out_path``.

Why all-Pillow + ffmpeg-concat (instead of HTML→PNG via Playwright):
  - no headless browser dependency on the GPU worker
  - frames stream into the existing ffmpeg post-stack with no detour
  - pure Python = stays trivial to test on the CPU-only api host too

Layout simplifications vs. real apps:
  - no avatars yet (Phase 2.5 media library will add image fetch)
  - no message timestamps under bubbles
  - no read-receipts ticks (keep blast radius small)
  - typing dots are static three-dot glyph, not animated frame-by-frame
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw

from apps.worker.render_adapters._font import load_font


Sender = Literal["me", "them"]
StyleId = Literal["ios", "whatsapp", "instagram", "tinder"]
ThemeId = Literal["light", "dark"]


@dataclass(frozen=True)
class ChatStyle:
    """Color + sizing tokens for one (platform, theme) combo."""
    bg: tuple[int, int, int]
    header_bg: tuple[int, int, int]
    header_fg: tuple[int, int, int]
    me_bubble: tuple[int, int, int]
    me_fg: tuple[int, int, int]
    them_bubble: tuple[int, int, int]
    them_fg: tuple[int, int, int]
    typing_bubble: tuple[int, int, int]
    typing_fg: tuple[int, int, int]


_PALETTE: dict[tuple[StyleId, ThemeId], ChatStyle] = {
    ("ios", "light"): ChatStyle(
        bg=(255, 255, 255),
        header_bg=(247, 247, 247), header_fg=(20, 20, 20),
        me_bubble=(0, 122, 255),   me_fg=(255, 255, 255),
        them_bubble=(229, 229, 234), them_fg=(20, 20, 20),
        typing_bubble=(229, 229, 234), typing_fg=(120, 120, 120),
    ),
    ("ios", "dark"): ChatStyle(
        bg=(0, 0, 0),
        header_bg=(28, 28, 30), header_fg=(255, 255, 255),
        me_bubble=(10, 132, 255), me_fg=(255, 255, 255),
        them_bubble=(38, 38, 40), them_fg=(255, 255, 255),
        typing_bubble=(38, 38, 40), typing_fg=(170, 170, 170),
    ),
    ("whatsapp", "light"): ChatStyle(
        bg=(236, 229, 221),
        header_bg=(7, 94, 84), header_fg=(255, 255, 255),
        me_bubble=(220, 248, 198), me_fg=(20, 20, 20),
        them_bubble=(255, 255, 255), them_fg=(20, 20, 20),
        typing_bubble=(255, 255, 255), typing_fg=(120, 120, 120),
    ),
    ("whatsapp", "dark"): ChatStyle(
        bg=(11, 20, 26),
        header_bg=(31, 44, 51), header_fg=(233, 237, 239),
        me_bubble=(0, 92, 75), me_fg=(233, 237, 239),
        them_bubble=(32, 44, 51), them_fg=(233, 237, 239),
        typing_bubble=(32, 44, 51), typing_fg=(140, 150, 156),
    ),
    ("instagram", "light"): ChatStyle(
        bg=(255, 255, 255),
        header_bg=(255, 255, 255), header_fg=(20, 20, 20),
        me_bubble=(56, 151, 240), me_fg=(255, 255, 255),
        them_bubble=(239, 239, 239), them_fg=(20, 20, 20),
        typing_bubble=(239, 239, 239), typing_fg=(120, 120, 120),
    ),
    ("instagram", "dark"): ChatStyle(
        bg=(0, 0, 0),
        header_bg=(0, 0, 0), header_fg=(255, 255, 255),
        me_bubble=(56, 151, 240), me_fg=(255, 255, 255),
        them_bubble=(38, 38, 38), them_fg=(255, 255, 255),
        typing_bubble=(38, 38, 38), typing_fg=(170, 170, 170),
    ),
    ("tinder", "light"): ChatStyle(
        bg=(255, 255, 255),
        header_bg=(255, 255, 255), header_fg=(20, 20, 20),
        me_bubble=(253, 41, 123), me_fg=(255, 255, 255),
        them_bubble=(238, 238, 238), them_fg=(20, 20, 20),
        typing_bubble=(238, 238, 238), typing_fg=(120, 120, 120),
    ),
    ("tinder", "dark"): ChatStyle(
        bg=(20, 20, 20),
        header_bg=(20, 20, 20), header_fg=(253, 41, 123),
        me_bubble=(253, 41, 123), me_fg=(255, 255, 255),
        them_bubble=(48, 48, 48), them_fg=(255, 255, 255),
        typing_bubble=(48, 48, 48), typing_fg=(170, 170, 170),
    ),
}


def get_chat_style(style: StyleId, theme: ThemeId) -> ChatStyle:
    return _PALETTE.get((style, theme)) or _PALETTE[("ios", "light")]


# ─── Layout primitives ──────────────────────────────────────────────────

def _wrap_text(
    text: str, font, max_width: int, draw: ImageDraw.ImageDraw,
) -> list[str]:
    """Greedy word-wrap honoring ``max_width`` in pixels."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = words[0]
    for w in words[1:]:
        candidate = f"{cur} {w}"
        if draw.textlength(candidate, font=font) <= max_width:
            cur = candidate
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def _draw_bubble(
    draw: ImageDraw.ImageDraw,
    *,
    box: tuple[int, int, int, int],
    fill: tuple[int, int, int],
    radius: int,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def _measure_message_height(
    text: str, font, max_text_w: int, line_h: int,
    bubble_pad_y: int, draw: ImageDraw.ImageDraw,
) -> tuple[int, list[str]]:
    lines = _wrap_text(text, font, max_text_w, draw)
    height = len(lines) * line_h + bubble_pad_y * 2
    return height, lines


# ─── Public renderer ────────────────────────────────────────────────────

def render_chat_frame(
    *,
    style: StyleId,
    theme: ThemeId,
    chat_title: str,
    visible: list[tuple[Sender, str]],
    typing: Sender | None,
    size: tuple[int, int],
    out_path: Path,
) -> Path:
    """Render one chat screen.

    ``visible`` are messages already on screen, oldest first. ``typing``
    is which side is currently typing (or None for no indicator). The
    most recent messages are pinned to the bottom of the chat area —
    when more messages arrive than fit, the oldest scroll off the top.
    """
    width, height = size
    palette = get_chat_style(style, theme)

    img = Image.new("RGB", size, color=palette.bg)
    draw = ImageDraw.Draw(img)

    # Sizing — scaled relative to width so 9:16 (576×1024) and 1:1
    # (768×768) both look balanced.
    scale = max(width / 480.0, 0.7)
    header_h = int(86 * scale)
    msg_font = load_font(int(28 * scale))
    title_font = load_font(int(30 * scale), bold=True)
    bubble_radius = int(22 * scale)
    bubble_pad_x = int(18 * scale)
    bubble_pad_y = int(12 * scale)
    edge_margin = int(20 * scale)
    gap_between = int(10 * scale)
    max_bubble_w = int((width - edge_margin * 2) * 0.74)
    max_text_w = max_bubble_w - bubble_pad_x * 2
    line_h = int(34 * scale)

    # Header bar.
    draw.rectangle((0, 0, width, header_h), fill=palette.header_bg)
    title_w = draw.textlength(chat_title, font=title_font)
    draw.text(
        ((width - title_w) // 2, header_h // 2 - line_h // 2),
        chat_title,
        font=title_font,
        fill=palette.header_fg,
    )
    # Subtle divider under header.
    draw.line(
        ((0, header_h), (width, header_h)),
        fill=tuple(max(c - 25, 0) for c in palette.header_bg),
        width=1,
    )

    # Pre-measure all visible messages + the typing bubble so we can
    # bottom-anchor the stack and crop oldest if it overflows.
    measured: list[tuple[Sender, str, int, list[str]]] = []
    for sender, text in visible:
        h, lines = _measure_message_height(
            text, msg_font, max_text_w, line_h, bubble_pad_y, draw,
        )
        measured.append((sender, text, h, lines))

    typing_h = 0
    if typing is not None:
        typing_h = bubble_pad_y * 2 + line_h

    chat_top = header_h + edge_margin
    chat_bottom = height - edge_margin
    available_h = chat_bottom - chat_top

    total_h = sum(h + gap_between for _s, _t, h, _l in measured)
    total_h += (typing_h + gap_between) if typing else 0

    # Drop oldest until everything fits.
    while measured and total_h > available_h:
        _s, _t, h, _l = measured.pop(0)
        total_h -= h + gap_between

    # Anchor stack to bottom of chat area.
    y = chat_bottom - total_h + gap_between

    for sender, _text, h, lines in measured:
        bubble_w = (
            max(int(draw.textlength(line, font=msg_font)) for line in lines)
            + bubble_pad_x * 2
        )
        bubble_w = min(bubble_w, max_bubble_w)

        if sender == "me":
            x_right = width - edge_margin
            x_left = x_right - bubble_w
            fill = palette.me_bubble
            text_fill = palette.me_fg
        else:
            x_left = edge_margin
            x_right = x_left + bubble_w
            fill = palette.them_bubble
            text_fill = palette.them_fg

        _draw_bubble(draw, box=(x_left, y, x_right, y + h),
                     fill=fill, radius=bubble_radius)

        ty = y + bubble_pad_y
        for line in lines:
            tx = x_left + bubble_pad_x
            draw.text((tx, ty), line, font=msg_font, fill=text_fill)
            ty += line_h
        y += h + gap_between

    if typing is not None:
        dots = "• • •"
        bubble_w = int(draw.textlength(dots, font=msg_font)) + bubble_pad_x * 2
        if typing == "me":
            x_right = width - edge_margin
            x_left = x_right - bubble_w
        else:
            x_left = edge_margin
            x_right = x_left + bubble_w
        _draw_bubble(
            draw,
            box=(x_left, y, x_right, y + typing_h),
            fill=palette.typing_bubble,
            radius=bubble_radius,
        )
        draw.text(
            (x_left + bubble_pad_x, y + bubble_pad_y),
            dots, font=msg_font, fill=palette.typing_fg,
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG")
    return out_path
