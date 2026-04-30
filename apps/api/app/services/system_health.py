"""System & model health probes — Phase 1 (Platform).

Cheap, side-effect-free checks the api can run on demand:

  * ffmpeg binary present & runnable (via imageio_ffmpeg)
  * Redis broker reachable (PING)
  * Object storage reachable (head_bucket on R2/MinIO)
  * faster-whisper import resolvable (importlib spec — does NOT load weights)
  * GPU / CUDA visibility via ``nvidia-smi`` (subprocess, not torch import)
  * Per-model weight cache presence on disk (HuggingFace hub layout +
    optional ``XVE_MODELS_DIR`` override)

The api never imports torch/CTranslate2/diffusers — that would defeat
the "lightweight CPU api" rule. ``importlib.util.find_spec`` answers
"is this importable?" without actually executing the module.

Returns dataclasses-as-dicts so the FastAPI router can serialize them
directly. Each probe is independent: a failure in one doesn't shortcut
the others.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


logger = logging.getLogger(__name__)


# ─── Probe result types ─────────────────────────────────────────────────


@dataclass
class ProbeResult:
    """One health check outcome.

    ``ok`` is the boolean "is this dependency usable right now?". Any
    non-ok probe carries ``error`` for the operator and ``hint`` for
    how to fix it (install command, env var, etc.).
    """
    name: str
    ok: bool
    detail: str = ""
    error: Optional[str] = None
    hint: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelProbe:
    """One AI model availability check.

    ``installed=True`` only when both the runtime python module is
    importable AND the weight cache exists on disk. ``mode`` is
    "text-to-video", "image-to-video", "speech-to-text", "lipsync", etc.
    """
    id: str
    name: str
    mode: str
    installed: bool
    required_vram_gb: float
    status: str
    error: Optional[str] = None
    hint: Optional[str] = None
    cache_path: Optional[str] = None


# ─── ffmpeg ─────────────────────────────────────────────────────────────


def probe_ffmpeg() -> ProbeResult:
    """Check the ffmpeg binary bundled with imageio_ffmpeg is runnable."""
    try:
        import imageio_ffmpeg  # type: ignore
    except ImportError as e:
        return ProbeResult(
            name="ffmpeg",
            ok=False,
            error=f"imageio-ffmpeg not installed: {e}",
            hint="pip install imageio-ffmpeg",
        )
    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # pragma: no cover - bundle missing
        return ProbeResult(
            name="ffmpeg",
            ok=False,
            error=f"could not resolve ffmpeg binary: {e}",
            hint="reinstall imageio-ffmpeg",
        )
    proc = subprocess.run(
        [exe, "-version"], capture_output=True, text=True, timeout=10,
    )
    if proc.returncode != 0:
        return ProbeResult(
            name="ffmpeg",
            ok=False,
            error=f"ffmpeg -version failed (exit={proc.returncode})",
            hint="check ffmpeg binary; reinstall imageio-ffmpeg",
        )
    first_line = (proc.stdout or "").splitlines()[0] if proc.stdout else ""
    return ProbeResult(
        name="ffmpeg",
        ok=True,
        detail=first_line[:200],
        extra={"path": exe},
    )


# ─── Redis ──────────────────────────────────────────────────────────────


def probe_redis() -> ProbeResult:
    """PING the configured Redis broker.

    Reads ``REDIS_URL`` (default ``redis://localhost:6379/0``). Uses
    socket_timeout so a dead host returns quickly.
    """
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis  # type: ignore
    except ImportError as e:
        return ProbeResult(
            name="redis",
            ok=False,
            error=f"redis-py not installed: {e}",
            hint="pip install redis",
        )
    try:
        client = redis.from_url(
            url, socket_connect_timeout=2, socket_timeout=2,
            decode_responses=True,
        )
        pong = client.ping()
    except Exception as e:
        return ProbeResult(
            name="redis",
            ok=False,
            error=f"connect/ping failed: {type(e).__name__}: {e}",
            hint=f"start Redis at {url} or set REDIS_URL",
            extra={"url": _redact_url(url)},
        )
    return ProbeResult(
        name="redis",
        ok=bool(pong),
        detail="PONG" if pong else "no response",
        extra={"url": _redact_url(url)},
    )


def _redact_url(url: str) -> str:
    """Strip credentials from a connection url for display."""
    if "@" not in url:
        return url
    scheme, rest = url.split("://", 1) if "://" in url else ("", url)
    _, host = rest.rsplit("@", 1)
    return f"{scheme}://***@{host}" if scheme else f"***@{host}"


# ─── Object storage ─────────────────────────────────────────────────────


def probe_storage() -> ProbeResult:
    """head_bucket against the configured R2/MinIO endpoint."""
    endpoint = os.environ.get("R2_ENDPOINT", "http://localhost:9000")
    bucket = os.environ.get("R2_BUCKET", "renders-dev")
    try:
        import boto3  # type: ignore
        from botocore.exceptions import ClientError, EndpointConnectionError
    except ImportError as e:
        return ProbeResult(
            name="storage",
            ok=False,
            error=f"boto3 not installed: {e}",
            hint="pip install boto3",
        )

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ.get("R2_ACCESS_KEY_ID", "minioadmin"),
        aws_secret_access_key=os.environ.get(
            "R2_SECRET_ACCESS_KEY", "minioadmin",
        ),
        region_name=os.environ.get("R2_REGION", "auto"),
    )
    try:
        client.head_bucket(Bucket=bucket)
        bucket_ok = True
        detail = f"bucket {bucket} reachable"
    except EndpointConnectionError as e:
        return ProbeResult(
            name="storage",
            ok=False,
            error=f"could not reach {endpoint}: {e}",
            hint=f"start MinIO/R2 at {endpoint} or set R2_ENDPOINT",
            extra={"endpoint": endpoint, "bucket": bucket},
        )
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchBucket", "NotFound"):
            bucket_ok = False
            detail = f"bucket {bucket} missing (will be auto-created on first render)"
        else:
            return ProbeResult(
                name="storage",
                ok=False,
                error=f"head_bucket: {code}: {e}",
                hint="check R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY",
                extra={"endpoint": endpoint, "bucket": bucket},
            )
    return ProbeResult(
        name="storage",
        ok=True,
        detail=detail,
        extra={
            "endpoint": endpoint, "bucket": bucket, "bucket_exists": bucket_ok,
        },
    )


# ─── Python import probes (no heavy load) ──────────────────────────────


def _module_importable(mod: str) -> bool:
    """Return True if ``mod`` can be imported without executing it."""
    try:
        return importlib.util.find_spec(mod) is not None
    except (ValueError, ImportError, ModuleNotFoundError):
        return False


def probe_faster_whisper() -> ProbeResult:
    if not _module_importable("faster_whisper"):
        return ProbeResult(
            name="faster_whisper",
            ok=False,
            error="faster-whisper python package not importable",
            hint="pip install faster-whisper>=1.0",
        )
    return ProbeResult(
        name="faster_whisper",
        ok=True,
        detail="faster_whisper module resolvable (CTranslate2 backend)",
    )


# ─── GPU / CUDA via nvidia-smi ─────────────────────────────────────────


def probe_gpu() -> ProbeResult:
    """Check GPU/CUDA visibility via ``nvidia-smi``.

    Uses subprocess instead of ``torch.cuda.is_available()`` so the api
    process never imports torch. Returns the GPU name + total VRAM in
    GiB on success.
    """
    smi = shutil.which("nvidia-smi")
    if not smi:
        return ProbeResult(
            name="gpu",
            ok=False,
            detail="nvidia-smi not on PATH (CPU-only host)",
            hint="GPU not required; ML models will run on CPU when supported",
        )
    try:
        proc = subprocess.run(
            [smi, "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception as e:
        return ProbeResult(
            name="gpu",
            ok=False,
            error=f"nvidia-smi invocation failed: {e}",
        )
    if proc.returncode != 0:
        return ProbeResult(
            name="gpu",
            ok=False,
            error=(proc.stderr or "").strip()[:200] or "nvidia-smi failed",
        )
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    if not lines:
        return ProbeResult(name="gpu", ok=False, error="nvidia-smi: no GPUs")

    gpus = []
    for ln in lines:
        parts = [p.strip() for p in ln.split(",")]
        name = parts[0] if parts else "unknown"
        mem_mib = float(parts[1]) if len(parts) > 1 else 0.0
        driver = parts[2] if len(parts) > 2 else ""
        gpus.append({
            "name": name,
            "vram_gb": round(mem_mib / 1024.0, 1),
            "driver": driver,
        })
    return ProbeResult(
        name="gpu",
        ok=True,
        detail=f"{len(gpus)} GPU(s); {gpus[0]['name']} ({gpus[0]['vram_gb']} GB)",
        extra={"gpus": gpus},
    )


# ─── Model weight cache probes ──────────────────────────────────────────


def _hf_cache_root() -> Path:
    """Return the active HuggingFace hub cache root.

    Honors ``HF_HOME`` and ``HF_HUB_CACHE``; defaults to the same path
    HuggingFace uses internally (``~/.cache/huggingface/hub`` on Linux,
    ``%USERPROFILE%/.cache/huggingface/hub`` on Windows).
    """
    if env := os.environ.get("HF_HUB_CACHE"):
        return Path(env)
    if env := os.environ.get("HF_HOME"):
        return Path(env) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _xve_models_root() -> Optional[Path]:
    """Optional operator override for a single models directory."""
    if env := os.environ.get("XVE_MODELS_DIR"):
        return Path(env)
    return None


def _hf_repo_present(repo_id: str) -> Optional[Path]:
    """Return the cache dir for ``repo_id`` if it exists, else None.

    HuggingFace stores repos as ``models--<org>--<name>`` directories
    under the hub cache. We only confirm presence; we do not validate
    that all weight files are intact (any operator who deleted a single
    blob can run ``huggingface-cli download`` to repair).
    """
    safe = "models--" + repo_id.replace("/", "--")
    candidates: list[Path] = [_hf_cache_root() / safe]
    if root := _xve_models_root():
        candidates.append(root / safe)
        candidates.append(root / repo_id.split("/")[-1])
    for cand in candidates:
        if cand.exists() and cand.is_dir():
            return cand
    return None


def _local_dir_present(*parts: str) -> Optional[Path]:
    """Return the first existing dir matching ``XVE_MODELS_DIR/<parts>``."""
    if not (root := _xve_models_root()):
        return None
    p = root.joinpath(*parts)
    return p if p.exists() and p.is_dir() else None


@dataclass
class _ModelSpec:
    id: str
    name: str
    mode: str
    runtime_module: str
    hf_repo: Optional[str]
    local_dirs: tuple[str, ...]
    required_vram_gb: float
    install_hint: str


# These specs are the source of truth for "what AI models the platform
# knows about". Each subsequent phase plugs into the same registry — a
# Wan/Hunyuan/SVD adapter adds its row here, the dashboard auto-displays.
_MODEL_SPECS: tuple[_ModelSpec, ...] = (
    _ModelSpec(
        id="faster_whisper_base",
        name="faster-whisper (base)",
        mode="speech-to-text",
        runtime_module="faster_whisper",
        hf_repo="Systran/faster-whisper-base",
        local_dirs=("faster-whisper-base",),
        required_vram_gb=0.0,
        install_hint=(
            "auto-downloaded on first transcription; "
            "to pre-cache: huggingface-cli download Systran/faster-whisper-base"
        ),
    ),
    _ModelSpec(
        id="faster_whisper_base_en",
        name="faster-whisper (base.en)",
        mode="speech-to-text",
        runtime_module="faster_whisper",
        hf_repo="Systran/faster-whisper-base.en",
        local_dirs=("faster-whisper-base.en",),
        required_vram_gb=0.0,
        install_hint=(
            "auto-downloaded on first English transcription; "
            "to pre-cache: huggingface-cli download Systran/faster-whisper-base.en"
        ),
    ),
    _ModelSpec(
        id="sdxl_base",
        name="Stable Diffusion XL Base",
        mode="text-to-image",
        runtime_module="diffusers",
        hf_repo="stabilityai/stable-diffusion-xl-base-1.0",
        local_dirs=("sdxl-base", "stable-diffusion-xl-base-1.0"),
        required_vram_gb=8.0,
        install_hint=(
            "huggingface-cli download stabilityai/stable-diffusion-xl-base-1.0"
        ),
    ),
    _ModelSpec(
        id="svd",
        name="Stable Video Diffusion (img2vid)",
        mode="image-to-video",
        runtime_module="diffusers",
        hf_repo="stabilityai/stable-video-diffusion-img2vid-xt",
        local_dirs=("svd", "stable-video-diffusion-img2vid-xt"),
        required_vram_gb=12.0,
        install_hint=(
            "huggingface-cli download "
            "stabilityai/stable-video-diffusion-img2vid-xt"
        ),
    ),
    _ModelSpec(
        id="wan21",
        name="Wan 2.1 T2V",
        mode="text-to-video",
        runtime_module="diffusers",
        hf_repo="Wan-AI/Wan2.1-T2V-1.3B",
        local_dirs=("wan21", "Wan2.1-T2V-1.3B"),
        required_vram_gb=10.0,
        install_hint="huggingface-cli download Wan-AI/Wan2.1-T2V-1.3B",
    ),
    _ModelSpec(
        id="hunyuan_video",
        name="HunyuanVideo",
        mode="text-to-video",
        runtime_module="diffusers",
        hf_repo="tencent/HunyuanVideo",
        local_dirs=("hunyuan_video", "HunyuanVideo"),
        required_vram_gb=24.0,
        install_hint="huggingface-cli download tencent/HunyuanVideo",
    ),
    _ModelSpec(
        id="cogvideox",
        name="CogVideoX-5b",
        mode="text-to-video",
        runtime_module="diffusers",
        hf_repo="THUDM/CogVideoX-5b",
        local_dirs=("cogvideox", "CogVideoX-5b"),
        required_vram_gb=14.0,
        install_hint="huggingface-cli download THUDM/CogVideoX-5b",
    ),
    _ModelSpec(
        id="wav2lip",
        name="Wav2Lip (lipsync)",
        mode="lipsync",
        runtime_module="cv2",
        hf_repo=None,
        local_dirs=("wav2lip", "wav2lip/checkpoints"),
        required_vram_gb=4.0,
        install_hint=(
            "place Wav2Lip checkpoints under XVE_MODELS_DIR/wav2lip/checkpoints"
        ),
    ),
    _ModelSpec(
        id="sadtalker",
        name="SadTalker (lipsync)",
        mode="lipsync",
        runtime_module="torch",
        hf_repo=None,
        local_dirs=("sadtalker", "sadtalker/checkpoints"),
        required_vram_gb=8.0,
        install_hint=(
            "place SadTalker checkpoints under XVE_MODELS_DIR/sadtalker/checkpoints"
        ),
    ),
    _ModelSpec(
        id="musetalk",
        name="MuseTalk (lipsync)",
        mode="lipsync",
        runtime_module="torch",
        hf_repo="TMElyralab/MuseTalk",
        local_dirs=("musetalk",),
        required_vram_gb=8.0,
        install_hint="huggingface-cli download TMElyralab/MuseTalk",
    ),
)


def probe_model(spec: _ModelSpec) -> ModelProbe:
    """Resolve installed/missing for one model spec.

    A model is "installed" only when both:
      1. its runtime python module is importable, AND
      2. weights are present (HF cache or XVE_MODELS_DIR)

    Either missing → not installed; status string explains which.
    """
    module_ok = _module_importable(spec.runtime_module)

    cache_dir: Optional[Path] = None
    if spec.hf_repo:
        cache_dir = _hf_repo_present(spec.hf_repo)
    if cache_dir is None:
        for ld in spec.local_dirs:
            if hit := _local_dir_present(ld):
                cache_dir = hit
                break

    if module_ok and cache_dir is not None:
        return ModelProbe(
            id=spec.id, name=spec.name, mode=spec.mode,
            installed=True,
            required_vram_gb=spec.required_vram_gb,
            status=f"ready (cache: {cache_dir})",
            cache_path=str(cache_dir),
        )
    if not module_ok and cache_dir is None:
        return ModelProbe(
            id=spec.id, name=spec.name, mode=spec.mode,
            installed=False,
            required_vram_gb=spec.required_vram_gb,
            status="missing runtime + weights",
            error=(
                f"python module '{spec.runtime_module}' not importable "
                "AND no weight cache found"
            ),
            hint=spec.install_hint,
        )
    if not module_ok:
        return ModelProbe(
            id=spec.id, name=spec.name, mode=spec.mode,
            installed=False,
            required_vram_gb=spec.required_vram_gb,
            status="missing runtime",
            error=f"python module '{spec.runtime_module}' not importable",
            hint=f"pip install the worker requirements; runtime: {spec.runtime_module}",
            cache_path=str(cache_dir) if cache_dir else None,
        )
    # weights missing only
    return ModelProbe(
        id=spec.id, name=spec.name, mode=spec.mode,
        installed=False,
        required_vram_gb=spec.required_vram_gb,
        status="missing weights",
        error=(
            f"runtime '{spec.runtime_module}' importable but no cached "
            "weights found"
        ),
        hint=spec.install_hint,
    )


def probe_all_models() -> list[ModelProbe]:
    return [probe_model(s) for s in _MODEL_SPECS]


# ─── System-level rollup ────────────────────────────────────────────────


def system_health_snapshot() -> dict[str, Any]:
    """Run all infra probes (ffmpeg / redis / storage / GPU / whisper)."""
    probes = [
        probe_ffmpeg(),
        probe_redis(),
        probe_storage(),
        probe_faster_whisper(),
        probe_gpu(),
    ]
    overall_ok = all(p.ok for p in probes if p.name != "gpu")
    # GPU is "advisory" — CPU-only hosts are still healthy
    return {
        "ok": overall_ok,
        "probes": [asdict(p) for p in probes],
    }


def models_health_snapshot() -> dict[str, Any]:
    """Per-model availability list."""
    items = [asdict(p) for p in probe_all_models()]
    return {
        "models": items,
        "installed": sum(1 for m in items if m["installed"]),
        "total": len(items),
    }
