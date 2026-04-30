"""Backend capability matrix for the LowPoly Video Engine.

Single-backend focus on Wan 2.1 T2V-1.3B with low-poly prompting.
Minimum viable target: GTX 1650 4GB (fp16, CPU offload, 480p short clips).
Comfortable target: RTX 2080 8GB (fp16, no offload, 480p longer clips).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from xvideo.spec import BackendName, Mode


class BackendStatus(str, Enum):
    AVAILABLE_NOW = "available_now"
    EXPERIMENTAL = "experimental"
    FUTURE = "future"


class BackendCapability(BaseModel):
    name: BackendName
    supported_modes: set[Mode]
    min_vram_gb: int
    max_duration_sec: float
    supported_resolutions: set[str]
    supported_fps: set[int]
    approx_cost_per_sec_usd: float = 0.0
    status: BackendStatus = BackendStatus.FUTURE
    notes: str = ""


CAPABILITIES: dict[BackendName, BackendCapability] = {
    # ─── AVAILABLE NOW on RTX 2080 LAN worker ─────────────────────────────
    BackendName.WAN21_LOWPOLY: BackendCapability(
        name=BackendName.WAN21_LOWPOLY,
        supported_modes={Mode.T2V},
        min_vram_gb=4,
        max_duration_sec=5.0,
        supported_resolutions={"480p"},
        supported_fps={24},
        approx_cost_per_sec_usd=0.0,
        status=BackendStatus.AVAILABLE_NOW,
        notes="Wan 2.1 T2V-1.3B fp16. 4GB min (CPU offload, short clips). "
              "8GB comfortable (no offload, longer clips). 480p only on 4GB.",
    ),

    # ─── FUTURE ───────────────────────────────────────────────────────────
    BackendName.WAN21_LOWPOLY_I2V: BackendCapability(
        name=BackendName.WAN21_LOWPOLY_I2V,
        supported_modes={Mode.I2V},
        min_vram_gb=8,
        max_duration_sec=5.0,
        supported_resolutions={"480p", "720p"},
        supported_fps={24},
        approx_cost_per_sec_usd=0.0,
        status=BackendStatus.FUTURE,
        notes="Image-conditioned low-poly video. Phase 2 feature.",
    ),
    BackendName.SDXL_KEYFRAME: BackendCapability(
        name=BackendName.SDXL_KEYFRAME,
        supported_modes={Mode.T2V},
        min_vram_gb=8,
        max_duration_sec=0.0,
        supported_resolutions={"512x512", "768x768", "1024x1024"},
        supported_fps={24},
        approx_cost_per_sec_usd=0.0,
        status=BackendStatus.FUTURE,
        notes="SDXL still keyframe for first-frame conditioning. Phase 2.",
    ),
}


def active_set() -> list[BackendName]:
    """Backends that are AVAILABLE_NOW on current hardware."""
    return [name for name, cap in CAPABILITIES.items()
            if cap.status == BackendStatus.AVAILABLE_NOW]


def backends_supporting(mode: Mode, include_experimental: bool = False) -> list[BackendName]:
    """Return backends that support the mode AND are implemented."""
    allowed = {BackendStatus.AVAILABLE_NOW}
    if include_experimental:
        allowed.add(BackendStatus.EXPERIMENTAL)
    return [name for name, cap in CAPABILITIES.items()
            if mode in cap.supported_modes and cap.status in allowed]


def default_backend() -> BackendName:
    """The single default backend for Phase 1."""
    return BackendName.WAN21_LOWPOLY
