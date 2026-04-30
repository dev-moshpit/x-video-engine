"""HunyuanVideo provider — Platform Phase 1.

Tencent's open-source HunyuanVideo, exposed via diffusers' HunyuanVideo
pipeline. Heavy: ~24 GB VRAM. The provider fails closed on any host
that doesn't already have the runtime + weight cache.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import Optional

from apps.worker.video_models.base import (
    GenerationRequest,
    ModelNotAvailable,
    ProviderInfo,
)


logger = logging.getLogger(__name__)


_PROVIDER_ID = "hunyuan_video"
_DEFAULT_REPO = "tencent/HunyuanVideo"


def _hf_cache_present(repo_id: str) -> Optional[Path]:
    safe = "models--" + repo_id.replace("/", "--")
    roots = []
    if env := os.environ.get("HF_HUB_CACHE"):
        roots.append(Path(env))
    if env := os.environ.get("HF_HOME"):
        roots.append(Path(env) / "hub")
    roots.append(Path.home() / ".cache" / "huggingface" / "hub")
    if env := os.environ.get("XVE_MODELS_DIR"):
        roots.append(Path(env))
    for r in roots:
        cand = r / safe
        if cand.exists() and cand.is_dir():
            return cand
    return None


def _info(installed: bool, error: Optional[str] = None,
          cache_path: Optional[str] = None) -> ProviderInfo:
    return ProviderInfo(
        id=_PROVIDER_ID,
        name="HunyuanVideo",
        mode="text-to-video",
        required_vram_gb=24.0,
        installed=installed,
        install_hint=f"huggingface-cli download {_DEFAULT_REPO}",
        error=error,
        cache_path=cache_path,
        description=(
            "Tencent's HunyuanVideo (~13B). Higher fidelity than Wan 2.1 "
            "but needs ~24 GB VRAM."
        ),
    )


class HunyuanVideoProvider:

    @property
    def info(self) -> ProviderInfo:
        for mod in ("torch", "diffusers"):
            if importlib.util.find_spec(mod) is None:
                return _info(
                    installed=False,
                    error=f"python module '{mod}' not importable",
                )
        cache = _hf_cache_present(_DEFAULT_REPO)
        if cache is None:
            return _info(
                installed=False,
                error=f"weight cache for {_DEFAULT_REPO} missing",
            )
        return _info(installed=True, cache_path=str(cache))

    def generate(self, req: GenerationRequest, work_dir: Path) -> Path:
        info = self.info
        if not info.installed:
            raise ModelNotAvailable(
                _PROVIDER_ID,
                info.error or "hunyuan_video not ready",
                info.install_hint,
            )

        try:
            import torch  # type: ignore
            try:
                from diffusers import HunyuanVideoPipeline  # type: ignore
            except ImportError as e:
                raise ModelNotAvailable(
                    _PROVIDER_ID,
                    "diffusers does not expose HunyuanVideoPipeline",
                    "pip install --upgrade 'diffusers>=0.32'",
                ) from e
            from diffusers.utils import export_to_video  # type: ignore
        except ImportError as e:
            raise ModelNotAvailable(
                _PROVIDER_ID, f"import failed: {e}", info.install_hint,
            ) from e

        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cpu":
            raise ModelNotAvailable(
                _PROVIDER_ID,
                "HunyuanVideo requires CUDA",
                "run on a host with NVIDIA GPU + CUDA toolkit",
            )

        logger.info("loading HunyuanVideo pipeline")
        pipe = HunyuanVideoPipeline.from_pretrained(
            _DEFAULT_REPO, torch_dtype=torch.float16,
        )
        pipe.to(device)
        if hasattr(pipe, "enable_model_cpu_offload"):
            pipe.enable_model_cpu_offload()

        seed = int(req.seed) if req.seed is not None else 42
        generator = torch.Generator(device=device).manual_seed(seed)
        num_frames = max(16, int(req.duration_seconds * (req.fps or 24)))
        num_frames = min(num_frames, int(req.extra.get("max_frames", 129)))

        frames = pipe(
            prompt=req.prompt,
            num_frames=num_frames,
            guidance_scale=float(req.extra.get("guidance_scale", 6.0)),
            num_inference_steps=int(req.extra.get("num_inference_steps", 50)),
            generator=generator,
        ).frames[0]

        work_dir.mkdir(parents=True, exist_ok=True)
        out = work_dir / f"{_PROVIDER_ID}.mp4"
        export_to_video(frames, str(out), fps=req.fps or 24)
        return out
