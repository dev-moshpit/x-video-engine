"""Loopback smoke test -- start the worker in a background thread on the
laptop itself, then exercise the full router->worker->download path against
localhost. Proves the protocol without the 2080 being online.

Run:
    python scripts/run_loopback_smoke.py
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker_runtime"))

import uvicorn

from xvideo.spec import BackendName, Mode, Priority, ShotPlan
from xvideo.workers.wan21 import Wan21LowPolyClient


def _start_worker_thread(port: int) -> threading.Thread:
    from worker_runtime.wan21_worker import app
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    def _run():
        server.run()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    return t


def main() -> int:
    port = 8765
    print(f"  [BOOT] Starting low-poly worker on localhost:{port}")
    _start_worker_thread(port)

    client = Wan21LowPolyClient(
        endpoint=f"http://127.0.0.1:{port}",
        timeout_sec=120,
        poll_interval_sec=0.3,
        cache_dir=Path(__file__).resolve().parents[1] / "cache" / "loopback",
    )

    if not client.is_available():
        print("  [FAIL] Worker health check failed")
        return 1
    print("  [OK] Worker health check passed")

    shot = ShotPlan(
        shot_id="loopback_000",
        backend=BackendName.WAN21_LOWPOLY,
        mode=Mode.T2V,
        prompt="low poly geometric fox, faceted triangular mesh, pastel colors, gradient lighting",
        negative_prompt="photorealistic, smooth surfaces, organic textures",
        duration_sec=2.0,
        resolution="480p",
        fps=24,
        aspect_ratio="16:9",
        priority=Priority.STANDARD,
        num_candidates=1,
        seed=1,
    )
    print(f"  [SUBMIT] {shot.shot_id}")
    take = client.generate_sync(shot)
    if take is None:
        print("  [FAIL] generate_sync returned None")
        return 1

    path = Path(take.video_path)
    size_kb = path.stat().st_size / 1024 if path.exists() else 0
    print(f"  [OK] Got take: {take.take_id}")
    print(f"       path={path}")
    print(f"       size={size_kb:.1f} KB")
    print(f"       gen_time={take.generation_time_sec:.2f}s")

    if size_kb < 1:
        print("  [WARN] Video file is empty (ffmpeg may be missing). Protocol still OK.")

    client.close()
    return 0


if __name__ == "__main__":
    print("LowPoly Video Engine \u2014 Loopback smoke test (laptop-only)")
    print("-" * 55)
    sys.exit(main())
