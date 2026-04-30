"""Golden end-to-end demo — the truth source for the LowPoly Video Engine.

Proves the full pipeline:
  1. Load preset + compose spec
  2. Engine.plan() → deterministic ShotPlan with guard mutations
  3. Dispatch to WAN21 low-poly worker (loopback or LAN)
  4. Score with FacetScorer (5 metrics incl. photoreal penalty)
  5. Style diagnostics
  6. Write sidecar artifact metadata (with guard_mutations)
  7. Print summary

Usage (loopback — no 2080 needed):
    python scripts/run_lowpoly_demo.py

Usage (LAN — worker must be running):
    export XVIDEO_WAN21_ENDPOINT="http://192.168.1.42:8080"
    python scripts/run_lowpoly_demo.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker_runtime"))

from xvideo.api import Engine
from xvideo.spec import (
    ArtifactMeta, CameraMove, LightingMode, LowPolySpec, PaletteMode,
    PolyDensity, RenderLane, StyleConfig,
)


def _boot_loopback_worker(port: int) -> None:
    import uvicorn
    from worker_runtime.wan21_worker import app
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)


def _patch_config_for_loopback(config_dir: Path, port: int) -> Path:
    import yaml
    base = config_dir / "backends.yaml"
    with open(base) as f:
        cfg = yaml.safe_load(f)
    cfg["workers"]["wan21_lowpoly"]["endpoint"] = f"http://127.0.0.1:{port}"
    override = config_dir / "backends.local.yaml"
    with open(override, "w") as f:
        yaml.safe_dump(cfg, f)
    return override


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    config_dir = project_root / "configs"
    port = 8766

    lan_endpoint = os.getenv("XVIDEO_WAN21_ENDPOINT")
    if lan_endpoint:
        print(f"  [MODE] LAN \u2014 targeting {lan_endpoint}")
        import yaml
        base = config_dir / "backends.yaml"
        with open(base) as f:
            cfg = yaml.safe_load(f)
        cfg["workers"]["wan21_lowpoly"]["endpoint"] = lan_endpoint
        override = config_dir / "backends.local.yaml"
        with open(override, "w") as f:
            yaml.safe_dump(cfg, f)
    else:
        print(f"  [MODE] Loopback \u2014 starting worker on localhost:{port}")
        _boot_loopback_worker(port)
        override = _patch_config_for_loopback(config_dir, port)

    # ── 1. Build the spec ────────────────────────────────────────────────
    spec = LowPolySpec(
        subject="a geometric fox",
        action="running through snow",
        environment="low poly forest, triangulated pine trees",
        style=StyleConfig(
            preset_name="crystal",
            poly_density=PolyDensity.MEDIUM,
            palette=PaletteMode.PASTEL,
            lighting=LightingMode.GRADIENT,
        ),
        camera=CameraMove.ORBIT,
        camera_speed=0.4,
        duration_sec=2.0,
        seed=42,
        render_lane=RenderLane.PREVIEW,
    )
    print(f"  [SPEC] subject='{spec.subject}' preset={spec.style.preset_name} lane={spec.render_lane.value}")

    # ── 2. Engine.plan() — deterministic composition ─────────────────────
    engine = Engine.__new__(Engine)
    engine.config_dir = config_dir
    from xvideo.router import Router
    engine.router = Router(config_path=override)
    from xvideo.spec import DEFAULT_POLICY, detect_hardware_tier
    engine.policy = DEFAULT_POLICY
    engine.hardware_tier = detect_hardware_tier()

    plan, mutations = engine.plan(spec)
    shot = plan.shots[0]
    print(f"  [PLAN] spec_id={plan.spec_id}")
    print(f"         shot_id={shot.shot_id}")
    print(f"         prompt={shot.prompt[:80]}...")
    print(f"         seed={shot.seed} steps={shot.num_inference_steps} cfg={shot.guidance_scale}")
    print(f"         resolution={shot.resolution} duration={shot.duration_sec}s")
    print(f"         preset={shot.style_config.preset_name} lane={shot.render_lane.value}")
    if mutations:
        print(f"         guard_mutations: {len(mutations)}")
        for m in mutations:
            print(f"           {m.rule}: {m.field} {m.from_value} \u2192 {m.to_value}")
    else:
        print(f"         guard_mutations: none (no contradictions)")

    # ── 3. Dispatch ──────────────────────────────────────────────────────
    print(f"  [DISPATCH] Sending to {shot.backend.value}...")
    result = engine.router.dispatch(shot)

    if not result.winner_take_id:
        print(f"  [FAIL] Dispatch failed: {result.failure_codes}")
        return 1

    winner = next(t for t in result.takes if t.take_id == result.winner_take_id)
    video_path = Path(winner.video_path)
    size_kb = video_path.stat().st_size / 1024 if video_path.exists() else 0
    print(f"  [OK] Winner: {winner.take_id}")
    print(f"       path={video_path}")
    print(f"       size={size_kb:.1f} KB")
    print(f"       gen_time={winner.generation_time_sec:.2f}s")

    # ── 4. Score (if video has actual frames) ────────────────────────────
    if size_kb > 1:
        try:
            from xvideo.scorer import score_take, diagnose_style
            fs = score_take(winner, shot.prompt)
            winner.facet_score = fs
            print(f"  [SCORE] facet_clarity={fs.facet_clarity:.3f}")
            print(f"          palette_cohesion={fs.palette_cohesion:.3f}")
            print(f"          prompt_alignment={fs.prompt_alignment:.3f}")
            print(f"          edge_stability={fs.edge_stability:.3f}")
            print(f"          stylization_strength={fs.stylization_strength:.3f}")
            print(f"          overall={fs.overall:.3f}")

            diag = diagnose_style(fs)
            winner.style_diagnostic = diag
            if diag.passed:
                print(f"  [STYLE] PASSED \u2014 style compliance OK")
            else:
                print(f"  [STYLE] FAILED \u2014 {len(diag.reasons)} issues:")
                for r in diag.reasons:
                    print(f"           - {r}")
        except ImportError:
            print("  [SKIP] Scorer requires opencv-python + numpy")
    else:
        print("  [SKIP] Video too small for scoring (ffmpeg may be missing)")

    # ── 5. Write artifact metadata sidecar ───────────────────────────────
    meta = ArtifactMeta(
        spec_id=plan.spec_id,
        seed=winner.seed,
        preset_name=shot.style_config.preset_name,
        compiled_prompt=shot.prompt,
        compiled_negative=shot.negative_prompt,
        style_config=shot.style_config,
        render_lane=shot.render_lane,
        num_inference_steps=shot.num_inference_steps,
        guidance_scale=shot.guidance_scale,
        resolution=shot.resolution,
        fps=shot.fps,
        duration_sec=shot.duration_sec,
        backend=shot.backend,
        guard_mutations=mutations,
    )
    sidecar_path = video_path.with_suffix(".meta.json")
    sidecar_path.write_text(meta.model_dump_json(indent=2))
    print(f"  [META] Artifact sidecar: {sidecar_path}")
    print(f"         prompt_hash={meta.prompt_hash}")
    if mutations:
        print(f"         guard_mutations={len(mutations)} recorded")

    # ── 6. Summary ───────────────────────────────────────────────────────
    print()
    print("  Demo complete. This proves:")
    print("    - Engine.plan() resolves preset + compiles prompt + captures guard mutations")
    print("    - Router dispatches to WAN21 low-poly backend")
    print("    - Artifact metadata captures full reproducibility snapshot")
    if size_kb > 1:
        print("    - FacetScorer scores on 5 metrics (incl. photoreal leak penalty)")
        print("    - StyleDiagnostic gives structured pass/fail with reasons")

    return 0


if __name__ == "__main__":
    print("LowPoly Video Engine \u2014 Golden end-to-end demo")
    print("=" * 55)
    sys.exit(main())
