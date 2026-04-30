"""Wan 2.1 T2V provider — Platform Phase 1.

Text-to-video via Wan-AI's open-source 1.3B and 14B variants. We pin
to the 1.3B variant by default because it fits on consumer GPUs;
operators with 24 GB VRAM can override via ``XVE_WAN21_REPO``.

This module fails closed: if the runtime / weights aren't available,
``generate`` raises :class:`ModelNotAvailable` with the install hint.
The api translates that to a 503 the operator sees.
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


_PROVIDER_ID = "wan21"
_DEFAULT_REPO = "Wan-AI/Wan2.1-T2V-1.3B"


def _resolve_repo() -> str:
    return os.environ.get("XVE_WAN21_REPO", _DEFAULT_REPO)


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
        name="Wan 2.1 T2V",
        mode="text-to-video",
        required_vram_gb=10.0,
        installed=installed,
        install_hint=f"huggingface-cli download {_resolve_repo()}",
        error=error,
        cache_path=cache_path,
        description=(
            "Open-source text-to-video model from Wan-AI. The 1.3B "
            "variant fits in ~10 GB VRAM."
        ),
    )


class Wan21Provider:

    @property
    def info(self) -> ProviderInfo:
        for mod in ("torch", "diffusers"):
            if importlib.util.find_spec(mod) is None:
                return _info(
                    installed=False,
                    error=f"python module '{mod}' not importable",
                )
        repo = _resolve_repo()
        cache = _hf_cache_present(repo)
        if cache is None:
            return _info(
                installed=False,
                error=f"weight cache for {repo} missing",
            )
        return _info(installed=True, cache_path=str(cache))

    def generate(self, req: GenerationRequest, work_dir: Path) -> Path:
        info = self.info
        if not info.installed:
            raise ModelNotAvailable(
                _PROVIDER_ID,
                info.error or "wan21 not ready",
                info.install_hint,
            )

        try:
            import torch  # type: ignore
            # Wan 2.1 is exposed via diffusers' ``WanPipeline`` in recent
            # versions. Older diffusers releases don't have it — surface
            # that as a clear "upgrade diffusers" hint instead of an
            # AttributeError mid-render.
            try:
                from diffusers import WanPipeline  # type: ignore
            except ImportError as e:
                raise ModelNotAvailable(
                    _PROVIDER_ID,
                    "diffusers does not expose WanPipeline (upgrade required)",
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
                "Wan 2.1 requires a CUDA GPU; CPU inference is not supported",
                "run on a host with NVIDIA GPU + CUDA toolkit",
            )

        dtype = torch.float16
        repo = _resolve_repo()

        logger.info("loading Wan 2.1 pipeline from %s", repo)
        pipe = WanPipeline.from_pretrained(repo, torch_dtype=dtype)
        pipe.to(device)
        if hasattr(pipe, "enable_model_cpu_offload"):
            pipe.enable_model_cpu_offload()

        seed = int(req.seed) if req.seed is not None else 42
        generator = torch.Generator(device=device).manual_seed(seed)

        num_frames = max(16, int(req.duration_seconds * (req.fps or 24)))
        num_frames = min(num_frames, int(req.extra.get("max_frames", 81)))

        frames = pipe(
            prompt=req.prompt,
            negative_prompt=req.extra.get("negative_prompt"),
            num_frames=num_frames,
            guidance_scale=float(req.extra.get("guidance_scale", 5.0)),
            num_inference_steps=int(req.extra.get("num_inference_steps", 50)),
            generator=generator,
        ).frames[0]

        work_dir.mkdir(parents=True, exist_ok=True)
        out = work_dir / f"{_PROVIDER_ID}.mp4"
        export_to_video(frames, str(out), fps=req.fps or 24)
        return out
