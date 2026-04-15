"""Backend capability matrix — the source of truth for routing decisions.

The planner consults this to decide which backend(s) can satisfy a spec.
The router uses it to enforce VRAM/cost constraints.

Status field reflects the CURRENT hardware target (laptop + RTX 2080 LAN):
- available_now: implemented and runs on the RTX 2080 worker
- experimental:  implemented but slow/unstable on this hardware
- future:        registered for later hardware, NOT implemented yet
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

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
    BackendName.WAN21_T2V: BackendCapability(
        name=BackendName.WAN21_T2V,
        supported_modes={Mode.T2V},
        min_vram_gb=8,
        max_duration_sec=5.0,
        supported_resolutions={"480p", "720p"},
        supported_fps={24},
        approx_cost_per_sec_usd=0.0,
        status=BackendStatus.AVAILABLE_NOW,
        notes="Wan 2.1 T2V-1.3B. ~8GB VRAM. Phase 1 workhorse on RTX 2080.",
    ),
    BackendName.SDXL_IMAGE: BackendCapability(
        name=BackendName.SDXL_IMAGE,
        supported_modes={Mode.T2V},    # emits a still that downstream backends animate
        min_vram_gb=8,
        max_duration_sec=0.0,          # still, not video
        supported_resolutions={"512x512", "768x768", "1024x1024"},
        supported_fps={24},
        approx_cost_per_sec_usd=0.0,
        status=BackendStatus.AVAILABLE_NOW,
        notes="SDXL still generation. Feeds first-frame i2v workflows. Runs native on 2080.",
    ),

    # ─── EXPERIMENTAL on 2080 (CPU offload, slow) ─────────────────────────
    BackendName.WAN22_TI2V: BackendCapability(
        name=BackendName.WAN22_TI2V,
        supported_modes={Mode.T2V, Mode.I2V},
        min_vram_gb=24,
        max_duration_sec=5.0,
        supported_resolutions={"720p"},
        supported_fps={24},
        approx_cost_per_sec_usd=0.0,
        status=BackendStatus.EXPERIMENTAL,
        notes="Wan 2.2 TI2V-5B. 24GB officially; runs on RTX 2080 only via brutal CPU offload. Patience backend.",
    ),

    # ─── FUTURE: larger bases not yet implemented ─────────────────────────
    BackendName.WAN22_T2V: BackendCapability(
        name=BackendName.WAN22_T2V,
        supported_modes={Mode.T2V},
        min_vram_gb=80,
        max_duration_sec=5.0,
        supported_resolutions={"480p", "720p"},
        supported_fps={24},
        approx_cost_per_sec_usd=0.015,
        status=BackendStatus.FUTURE,
        notes="Wan 2.2 T2V-A14B. Requires A100 80GB. Not reachable on 2080.",
    ),
    BackendName.WAN22_I2V: BackendCapability(
        name=BackendName.WAN22_I2V,
        supported_modes={Mode.I2V},
        min_vram_gb=80,
        max_duration_sec=5.0,
        supported_resolutions={"480p", "720p"},
        supported_fps={24},
        approx_cost_per_sec_usd=0.015,
        status=BackendStatus.FUTURE,
        notes="Wan 2.2 I2V-A14B. Requires A100 80GB. Not reachable on 2080.",
    ),
    BackendName.HUNYUAN15_T2V: BackendCapability(
        name=BackendName.HUNYUAN15_T2V,
        supported_modes={Mode.T2V},
        min_vram_gb=14,
        max_duration_sec=5.0,
        supported_resolutions={"480p", "720p"},
        supported_fps={24},
        approx_cost_per_sec_usd=0.012,
        status=BackendStatus.FUTURE,
        notes="HunyuanVideo-1.5 T2V. 14GB min with offload. Skip on 2080 for v1.",
    ),
    BackendName.HUNYUAN15_I2V: BackendCapability(
        name=BackendName.HUNYUAN15_I2V,
        supported_modes={Mode.I2V},
        min_vram_gb=14,
        max_duration_sec=5.0,
        supported_resolutions={"480p", "720p"},
        supported_fps={24},
        approx_cost_per_sec_usd=0.012,
        status=BackendStatus.FUTURE,
        notes="HunyuanVideo-1.5 I2V. Step-distilled 480p variant is cheaper. Skip on 2080 for v1.",
    ),
    BackendName.OMNIWEAVING: BackendCapability(
        name=BackendName.OMNIWEAVING,
        supported_modes={
            Mode.T2V,
            Mode.I2V,
            Mode.FIRST_LAST_FRAME,
            Mode.REFERENCE_TO_VIDEO,
            Mode.MULTI_IMAGE_TO_VIDEO,
            Mode.VIDEO_EDIT,
        },
        min_vram_gb=60,
        max_duration_sec=5.0,
        supported_resolutions={"480p", "720p"},
        supported_fps={24},
        approx_cost_per_sec_usd=0.014,
        status=BackendStatus.FUTURE,
        notes="OmniWeaving. Built on HunyuanVideo-1.5. Not practical on 2080.",
    ),
    BackendName.LTX_KEYFRAME: BackendCapability(
        name=BackendName.LTX_KEYFRAME,
        supported_modes={Mode.I2V, Mode.FIRST_LAST_FRAME},
        min_vram_gb=16,
        max_duration_sec=10.0,
        supported_resolutions={"480p", "720p"},
        supported_fps={24, 30},
        approx_cost_per_sec_usd=0.0,
        status=BackendStatus.FUTURE,
        notes="LTX-Video keyframe. Official tooling wants 16GB+. Phase 2 experiment on 2080.",
    ),
    BackendName.LTX_CONTROL: BackendCapability(
        name=BackendName.LTX_CONTROL,
        supported_modes={Mode.CONTROLLED, Mode.I2V},
        min_vram_gb=16,
        max_duration_sec=10.0,
        supported_resolutions={"480p", "720p"},
        supported_fps={24, 30},
        approx_cost_per_sec_usd=0.0,
        status=BackendStatus.FUTURE,
        notes="LTX-Video depth/pose/canny guidance. Phase 2 experiment.",
    ),
    BackendName.LTX_EXTEND: BackendCapability(
        name=BackendName.LTX_EXTEND,
        supported_modes={Mode.VIDEO_EXTEND},
        min_vram_gb=16,
        max_duration_sec=10.0,
        supported_resolutions={"480p", "720p"},
        supported_fps={24, 30},
        approx_cost_per_sec_usd=0.0,
        status=BackendStatus.FUTURE,
        notes="LTX-Video forward/backward extension. Phase 2 experiment.",
    ),
}


def active_set() -> list[BackendName]:
    """Backends that are AVAILABLE_NOW on current hardware."""
    return [name for name, cap in CAPABILITIES.items() if cap.status == BackendStatus.AVAILABLE_NOW]


def experimental_set() -> list[BackendName]:
    return [name for name, cap in CAPABILITIES.items() if cap.status == BackendStatus.EXPERIMENTAL]


def backends_supporting(mode: Mode, include_experimental: bool = False) -> list[BackendName]:
    """Return backends that support the mode AND are implemented."""
    allowed_statuses = {BackendStatus.AVAILABLE_NOW}
    if include_experimental:
        allowed_statuses.add(BackendStatus.EXPERIMENTAL)
    return [
        name for name, cap in CAPABILITIES.items()
        if mode in cap.supported_modes and cap.status in allowed_statuses
    ]


def cheapest_backend_for(
    mode: Mode,
    max_vram_gb: int | None = None,
    include_experimental: bool = False,
) -> BackendName | None:
    """Cheapest implemented backend supporting mode within VRAM budget."""
    allowed_statuses = {BackendStatus.AVAILABLE_NOW}
    if include_experimental:
        allowed_statuses.add(BackendStatus.EXPERIMENTAL)
    candidates = [
        (name, cap) for name, cap in CAPABILITIES.items()
        if mode in cap.supported_modes
        and cap.status in allowed_statuses
        and (max_vram_gb is None or cap.min_vram_gb <= max_vram_gb)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[1].approx_cost_per_sec_usd)
    return candidates[0][0]
