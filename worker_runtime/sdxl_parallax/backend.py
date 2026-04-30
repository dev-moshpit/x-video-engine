"""SDXL-Turbo + parallax backend — laptop-friendly Shorts generator.

Keeps the pipeline warm in memory across calls. Exposes a single
`generate()` function that takes a prompt and returns an mp4 path.
"""

from __future__ import annotations

import gc
import logging
import os
import time
from pathlib import Path
from typing import Literal, Optional

import numpy as np

from .parallax import AnimMode, animate_still, write_video

logger = logging.getLogger(__name__)

# Suppress symlink warnings on Windows
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


class SDXLParallaxBackend:
    """SDXL-Turbo + parallax. Keeps pipeline warm for throughput."""

    def __init__(
        self,
        model_id: str = "stabilityai/sdxl-turbo",
        image_size: int = 512,
        variant: Optional[str] = "fp16",
    ):
        self.model_id = model_id
        self.image_size = image_size
        self.variant = variant
        self._pipe = None

    def load(self):
        """Lazy-load the SDXL pipeline with CPU offload."""
        if self._pipe is not None:
            return self._pipe

        import torch
        from diffusers import AutoPipelineForText2Image

        t0 = time.time()
        logger.info("Loading %s (variant=%s, fp16)", self.model_id, self.variant)
        kwargs = {"torch_dtype": torch.float16}
        if self.variant:
            kwargs["variant"] = self.variant
        pipe = AutoPipelineForText2Image.from_pretrained(self.model_id, **kwargs)
        pipe.enable_model_cpu_offload()

        # Optional: disable the internal progress bar for cleaner logs
        try:
            pipe.set_progress_bar_config(disable=True)
        except Exception:
            pass

        self._pipe = pipe
        logger.info("Pipeline ready in %.1fs", time.time() - t0)
        return pipe

    def generate_image(
        self,
        prompt: str,
        negative_prompt: str = "",
        seed: int = 42,
        steps: int = 2,
        guidance: float = 0.0,
    ) -> np.ndarray:
        """Generate one BGR image via SDXL-Turbo."""
        import cv2
        import torch

        pipe = self.load()
        generator = torch.Generator(device="cpu").manual_seed(seed)

        t0 = time.time()
        image = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt or None,
            num_inference_steps=steps,
            guidance_scale=guidance,
            height=self.image_size,
            width=self.image_size,
            generator=generator,
        ).images[0]
        logger.info("SDXL generation in %.1fs", time.time() - t0)

        # PIL RGB → cv2 BGR
        bgr = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        return bgr

    def generate_video(
        self,
        prompt: str,
        out_path: str,
        negative_prompt: str = "",
        seed: int = 42,
        duration_sec: float = 3.0,
        fps: int = 24,
        aspect_ratio: Literal["9:16", "16:9", "1:1"] = "9:16",
        anim_mode: AnimMode = "ken_burns",
        zoom_range: tuple[float, float] = (1.0, 1.25),
        steps: int = 2,
        guidance: float = 0.0,
    ) -> dict:
        """Full pipeline: prompt → image → parallax → mp4.

        Returns a dict with timing breakdown and output path.
        """
        timings = {}
        t_total = time.time()

        # 1. Generate still
        t0 = time.time()
        image = self.generate_image(prompt, negative_prompt, seed, steps, guidance)
        timings["image_gen_sec"] = round(time.time() - t0, 2)

        # 2. Decide output size by aspect ratio
        if aspect_ratio == "9:16":
            out_size = (576, 1024)
        elif aspect_ratio == "16:9":
            out_size = (1024, 576)
        else:
            out_size = (768, 768)

        # 3. Animate
        t1 = time.time()
        frames = animate_still(
            image,
            mode=anim_mode,
            duration_sec=duration_sec,
            fps=fps,
            out_size=out_size,
            zoom_range=zoom_range,
        )
        timings["animate_sec"] = round(time.time() - t1, 2)

        # 4. Write video
        t2 = time.time()
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        write_video(frames, out_path, fps=fps)
        timings["write_sec"] = round(time.time() - t2, 2)

        timings["total_sec"] = round(time.time() - t_total, 2)
        timings["n_frames"] = len(frames)

        return {
            "video_path": out_path,
            "timings": timings,
            "width": out_size[0],
            "height": out_size[1],
        }

    def unload(self):
        if self._pipe is not None:
            del self._pipe
            self._pipe = None
        gc.collect()
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass
