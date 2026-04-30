"""Post-processing pipeline — toggleable per-pass processing chain.

Each pass is controlled by config flags. The pipeline reads frames from
a video, applies enabled passes in order, and writes the result.

Pass order:
  1. palette_quantize  — enforce colour cohesion
  2. posterize         — reduce tonal banding
  3. edge_sharpen      — enhance facet edges

All passes are image-level and run on CPU. No model inference.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .edges import sharpen_video
from .posterize import posterize_video
from .quantize import quantize_video

logger = logging.getLogger(__name__)


@dataclass
class PostprocessConfig:
    """Toggleable post-processing passes."""
    enabled: bool = False
    palette_quantize: bool = False
    quantize_colors: int = 8
    quantize_temporal_lock: bool = True
    posterize: bool = False
    posterize_levels: int = 6
    edge_sharpen: bool = False
    edge_boost: float = 0.3


def _read_video(path: str) -> tuple[list[np.ndarray], float, tuple[int, int]]:
    """Read all frames from a video file. Returns (frames, fps, (w, h))."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    return frames, fps, (w, h)


def _write_video(
    path: str,
    frames: list[np.ndarray],
    fps: float,
    size: tuple[int, int],
) -> None:
    """Write frames to an mp4 file."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, size)
    for frame in frames:
        writer.write(frame)
    writer.release()


def run_postprocess(
    input_path: str,
    output_path: str | None = None,
    config: PostprocessConfig | None = None,
) -> str:
    """Run the post-processing pipeline on a video file.

    Args:
        input_path: Path to input .mp4.
        output_path: Path for output .mp4. If None, overwrites input.
        config: Post-processing settings. If None, uses defaults (all off).

    Returns:
        Path to the output video.
    """
    cfg = config or PostprocessConfig()
    if not cfg.enabled:
        logger.debug("Postprocess disabled; skipping")
        return input_path

    out = output_path or input_path
    frames, fps, (w, h) = _read_video(input_path)
    if not frames:
        logger.warning("No frames read from %s; skipping postprocess", input_path)
        return input_path

    logger.info(
        "Postprocessing %d frames: quantize=%s posterize=%s sharpen=%s",
        len(frames), cfg.palette_quantize, cfg.posterize, cfg.edge_sharpen,
    )

    # Pass 1: palette quantization
    if cfg.palette_quantize:
        frames = quantize_video(
            frames,
            n_colors=cfg.quantize_colors,
            temporal_lock=cfg.quantize_temporal_lock,
        )

    # Pass 2: posterize
    if cfg.posterize:
        frames = posterize_video(frames, levels=cfg.posterize_levels)

    # Pass 3: edge sharpen
    if cfg.edge_sharpen:
        frames = sharpen_video(frames, edge_boost=cfg.edge_boost)

    _write_video(out, frames, fps, (w, h))
    logger.info("Postprocessed video written to %s", out)
    return out
