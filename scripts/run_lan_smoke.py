"""Phase 1d smoke test — laptop dispatches to 2080 worker over LAN.

Usage from the laptop:
    # 1. Start the worker on the 2080 desktop:
    #    python worker_runtime/wan21_worker.py --host 0.0.0.0 --port 8080
    #
    # 2. Set the endpoint (in configs/backends.yaml or via env):
    #    export XVIDEO_WAN21_ENDPOINT="http://192.168.1.42:8080"
    #
    # 3. Run this script:
    #    python scripts/run_lan_smoke.py

This test:
    1. Loads router config (or uses env override)
    2. Pings the worker health endpoint
    3. Submits a Wan 2.1 T2V job
    4. Polls until done
    5. Downloads the result .mp4
    6. Prints the local path + file size

Phase 1b worker returns an ffmpeg testsrc video (fake). Phase 1d swaps in
real Wan 2.1 inference.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from xvideo.router import Router
from xvideo.spec import BackendName, Mode, Priority, ShotPlan


def _patch_endpoint_from_env(config_path: Path) -> Path:
    """If XVIDEO_WAN21_ENDPOINT is set, materialize an override config."""
    endpoint = os.getenv("XVIDEO_WAN21_ENDPOINT")
    if not endpoint:
        return config_path

    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    cfg.setdefault("workers", {}).setdefault("wan21_t2v", {})["endpoint"] = endpoint

    override_path = config_path.parent / "backends.local.yaml"
    with open(override_path, "w") as f:
        yaml.safe_dump(cfg, f)
    print(f"  [INFO] Using endpoint from XVIDEO_WAN21_ENDPOINT={endpoint}")
    return override_path


def main():
    config_path = Path(__file__).resolve().parents[1] / "configs" / "backends.yaml"
    config_path = _patch_endpoint_from_env(config_path)

    router = Router(config_path=config_path)
    available = router.available_backends()
    print(f"  [INFO] Registered clients: {[b.value for b in available]}")

    if BackendName.WAN21_T2V not in available:
        print("  [SKIP] Wan 2.1 worker not configured. Set endpoint in configs/backends.yaml")
        print("         or export XVIDEO_WAN21_ENDPOINT=http://<2080-lan-ip>:8080")
        return 0

    # 1. Health check
    health = router.health_check()
    print(f"  [HEALTH] {health}")
    if not health.get(BackendName.WAN21_T2V.value):
        print("  [FAIL] Worker health check failed. Is the FastAPI service running?")
        return 1

    # 2. Dispatch a single shot
    shot = ShotPlan(
        shot_id="lan_smoke_000",
        backend=BackendName.WAN21_T2V,
        mode=Mode.T2V,
        prompt="a lone silhouette walking through neon-lit rain, cinematic",
        negative_prompt="blurry, low quality, watermark",
        duration_sec=3.0,
        resolution="480p",
        fps=24,
        aspect_ratio="16:9",
        priority=Priority.STANDARD,
        num_candidates=1,
        seed=42,
    )
    print(f"  [DISPATCH] {shot.shot_id} @ {shot.backend.value} ({shot.duration_sec}s {shot.resolution})")
    result = router.dispatch(shot)

    if not result.winner_take_id:
        print(f"  [FAIL] Dispatch failed: {result.failure_codes}")
        return 1

    winner = next(t for t in result.takes if t.take_id == result.winner_take_id)
    path = Path(winner.video_path)
    size_kb = path.stat().st_size / 1024 if path.exists() else 0
    print(f"  [OK] Winner: {winner.take_id}")
    print(f"       path={path}")
    print(f"       size={size_kb:.1f} KB")
    print(f"       gen_time={winner.generation_time_sec:.1f}s")
    return 0


if __name__ == "__main__":
    print("X-Video Engine — Phase 1d LAN smoke test")
    print("-" * 50)
    sys.exit(main())
