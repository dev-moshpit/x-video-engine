"""Stable Video Diffusion provider (image-to-video) — Platform Phase 1.

Image-to-video via the diffusers ``StableVideoDiffusionPipeline``.
Requires ~12 GB VRAM for the XT variant; we expose only the
img2vid-xt path because it produces 25-frame 14fps clips that look
materially better than the 14-frame v0 weights.

Adapter contract: returns an mp4 in ``work_dir`` for any
:class:`GenerationRequest` that includes ``image_url``. If the user
gave only a prompt, we raise — text-to-video isn't this model's mode,
and the api shouldn't have routed here.
"""

from __future__ import annotations

import importlib.util
import logging
import urllib.request
from pathlib import Path
from typing import Optional

from apps.worker.video_models.base import (
    GenerationRequest,
    ModelNotAvailable,
    ProviderInfo,
)


logger = logging.getLogger(__name__)


_PROVIDER_ID = "svd"
_HF_REPO = "stabilityai/stable-video-diffusion-img2vid-xt"


def _hf_cache_present(repo_id: str) -> Optional[Path]:
    """Look up ``models--<org>--<name>`` under the HF hub cache."""
    import os
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
        name="Stable Video Diffusion (img2vid)",
        mode="image-to-video",
        required_vram_gb=12.0,
        installed=installed,
        install_hint=(
            "huggingface-cli download stabilityai/stable-video-diffusion-img2vid-xt"
        ),
        error=error,
        cache_path=cache_path,
        description=(
            "Animates a still image into a 25-frame clip at 14fps. "
            "GPU only; needs ~12 GB VRAM."
        ),
    )


class SVDProvider:
    """SVD-XT image-to-video adapter."""

    @property
    def info(self) -> ProviderInfo:
        for mod in ("torch", "diffusers"):
            if importlib.util.find_spec(mod) is None:
                return _info(
                    installed=False,
                    error=f"python module '{mod}' not importable",
                )
        cache = _hf_cache_present(_HF_REPO)
        if cache is None:
            return _info(
                installed=False,
                error=f"weight cache for {_HF_REPO} missing",
            )
        return _info(installed=True, cache_path=str(cache))

    def generate(self, req: GenerationRequest, work_dir: Path) -> Path:
        info = self.info
        if not info.installed:
            raise ModelNotAvailable(
                _PROVIDER_ID, info.error or "svd not ready", info.install_hint,
            )
        if not req.image_url:
            raise ModelNotAvailable(
                _PROVIDER_ID,
                "SVD requires image_url (image-to-video model)",
                "set image_url on the request to use SVD",
            )

        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            import torch  # type: ignore
            from diffusers import StableVideoDiffusionPipeline  # type: ignore
            from diffusers.utils import export_to_video, load_image  # type: ignore
        except ImportError as e:
            raise ModelNotAvailable(
                _PROVIDER_ID, f"import failed: {e}", info.install_hint,
            ) from e

        # Resolve image.
        if req.image_url.startswith(("http://", "https://")):
            img_path = work_dir / "svd_input.png"
            urllib.request.urlretrieve(req.image_url, img_path)
            image = load_image(str(img_path))
        else:
            image = load_image(req.image_url)

        # Pick dtype / device.
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32

        logger.info("loading SVD pipeline (device=%s, dtype=%s)", device, dtype)
        pipe = StableVideoDiffusionPipeline.from_pretrained(
            _HF_REPO,
            torch_dtype=dtype,
            variant="fp16" if dtype == torch.float16 else None,
        )
        pipe.to(device)
        pipe.enable_model_cpu_offload()

        seed = int(req.seed) if req.seed is not None else 42
        generator = torch.manual_seed(seed)

        # SVD generates 25 frames @ 14 fps native; we expose
        # ``num_frames`` via extra and clamp to a sensible range.
        num_frames = int(req.extra.get("num_frames", 25))
        num_frames = max(8, min(50, num_frames))
        decode_chunk_size = int(req.extra.get("decode_chunk_size", 8))

        frames = pipe(
            image,
            decode_chunk_size=decode_chunk_size,
            generator=generator,
            num_frames=num_frames,
        ).frames[0]

        out = work_dir / f"{_PROVIDER_ID}.mp4"
        export_to_video(frames, str(out), fps=req.fps or 14)
        return out
