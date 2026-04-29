"""Caption-style helper for worker render adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from xvideo.prompt_native.caption_style_engine import build_caption_file


def write_caption_file(
    *,
    words: Iterable,
    out_path: Path,
    style: str | None,
    size: tuple[int, int],
    default_style: str = "bold_word",
) -> Path:
    """Write an ASS caption file using the selected production style.

    The engine emits ``WrapStyle: 2`` (no wrap, only manual ``\\N``) which
    means a long ``clean_subtitle`` line — the engine packs 7 words per
    event — overflows the 9:16 frame width and gets clipped at the
    edges. We post-process the file to flip ``WrapStyle`` to ``0``
    (smart wrap), letting libass break overlong lines on the
    ``MarginL/MarginR`` budget. We don't touch ``xvideo/``.
    """
    chosen = style or default_style
    path = build_caption_file(
        style=chosen,
        words=words,
        out_path=out_path,
        video_width=size[0],
        video_height=size[1],
    )
    try:
        text = path.read_text(encoding="utf-8")
        if "WrapStyle: 2" in text:
            path.write_text(text.replace("WrapStyle: 2", "WrapStyle: 0"), encoding="utf-8")
    except OSError:
        # Caption file isn't readable post-write — leave it; libass
        # will still render with the engine default.
        pass
    return path
