"""CogVideoX provider — Platform Phase 1.

THUDM's CogVideoX-5b, text-to-video. Requires ~14 GB VRAM with the
default fp16 weights.
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


_PROVIDER_ID = "cogvideox"
_DEFAULT_REPO = "THUDM/CogVideoX-5b"


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
        name="CogVideoX-5b",
        mode="text-to-video",
        required_vram_gb=14.0,
        installed=installed,
        install_hint=f"huggingface-cli download {_DEFAULT_REPO}",
        error=error,
        cache_path=cache_path,
        description=(
            "THUDM's CogVideoX 5B. Strong prompt adherence; needs ~14 GB VRAM."
        ),
    )


class CogVideoXProvider:

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
                info.error or "cogvideox not ready",
                info.install_hint,
            )

        try:
            import torch  # type: ignore
            try:
                from diffusers import CogVideoXPipeline  # type: ignore
            except ImportError as e:
                raise ModelNotAvailable(
                    _PROVIDER_ID,
                    "diffusers does not expose CogVideoXPipeline",
                    "pip install --upgrade 'diffusers>=0.30'",
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
                "CogVideoX requires CUDA",
                "run on a host with NVIDIA GPU + CUDA toolkit",
            )

        logger.info("loading CogVideoX pipeline")
        pipe = CogVideoXPipeline.from_pretrained(
            _DEFAULT_REPO, torch_dtype=torch.bfloat16,
        )
        pipe.to(device)
        if hasattr(pipe, "enable_model_cpu_offload"):
            pipe.enable_model_cpu_offload()

        seed = int(req.seed) if req.seed is not None else 42
        generator = torch.Generator(device=device).manual_seed(seed)
        num_frames = max(8, int(req.duration_seconds * (req.fps or 8)))
        num_frames = min(num_frames, int(req.extra.get("max_frames", 49)))

        frames = pipe(
            prompt=req.prompt,
            num_videos_per_prompt=1,
            num_inference_steps=int(req.extra.get("num_inference_steps", 50)),
            num_frames=num_frames,
            guidance_scale=float(req.extra.get("guidance_scale", 6.0)),
            generator=generator,
        ).frames[0]

        work_dir.mkdir(parents=True, exist_ok=True)
        out = work_dir / f"{_PROVIDER_ID}.mp4"
        export_to_video(frames, str(out), fps=req.fps or 8)
        return out
