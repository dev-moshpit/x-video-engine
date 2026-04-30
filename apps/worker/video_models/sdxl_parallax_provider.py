"""SDXL parallax provider — Platform Phase 1.

Wraps the existing ``worker_runtime.sdxl_parallax.SDXLParallaxBackend``
under the new VideoModelProvider contract. This is the always-available
"lightweight" path — when other models (Wan, Hunyuan, CogVideoX, SVD)
aren't installed, the user can still generate via SDXL stills with a
2.5D parallax animation pass.

We intentionally don't auto-pick this when the user requested another
model. The api surfaces the disabled state of unavailable models so
the operator picks an installed alternative explicitly.
"""

from __future__ import annotations

import importlib.util
import logging
import math
from pathlib import Path
from typing import Optional

from apps.worker.video_models.base import (
    GenerationRequest,
    ModelNotAvailable,
    ProviderInfo,
)


logger = logging.getLogger(__name__)


_PROVIDER_ID = "sdxl_parallax"


def _info(installed: bool, error: Optional[str] = None) -> ProviderInfo:
    return ProviderInfo(
        id=_PROVIDER_ID,
        name="SDXL Parallax (lightweight)",
        mode="text-to-video",
        required_vram_gb=4.0,
        installed=installed,
        install_hint=(
            "pip install diffusers transformers torch torchvision; "
            "huggingface-cli download stabilityai/sdxl-turbo"
        ),
        error=error,
        description=(
            "Generates SDXL stills + 2.5D parallax. Laptop-friendly "
            "(GTX 1650 +); always available when worker has torch + diffusers."
        ),
    )


class SDXLParallaxProvider:
    """Always-attempted SDXL parallax provider.

    Heavy imports (torch, diffusers) happen inside ``generate``, not at
    module load. The ``info`` probe uses ``importlib`` to determine
    availability without actually loading torch.
    """

    @property
    def info(self) -> ProviderInfo:
        for mod in ("torch", "diffusers"):
            if importlib.util.find_spec(mod) is None:
                return _info(
                    installed=False,
                    error=f"python module '{mod}' not importable",
                )
        return _info(installed=True)

    def generate(self, req: GenerationRequest, work_dir: Path) -> Path:
        info = self.info
        if not info.installed:
            raise ModelNotAvailable(
                _PROVIDER_ID,
                info.error or "sdxl_parallax not ready",
                info.install_hint,
            )

        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            from worker_runtime.sdxl_parallax.backend import (  # type: ignore
                SDXLParallaxBackend,
            )
            from worker_runtime.sdxl_parallax.parallax import (  # type: ignore
                AnimMode,
                animate_still,
                write_video,
            )
        except ImportError as e:
            raise ModelNotAvailable(
                _PROVIDER_ID,
                f"sdxl_parallax import failed: {e}",
                info.install_hint,
            ) from e

        backend = SDXLParallaxBackend()
        backend.load()
        # Generate one still
        seed = int(req.seed) if req.seed is not None else 42
        still = backend.generate_image(prompt=req.prompt, seed=seed)
        # Pick aspect-aware target resolution.
        targets = {"9:16": (720, 1280), "1:1": (1024, 1024), "16:9": (1280, 720)}
        out_w, out_h = targets.get(req.aspect_ratio, (720, 1280))

        n_frames = max(1, int(math.ceil(req.duration_seconds * req.fps)))
        frames = animate_still(
            still,
            num_frames=n_frames,
            mode=AnimMode.KEN_BURNS,
            target_w=out_w,
            target_h=out_h,
        )
        out = work_dir / f"{_PROVIDER_ID}.mp4"
        write_video(frames, str(out), fps=req.fps)
        return out
