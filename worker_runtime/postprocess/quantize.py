"""Palette quantization — reduce frame colours to enforce low-poly cohesion.

Applies k-means colour clustering per frame (or per window for temporal
consistency), then remaps pixels to the nearest cluster centre. This gives
a visible low-poly colour-blocking boost without any model complexity.
"""

from __future__ import annotations

import cv2
import numpy as np


def quantize_frame(
    frame: np.ndarray,
    n_colors: int = 8,
    iterations: int = 10,
) -> np.ndarray:
    """Quantize a single BGR frame to n_colors via k-means."""
    h, w = frame.shape[:2]
    pixels = frame.reshape(-1, 3).astype(np.float32)

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, iterations, 1.0)
    _, labels, centers = cv2.kmeans(
        pixels, n_colors, None, criteria, 3, cv2.KMEANS_PP_CENTERS,
    )
    quantized = centers[labels.flatten()].astype(np.uint8)
    return quantized.reshape(h, w, 3)


def quantize_video(
    frames: list[np.ndarray],
    n_colors: int = 8,
    temporal_lock: bool = True,
) -> list[np.ndarray]:
    """Quantize a sequence of frames.

    If temporal_lock is True, compute palette from the first frame and
    apply it to all frames (prevents palette flicker across the clip).
    If False, each frame gets its own k-means pass.
    """
    if not frames:
        return frames

    if temporal_lock:
        # Compute palette from first frame
        h, w = frames[0].shape[:2]
        pixels = frames[0].reshape(-1, 3).astype(np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, _, centers = cv2.kmeans(
            pixels, n_colors, None, criteria, 3, cv2.KMEANS_PP_CENTERS,
        )
        # Apply locked palette to all frames
        result = []
        for frame in frames:
            h, w = frame.shape[:2]
            px = frame.reshape(-1, 3).astype(np.float32)
            # Nearest-centre assignment
            dists = np.linalg.norm(px[:, None, :] - centers[None, :, :], axis=2)
            labels = np.argmin(dists, axis=1)
            quantized = centers[labels].astype(np.uint8).reshape(h, w, 3)
            result.append(quantized)
        return result
    else:
        return [quantize_frame(f, n_colors) for f in frames]
