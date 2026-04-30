"""Edge-aware sharpening — enhance facet edges in low-poly video frames.

Uses bilateral filtering to smooth flat regions while preserving edges,
then optionally overlays detected edges for a sharper faceted look.
"""

from __future__ import annotations

import cv2
import numpy as np


def sharpen_facets(
    frame: np.ndarray,
    d: int = 9,
    sigma_color: float = 75.0,
    sigma_space: float = 75.0,
    edge_boost: float = 0.3,
) -> np.ndarray:
    """Bilateral filter + edge overlay for a single BGR frame.

    Args:
        d: Diameter of pixel neighbourhood for bilateral filter.
        sigma_color: Filter sigma in the colour space.
        sigma_space: Filter sigma in the coordinate space.
        edge_boost: Strength of edge overlay (0 = none, 1 = full).
    """
    # Bilateral: smooth flat areas, keep edges sharp
    smooth = cv2.bilateralFilter(frame, d, sigma_color, sigma_space)

    if edge_boost <= 0:
        return smooth

    # Detect edges and blend them in
    gray = cv2.cvtColor(smooth, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 150)
    # Dilate slightly for visible edge lines
    kernel = np.ones((2, 2), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=1)

    # Darken pixels on edges to emphasise facet boundaries
    edge_mask = edges.astype(np.float32) / 255.0
    result = smooth.astype(np.float32)
    for c in range(3):
        result[:, :, c] *= (1.0 - edge_boost * edge_mask)
    return np.clip(result, 0, 255).astype(np.uint8)


def sharpen_video(
    frames: list[np.ndarray],
    edge_boost: float = 0.3,
) -> list[np.ndarray]:
    """Apply facet sharpening to all frames."""
    return [sharpen_facets(f, edge_boost=edge_boost) for f in frames]
