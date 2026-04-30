"""2.5D parallax animation — turn a still into a 2-5s vertical video.

Ken Burns + parallax variants. Each function returns a list of frames
(numpy BGR arrays) ready for the postprocess pipeline and ffmpeg.

Animation modes:
  - zoom_in:   slow dolly in, center fixed
  - zoom_out:  slow dolly out from tight crop
  - orbit:     small arc pan (fake orbit)
  - pan_left / pan_right: horizontal camera pan
  - ken_burns: zoom + pan combined (most cinematic for Shorts)
"""

from __future__ import annotations

import math
from typing import Literal

import cv2
import numpy as np

AnimMode = Literal["zoom_in", "zoom_out", "orbit", "pan_left", "pan_right", "ken_burns"]


def _ease_in_out(t: float) -> float:
    """Smooth ease for cinematic camera feel."""
    return t * t * (3.0 - 2.0 * t)


def animate_still(
    image: np.ndarray,
    mode: AnimMode = "ken_burns",
    duration_sec: float = 3.0,
    fps: int = 24,
    out_size: tuple[int, int] = (576, 1024),  # 9:16 for Shorts
    zoom_range: tuple[float, float] = (1.0, 1.25),
    pan_fraction: float = 0.15,
) -> list[np.ndarray]:
    """Animate a still image into a sequence of frames.

    Args:
        image: input BGR image (will be upscaled if smaller than out_size).
        mode: animation style.
        duration_sec: output clip length.
        fps: output frame rate.
        out_size: (width, height) of output frames (9:16 for Shorts by default).
        zoom_range: (start_scale, end_scale) relative to the base crop.
        pan_fraction: max fraction of image width/height to pan.

    Returns:
        List of BGR frames, ready for video writing.
    """
    out_w, out_h = out_size
    src_h, src_w = image.shape[:2]
    n_frames = int(duration_sec * fps)
    if n_frames < 1:
        n_frames = 1

    # Upscale source if needed so we can always crop a large-enough window
    # even at max zoom. We need source >= out_size * max_zoom.
    max_zoom = max(zoom_range)
    need_w = int(out_w * max_zoom * 1.3)  # extra margin for pan
    need_h = int(out_h * max_zoom * 1.3)
    if src_w < need_w or src_h < need_h:
        scale = max(need_w / src_w, need_h / src_h)
        new_w = int(src_w * scale)
        new_h = int(src_h * scale)
        image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
        src_h, src_w = image.shape[:2]

    frames: list[np.ndarray] = []
    for i in range(n_frames):
        t = i / max(n_frames - 1, 1)
        te = _ease_in_out(t)

        # Determine this frame's zoom and (cx, cy) center on the source image
        if mode == "zoom_in":
            zoom = zoom_range[0] + (zoom_range[1] - zoom_range[0]) * te
            cx, cy = src_w // 2, src_h // 2
        elif mode == "zoom_out":
            zoom = zoom_range[1] - (zoom_range[1] - zoom_range[0]) * te
            cx, cy = src_w // 2, src_h // 2
        elif mode == "pan_left":
            zoom = 1.0 + (zoom_range[1] - 1.0) * 0.5
            px = src_w // 2 + int(src_w * pan_fraction * (0.5 - te))
            cx, cy = px, src_h // 2
        elif mode == "pan_right":
            zoom = 1.0 + (zoom_range[1] - 1.0) * 0.5
            px = src_w // 2 + int(src_w * pan_fraction * (te - 0.5))
            cx, cy = px, src_h // 2
        elif mode == "orbit":
            # Small arc: pan horizontally + slight zoom oscillation
            zoom = zoom_range[0] + (zoom_range[1] - zoom_range[0]) * 0.5 * (1 + math.sin(te * math.pi))
            px = src_w // 2 + int(src_w * pan_fraction * math.sin(te * 2 * math.pi))
            cx, cy = px, src_h // 2
        elif mode == "ken_burns":
            zoom = zoom_range[0] + (zoom_range[1] - zoom_range[0]) * te
            px = src_w // 2 + int(src_w * pan_fraction * (te - 0.5))
            py = src_h // 2 + int(src_h * pan_fraction * 0.3 * (te - 0.5))
            cx, cy = px, py
        else:
            zoom = 1.0
            cx, cy = src_w // 2, src_h // 2

        # Crop a region of size (out_w*zoom, out_h*zoom) centered on (cx,cy)
        crop_w = int(out_w * zoom)
        crop_h = int(out_h * zoom)
        x0 = max(0, min(cx - crop_w // 2, src_w - crop_w))
        y0 = max(0, min(cy - crop_h // 2, src_h - crop_h))
        crop = image[y0:y0 + crop_h, x0:x0 + crop_w]

        # Resize back to output size
        frame = cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
        frames.append(frame)

    return frames


def write_video(
    frames: list[np.ndarray],
    out_path: str,
    fps: int = 24,
) -> str:
    """Write frames to an mp4 via OpenCV."""
    if not frames:
        raise ValueError("No frames to write")
    h, w = frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(out_path, fourcc, fps, (w, h))
    for frame in frames:
        writer.write(frame)
    writer.release()
    return out_path
