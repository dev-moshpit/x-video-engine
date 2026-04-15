"""Phase 0 smoke test: verify the scaffolding imports, dataclasses validate,
and the capability matrix is sane. No network, no GPU, no workers.

Run: python scripts/smoke_test_backend.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from xvideo.capabilities import (
    CAPABILITIES,
    BackendStatus,
    Mode,
    active_set,
    backends_supporting,
    cheapest_backend_for,
    experimental_set,
)
from xvideo.router import Router
from xvideo.spec import (
    BackendName,
    Camera,
    Constraints,
    ExecutionPlan,
    GenerationSpec,
    Priority,
    ShotPlan,
)


def test_spec_validates():
    spec = GenerationSpec(
        subject="a lone figure walking through neon rain",
        action="walking forward slowly",
        environment="cyberpunk alley, neon signs, wet asphalt",
        style="cinematic, shallow depth of field",
        duration_sec=5.0,
        camera=Camera(move="push", speed="slow", angle="low"),
        constraints=Constraints(aspect_ratio="9:16", resolution="720p", fps=24, seed=42),
    )
    assert spec.mode == Mode.T2V
    assert spec.duration_sec == 5.0
    print(f"  [OK] GenerationSpec validates: mode={spec.mode.value}, dur={spec.duration_sec}s")


def test_capability_matrix():
    assert len(CAPABILITIES) == len(BackendName), "every backend needs a capability entry"

    # Phase 1: WAN21_T2V and SDXL_IMAGE must be AVAILABLE_NOW
    active = active_set()
    assert BackendName.WAN21_T2V in active, "Wan 2.1 1.3B must be available_now for Phase 1"
    assert BackendName.SDXL_IMAGE in active, "SDXL must be available_now for Phase 1"
    print(f"  [OK] active_now backends: {[b.value for b in active]}")

    # Experimental set should include Wan 2.2 TI2V-5B (CPU offload on 2080)
    experimental = experimental_set()
    assert BackendName.WAN22_TI2V in experimental
    print(f"  [OK] experimental backends: {[b.value for b in experimental]}")

    # backends_supporting(T2V) without experimental = only available_now
    t2v_now = backends_supporting(Mode.T2V, include_experimental=False)
    assert BackendName.WAN21_T2V in t2v_now
    assert BackendName.WAN22_TI2V not in t2v_now, "experimental must be excluded by default"
    print(f"  [OK] T2V backends (available_now only): {len(t2v_now)}")

    # Cheapest T2V within 8GB VRAM should be Wan 2.1 1.3B
    cheapest_8 = cheapest_backend_for(Mode.T2V, max_vram_gb=8)
    assert cheapest_8 == BackendName.WAN21_T2V
    print(f"  [OK] cheapest T2V @ 8GB = {cheapest_8.value} (fits RTX 2080)")


def test_shot_plan_and_cost_estimate():
    plan = ExecutionPlan(
        spec_id="test001",
        shots=[
            ShotPlan(
                shot_id="s0",
                backend=BackendName.WAN21_T2V,
                mode=Mode.T2V,
                prompt="cinematic establishing shot",
                duration_sec=5.0,
                priority=Priority.HERO,
                num_candidates=2,
                seed=1,
            ),
        ],
    )
    router = Router(config_path=Path(__file__).resolve().parents[1] / "configs" / "backends.yaml")
    cost = router.estimate_cost(plan)
    # LAN worker = $0 per second
    assert cost == 0.0
    print(f"  [OK] 1-shot LAN plan cost estimate: ${cost:.3f} (Wan 2.1 on 2080)")


def test_router_config_loads():
    router = Router(config_path=Path(__file__).resolve().parents[1] / "configs" / "backends.yaml")
    # No endpoints configured yet in Phase 0, so available should be empty.
    available = router.available_backends()
    assert available == [], "Phase 0 expects no configured workers"
    print(f"  [OK] Router config loads; {len(available)} workers configured")


if __name__ == "__main__":
    print("X-Video Engine — Phase 0 smoke test")
    print("-" * 40)
    test_spec_validates()
    test_capability_matrix()
    test_shot_plan_and_cost_estimate()
    test_router_config_loads()
    print("-" * 40)
    print("All Phase 0 smoke tests passed.")
