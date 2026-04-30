"""Posterization — reduce tonal range to enforce flat-shaded low-poly look.

Snaps colour values to discrete levels, producing banding that reinforces
the faceted aesthetic. Lighter than full palette quantization.
"""

from __future__ import annotations

import numpy as np


def posterize_frame(frame: np.ndarray, levels: int = 6) -> np.ndarray:
    """Posterize a single BGR frame to the given number of tonal levels."""
    if levels < 2:
        levels = 2
    divisor = 256.0 / levels
    return (np.floor(frame.astype(np.float32) / divisor) * divisor).astype(np.uint8)


def posterize_video(frames: list[np.ndarray], levels: int = 6) -> list[np.ndarray]:
    """Apply posterization to all frames."""
    return [posterize_frame(f, levels) for f in frames]
