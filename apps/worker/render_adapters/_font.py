"""Font loading with graceful cross-platform fallback.

Phase 2 adapters (fake_text, twitter, would_you_rather, top_five) burn
text into PNG frames via Pillow. We need a TrueType font that exists on
Windows (dev), Linux (prod worker), and macOS (occasional dev). We do
NOT bundle fonts to avoid licensing issues — instead we probe the
common system paths and fall back to PIL's built-in pixel font as a
last resort so rendering never crashes.
"""

from __future__ import annotations

import platform
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont


_WINDOWS_FONTS = [
    r"C:\Windows\Fonts\seguiemj.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
]

_LINUX_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
]

_MACOS_FONTS = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/Library/Fonts/Arial.ttf",
]


def _candidate_paths(want_bold: bool) -> list[str]:
    sys = platform.system()
    if sys == "Windows":
        if want_bold:
            return [
                r"C:\Windows\Fonts\arialbd.ttf",
                r"C:\Windows\Fonts\segoeuib.ttf",
            ] + _WINDOWS_FONTS
        return _WINDOWS_FONTS
    if sys == "Darwin":
        return _MACOS_FONTS
    return _LINUX_FONTS


@lru_cache(maxsize=64)
def load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    """Return a TTF font of the requested pixel size, or PIL's default.

    Cached because PIL ``truetype`` font construction is non-trivial —
    chat-frame rendering loads the same sizes thousands of times.
    """
    for path in _candidate_paths(want_bold=bold):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    # Last-resort: PIL's built-in 8 px bitmap. Looks bad at large sizes
    # but always renders — chat frames stay legible.
    return ImageFont.load_default()
