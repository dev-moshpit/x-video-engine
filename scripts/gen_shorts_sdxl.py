"""End-to-end Shorts generator: prompt -> low-poly image (SDXL-Turbo)
-> parallax animation -> mp4 + sidecar.

Uses our existing prompt compiler, style guards, scorer, and artifact
metadata. This is the laptop-friendly path for shipping YouTube Shorts.

Usage:
    # Single clip with defaults:
    python scripts/gen_shorts_sdxl.py

    # Custom prompt + preset:
    python scripts/gen_shorts_sdxl.py --subject "a crystal deer" --preset crystal

    # Batch from eval corpus (first N entries):
    python scripts/gen_shorts_sdxl.py --batch 5
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HOME", "D:/hf_cache")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker_runtime"))

from xvideo.prompt import compile_prompt
from xvideo.spec import (
    ArtifactMeta, BackendName, CameraMove, LightingMode, LowPolySpec,
    PaletteMode, PolyDensity, RenderLane, StyleConfig, TimingBreakdown,
)
from xvideo.styles import resolve_style


def _camera_to_anim_mode(camera: CameraMove) -> str:
    """Map our CameraMove enum to parallax animation modes."""
    return {
        CameraMove.STATIC: "ken_burns",
        CameraMove.ORBIT: "orbit",
        CameraMove.DOLLY_IN: "zoom_in",
        CameraMove.DOLLY_OUT: "zoom_out",
        CameraMove.PAN_LEFT: "pan_left",
        CameraMove.PAN_RIGHT: "pan_right",
        CameraMove.TILT_UP: "ken_burns",
        CameraMove.TILT_DOWN: "ken_burns",
        CameraMove.CRANE: "ken_burns",
        CameraMove.TRACKING: "pan_right",
    }.get(camera, "ken_burns")


def generate_short(
    backend,
    spec: LowPolySpec,
    out_dir: Path,
    configs_dir: Path,
) -> dict:
    """Run the full pipeline for one spec. Returns a result dict."""

    # 1. Resolve style + apply guards + compile prompt (our existing pipeline)
    resolved_style = resolve_style(
        preset_name=spec.style.preset_name,
        overrides=spec.style.model_dump(exclude={"preset_name"}),
        styles_dir=configs_dir / "styles",
    )
    spec = spec.model_copy(update={"style": resolved_style})
    positive, negative, mutations = compile_prompt(spec)

    # 2. Build a stable output name
    seed = spec.seed or 42
    tag = f"{resolved_style.preset_name}_s{seed}_{int(time.time())}"
    out_path = out_dir / f"{tag}.mp4"
    img_path = out_dir / f"{tag}.png"

    print(f"\n[GEN] {spec.subject} | {resolved_style.preset_name} | seed={seed}")
    if mutations:
        print(f"  guards: {len(mutations)} applied")
        for m in mutations:
            print(f"    - {m.rule}: {m.field} {m.from_value} -> {m.to_value}")
    print(f"  prompt: {positive[:80]}...")

    # 3. Generate via backend
    t_total = time.time()
    result = backend.generate_video(
        prompt=positive,
        negative_prompt=negative,
        seed=seed,
        duration_sec=spec.duration_sec,
        fps=spec.fps,
        aspect_ratio=spec.aspect_ratio,
        anim_mode=_camera_to_anim_mode(spec.camera),
        out_path=str(out_path),
    )
    wall_total = time.time() - t_total

    timings = result["timings"]
    print(f"  image_gen: {timings['image_gen_sec']}s  "
          f"animate: {timings['animate_sec']}s  "
          f"write: {timings['write_sec']}s  "
          f"total: {timings['total_sec']}s")

    # 4. Also save the keyframe for inspection
    try:
        import cv2
        import numpy as np
        from PIL import Image
        img = backend.generate_image(positive, negative, seed, steps=2, guidance=0.0)
        Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).save(img_path)
    except Exception as e:
        logging.debug("keyframe save skipped: %s", e)

    # 5. Score (optional — requires opencv + our frames exist)
    score_dict = None
    try:
        from xvideo.scorer import score_take, diagnose_style, build_decision_summary
        from xvideo.spec import Take
        take = Take(
            take_id=tag,
            shot_id=tag,
            video_path=str(out_path),
            seed=seed,
            backend=BackendName.WAN21_LOWPOLY,
        )
        fs = score_take(take, positive)
        take.facet_score = fs
        take.style_diagnostic = diagnose_style(fs)
        take.decision_summary = build_decision_summary(take)

        score_dict = {
            "facet_clarity": round(fs.facet_clarity, 3),
            "palette_cohesion": round(fs.palette_cohesion, 3),
            "prompt_alignment": round(fs.prompt_alignment, 3),
            "edge_stability": round(fs.edge_stability, 3),
            "stylization_strength": round(fs.stylization_strength, 3),
            "overall": round(fs.overall, 3),
            "diagnostic_passed": take.style_diagnostic.passed,
            "diagnostic_reasons": take.style_diagnostic.reasons,
        }
        print(f"  score: overall={fs.overall:.3f}  "
              f"facet={fs.facet_clarity:.2f}  "
              f"palette={fs.palette_cohesion:.2f}  "
              f"stylization={fs.stylization_strength:.2f}")
        print(f"  decision: {take.decision_summary}")
    except Exception as e:
        print(f"  [scoring skipped: {e}]")

    # 6. Write artifact metadata sidecar
    meta = ArtifactMeta(
        spec_id=tag,
        seed=seed,
        preset_name=resolved_style.preset_name,
        compiled_prompt=positive,
        compiled_negative=negative,
        style_config=resolved_style,
        render_lane=spec.render_lane,
        num_inference_steps=2,
        guidance_scale=0.0,
        resolution=f"{result['width']}x{result['height']}",
        fps=spec.fps,
        duration_sec=spec.duration_sec,
        backend=BackendName.WAN21_LOWPOLY,  # placeholder enum; real model recorded below
        guard_mutations=mutations,
    )
    meta.timing = TimingBreakdown(
        generation_sec=timings["image_gen_sec"] + timings["animate_sec"],
        postprocess_sec=timings["write_sec"],
        total_sec=wall_total,
    )
    sidecar = out_path.with_suffix(".meta.json")
    meta_d = json.loads(meta.model_dump_json())
    meta_d["real_backend"] = f"sdxl-turbo+parallax ({backend.model_id})"
    meta_d["score"] = score_dict
    sidecar.write_text(json.dumps(meta_d, indent=2))
    print(f"  saved: {out_path.name} + {sidecar.name}")

    return {
        "out_path": str(out_path),
        "timings": timings,
        "wall_total_sec": round(wall_total, 2),
        "score": score_dict,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", default="a geometric fox")
    parser.add_argument("--action", default="running through snow")
    parser.add_argument("--environment", default="low poly forest")
    parser.add_argument("--preset", default="crystal",
                        choices=["crystal", "papercraft", "wireframe",
                                 "geometric_nature", "neon_arcade", "monument"])
    parser.add_argument("--duration", type=float, default=3.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--aspect", default="9:16", choices=["9:16", "16:9", "1:1"])
    parser.add_argument("--anim", default="ken_burns",
                        choices=["ken_burns", "zoom_in", "zoom_out", "orbit",
                                 "pan_left", "pan_right"])
    parser.add_argument("--batch", type=int, default=0,
                        help="If > 0, batch-generate N clips from eval_corpus.yaml")
    parser.add_argument("--audit", action="store_true",
                        help="Generate one curated clip per preset to showcase each preset's strengths")
    parser.add_argument("--out-dir", default="cache/shorts")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    project_root = Path(__file__).resolve().parents[1]
    configs_dir = project_root / "configs"
    out_dir = project_root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("LowPoly Shorts Generator — SDXL-Turbo + Parallax")
    print("=" * 60)

    # Boot backend (loads SDXL-Turbo into memory once)
    from sdxl_parallax.backend import SDXLParallaxBackend
    backend = SDXLParallaxBackend()
    print("\n[BOOT] Loading SDXL-Turbo (first run downloads ~7GB)...")
    t0 = time.time()
    backend.load()
    print(f"[BOOT] Ready in {time.time()-t0:.1f}s\n")

    results = []

    if args.audit:
        # Audit mode: one clip per preset, subjects curated to play to each preset's strengths.
        # Goal: visual verdict on which presets are launch-grade.
        audit_plan = [
            ("crystal",          "a geometric deer",              "standing alert",       "misty forest clearing",         CameraMove.ORBIT,    "orbit"),
            ("papercraft",       "a cozy paper cottage",          "",                     "rolling hills",                 CameraMove.DOLLY_IN, "zoom_in"),
            ("wireframe",        "a geometric astronaut",         "floating slowly",      "outer space with stars",        CameraMove.ORBIT,    "orbit"),
            ("geometric_nature", "a mountain landscape",          "slowly rotating",      "sunset sky with clouds",        CameraMove.ORBIT,    "ken_burns"),
            ("neon_arcade",      "a sports car",                  "driving",              "neon city street at night",     CameraMove.PAN_RIGHT,"pan_right"),
            ("monument",         "an impossible floating staircase", "",                  "abstract pastel space",         CameraMove.DOLLY_IN, "zoom_in"),
        ]
        for i, (preset, subject, action, environment, camera, anim) in enumerate(audit_plan):
            spec = LowPolySpec(
                subject=subject,
                action=action,
                environment=environment,
                style=StyleConfig(preset_name=preset),
                camera=camera,
                camera_speed=0.3,
                duration_sec=args.duration,
                aspect_ratio=args.aspect,
                seed=args.seed + i * 100,
                render_lane=RenderLane.PREVIEW,
            )
            # Audit records its own anim_mode choice (not derived from CameraMove)
            result = generate_short(backend, spec, out_dir, configs_dir)
            results.append(result)
    elif args.batch > 0:
        # Batch mode: pull from eval corpus
        import yaml
        with open(configs_dir / "eval_corpus.yaml") as f:
            corpus = yaml.safe_load(f)
        prompts = corpus["prompts"][:args.batch]
        for i, entry in enumerate(prompts):
            preset = (entry.get("presets", ["crystal"]))[0]
            spec = LowPolySpec(
                subject=entry["subject"],
                action=entry.get("action", ""),
                environment=entry.get("environment", ""),
                style=StyleConfig(preset_name=preset),
                camera=CameraMove.ORBIT,
                duration_sec=args.duration,
                aspect_ratio=args.aspect,
                seed=args.seed + i,
                render_lane=RenderLane.PREVIEW,
            )
            results.append(generate_short(backend, spec, out_dir, configs_dir))
    else:
        # Single clip
        spec = LowPolySpec(
            subject=args.subject,
            action=args.action,
            environment=args.environment,
            style=StyleConfig(preset_name=args.preset),
            camera=CameraMove.ORBIT,
            duration_sec=args.duration,
            aspect_ratio=args.aspect,
            seed=args.seed,
            render_lane=RenderLane.PREVIEW,
        )
        results.append(generate_short(backend, spec, out_dir, configs_dir))

    print("\n" + "=" * 60)
    print(f"DONE: {len(results)} clip(s) generated")
    for r in results:
        print(f"  {r['wall_total_sec']:.1f}s  {r['out_path']}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
