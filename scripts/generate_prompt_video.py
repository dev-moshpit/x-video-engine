"""Prompt-native video generation CLI.

The primary path of the LowPoly Shorts Engine. Each invocation:

    1. Sanitizes the prompt and generates one or more fresh ``VideoPlan``s
       (title, concept, hook, scene plan, voiceover, CTA, seed, ...).
    2. Renders each scene as a background clip via SDXL-Turbo + parallax.
    3. With --finish: stitches scenes, generates TTS, builds word
       captions in the chosen style, overlays the hook, and (optionally)
       mixes a music bed under voice — outputs a single final MP4.

Same prompt produces a different video each call unless a fixed seed is
supplied via --seed (which gives full reproducibility).

Usage:

    # Generate a brand new video plan + render its scene clips
    python scripts/generate_prompt_video.py \\
        --prompt "Make a motivational video about discipline"

    # Same thing but with the final MP4 (TTS, captions, hook, mux)
    python scripts/generate_prompt_video.py \\
        --prompt "Make a motivational video about discipline" --finish

    # Five distinct creative directions for the same prompt
    python scripts/generate_prompt_video.py \\
        --prompt "AI tools are replacing boring work" \\
        --format tiktok_fast --variations 5

    # Reproducible (pin the seed)
    python scripts/generate_prompt_video.py \\
        --prompt "Luxury villa open house in Dubai" \\
        --format reels_aesthetic --seed 1234 --finish

    # Plan-only — no GPU. Inspect concept / hook / scenes / VO / CTA.
    python scripts/generate_prompt_video.py --prompt "..." --dry-run

    # Pick a caption style (6 supported; default depends on format)
    python scripts/generate_prompt_video.py --prompt "..." \\
        --caption-style karaoke_3word --finish

    # Drop a royalty-free loop in assets/music/ then:
    python scripts/generate_prompt_video.py --prompt "..." \\
        --music-bed auto --finish

The CLI also still accepts the legacy ``--plan-only`` and ``--no-finalize``
flags from the previous version so existing scripts and the UI keep
working unchanged.
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

from xvideo.prompt_native import (
    CAPTION_STYLES,
    available_themes,
    default_caption_style_for,
    generate_video_plan,
    plan_meets_thresholds,
    render_video_plan,
    score_plan,
)
from xvideo.prompt_native.safety_filters import audit_plan


def _onoff(s: str) -> bool:
    s = s.strip().lower()
    if s in ("on", "true", "1", "yes"):
        return True
    if s in ("off", "false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError(f"expected on/off, got '{s}'")


def _print_plan(plan, idx: int, total: int) -> None:
    print("=" * 72)
    print(f"VIDEO PLAN  variation {idx + 1}/{total}   "
          f"(seed={plan.seed}, hash={plan.prompt_hash})")
    print("=" * 72)
    print(f"  Theme        : {plan.theme}")
    print(f"  Title        : {plan.title}")
    print(f"  Hook         : {plan.hook}")
    print(f"  Concept      : {plan.concept}")
    print(f"  Visual style : {plan.visual_style}   palette={plan.color_palette}")
    print(f"  Pacing       : {plan.pacing}        voice={plan.voice_tone}")
    print(f"  Audience     : {plan.audience}")
    print(f"  Emotional    : {plan.emotional_angle}")
    print(f"  Caption style: {plan.caption_style}")
    print()
    print(f"  Scenes ({len(plan.scenes)}):")
    for s in plan.scenes:
        print(f"    [{s.scene_id}] {s.duration:.1f}s  "
              f"camera={s.camera_motion}  transition={s.transition}")
        print(f"        subj   : {s.subject}")
        print(f"        env    : {s.environment}")
        prompt_preview = s.visual_prompt[:90]
        if len(s.visual_prompt) > 90:
            prompt_preview += "…"
        print(f"        prompt : {prompt_preview}")
        print(f"        narr   : {s.narration_line}")
        print(f"        cap    : {s.on_screen_caption}")
    print()
    print(f"  Voiceover lines:")
    for line in plan.voiceover_lines:
        print(f"    · {line}")
    print(f"  CTA          : {plan.cta}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generate a brand new video from a prompt (prompt-native).",
    )

    # Core
    ap.add_argument("--prompt", required=False,
                    help="Free-form creative request (required unless --list-themes).")
    ap.add_argument("--format", default="shorts_clean",
                    help="Social format preset name "
                         "(shorts_clean, tiktok_fast, reels_aesthetic).")
    ap.add_argument("--variations", type=int, default=1,
                    help="How many distinct VideoPlans to generate from this prompt.")
    ap.add_argument("--style", default=None,
                    help="Optional style preference cue (e.g. \"intense\", \"dreamy\").")
    ap.add_argument("--duration", type=float, default=None,
                    help="Target final-video duration in seconds.")
    ap.add_argument("--seed", type=int, default=None,
                    help="Pin the variation seed for full reproducibility.")
    ap.add_argument("--aspect", default="9:16", choices=("9:16", "16:9", "1:1"))

    # Output
    ap.add_argument("--out-dir", "--out-root", dest="out_dir",
                    default="cache/batches",
                    help="Output root for prompt-native batches.")
    ap.add_argument("--batch-name", default=None,
                    help="Override the auto-generated batch folder name. "
                         "Only meaningful with --variations 1.")

    # Behavior gates (spec form + legacy aliases)
    ap.add_argument("--finish", action="store_true",
                    help="Render scenes + TTS + captions + hook + final MP4.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Generate plan(s) only — no rendering.")
    ap.add_argument("--plan-only", action="store_true",
                    help="(Legacy alias) same as --dry-run.")
    ap.add_argument("--no-finalize", action="store_true",
                    help="(Legacy) render scene clips only, skip TTS+captions+stitch.")

    # Post-stage knobs
    ap.add_argument("--caption-style", default=None, choices=CAPTION_STYLES,
                    help="Caption look. Default depends on --format.")
    ap.add_argument("--music-bed", default="none",
                    help="Music bed: 'none' (default), 'auto', or a path to an audio file.")
    ap.add_argument("--music-bed-db", type=float, default=-18.0,
                    help="Music bed level under voice in dB (default -18).")
    ap.add_argument("--voice", type=_onoff, default=True,
                    help="Generate TTS voiceover (on/off, default on).")
    ap.add_argument("--captions", type=_onoff, default=True,
                    help="Burn captions into the final (on/off, default on).")
    ap.add_argument("--hook", type=_onoff, default=True,
                    help="Overlay hook text in first ~2.5s (on/off, default on).")
    ap.add_argument("--voice-name", default=None,
                    help="Override TTS voice (e.g. en-US-JennyNeural).")
    ap.add_argument("--voice-rate", default="+0%",
                    help="TTS speech rate, edge-tts format (default '+0%%').")

    # Planner selection (spec)
    ap.add_argument("--planner", default="prompt_native",
                    choices=("prompt_native", "legacy_pack", "llm"),
                    help="Which planner to use (default: prompt_native). "
                         "legacy_pack and llm are not implemented in this CLI; "
                         "use scripts/run_shorts_batch.py for legacy_pack.")

    # Quality scoring
    ap.add_argument("--score-and-filter", action="store_true",
                    help="Run plans through the heuristic scorer and "
                         "regenerate weak plans before rendering.")

    # Misc
    ap.add_argument("--list-themes", action="store_true",
                    help="Print known themes and exit.")
    ap.add_argument("--list-caption-styles", action="store_true",
                    help="Print known caption styles and exit.")

    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                          format="[%(asctime)s] %(message)s",
                          datefmt="%H:%M:%S")

    if args.list_themes:
        for t in available_themes():
            print(t)
        return 0
    if args.list_caption_styles:
        for s in CAPTION_STYLES:
            print(s)
        return 0

    if args.planner != "prompt_native":
        print(f"[ERROR] --planner {args.planner} is not implemented in this CLI.")
        if args.planner == "legacy_pack":
            print("        Use: scripts/run_shorts_batch.py --pack ... --csv ...")
        return 4

    if not args.prompt:
        ap.error("--prompt is required (unless --list-themes / --list-caption-styles)")

    if args.variations < 1:
        print("[ERROR] --variations must be >= 1")
        return 2

    # Resolve final-mode behavior. Spec semantics:
    #   --dry-run / --plan-only       → plan only
    #   --finish                      → full render with finalization
    #   --no-finalize                 → render scenes, no finalization
    #   default                       → render scenes, no finalization
    dry_run = args.dry_run or args.plan_only
    finalize = args.finish and not args.no_finalize and not dry_run
    render_scenes = not dry_run

    project_root = Path(__file__).resolve().parents[1]
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = (project_root / out_dir).resolve()

    # 1. Generate plans (cheap, no GPU).
    plans = generate_video_plan(
        prompt=args.prompt,
        platform=args.format,
        duration=args.duration,
        style=args.style,
        seed=args.seed,
        variations=args.variations,
        aspect_ratio=args.aspect,
        score_and_filter=args.score_and_filter,
    )

    print()
    print(f"PROMPT       : {args.prompt}")
    print(f"FORMAT       : {args.format}")
    print(f"VARIATIONS   : {args.variations}")
    print(f"PLANNER      : {args.planner}")
    print(f"SEED         : {'fixed=' + str(args.seed) if args.seed is not None else 'random per call'}")
    print(f"CAPTION STYLE: {args.caption_style or default_caption_style_for(args.format) + ' (auto)'}")
    print(f"MUSIC BED    : {args.music_bed}")
    print(f"FINISH       : {'on' if finalize else 'off'}")
    print(f"DRY RUN      : {'on' if dry_run else 'off'}")
    print()

    plan_scores = []
    for i, plan in enumerate(plans):
        _print_plan(plan, i, len(plans))
        # Soft audit warnings — non-blocking.
        warnings = audit_plan(plan)
        if warnings:
            print("  ⚠ audit warnings:")
            for w in warnings:
                print(f"    · {w}")
        # Score (always compute for sidecar; only block if --score-and-filter).
        s = score_plan(plan)
        plan_scores.append(s)
        passed = plan_meets_thresholds(s)
        print(f"  Score        : total={s.total:.1f}/100  hook={s.hook_strength:.1f}  "
              f"variety={s.scene_variety:.1f}  "
              f"{'PASS' if passed else 'WARN'}")
        if s.notes:
            for n in s.notes:
                print(f"    · {n}")
        print()

    if dry_run:
        # Drop a JSON dump per plan so downstream tools can read it.
        dump_dir = out_dir / "_prompt_plans"
        dump_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        for plan, score in zip(plans, plan_scores):
            p = dump_dir / f"plan_{plan.prompt_hash[:8]}_v{plan.variation_id}_{ts}.json"
            payload = {
                "video_plan": plan.to_dict(),
                "score": score.to_dict(),
                "engine_version": "prompt_native/1.0",
            }
            p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
            print(f"  plan dumped: {p}")
        return 0

    # 2. Render — heavy, lazy.
    print("=" * 72)
    print(f"RENDERING ({args.variations} plan{'s' if args.variations != 1 else ''})  "
          f"finish={'on' if finalize else 'off'}")
    print("=" * 72)

    # Pre-load the SDXL backend ONCE so a batch of N variations doesn't
    # pay the ~8s pipeline-load cost N times. The backend instance is
    # threaded through the bridge → runner → _render_scene call chain.
    shared_backend = None
    if render_scenes:
        try:
            from sdxl_parallax.backend import SDXLParallaxBackend
            t_load = time.time()
            print(f"[{time.strftime('%H:%M:%S')}] Loading SDXL pipeline (one-time for batch)…")
            shared_backend = SDXLParallaxBackend()
            shared_backend.load()
            print(f"[{time.strftime('%H:%M:%S')}] Pipeline ready in {time.time() - t_load:.1f}s")
        except Exception as e:
            logging.error("Failed to load SDXL backend: %s", e)
            print(f"[ERROR] backend load failed: {e}")
            return 5

    batch_t0 = time.time()
    failures: list[str] = []
    finals: list[Path] = []
    succeeded: list[dict] = []  # for the group manifest
    for i, (plan, score) in enumerate(zip(plans, plan_scores)):
        batch_name = (args.batch_name
                       if (args.variations == 1 and args.batch_name) else None)
        print(f"\n[{i + 1}/{len(plans)}] {plan.title}  (seed={plan.seed})")
        v_t0 = time.time()
        try:
            artifacts = render_video_plan(
                plan=plan,
                output_root=out_dir,
                batch_name=batch_name,
                finalize=finalize,
                want_voice=args.voice,
                want_captions=args.captions,
                want_hook=args.hook,
                voice_name=args.voice_name,
                voice_rate=args.voice_rate,
                caption_style=args.caption_style,
                music_bed=args.music_bed,
                music_bed_db=args.music_bed_db,
                plan_score=score.to_dict(),
                backend=shared_backend,
            )
            v_elapsed = time.time() - v_t0
            print(f"  batch_dir : {artifacts.batch_dir}")
            print(f"  scenes    : {len(artifacts.scene_clips)}")
            print(f"  elapsed   : {v_elapsed:.1f}s")
            if artifacts.final_mp4:
                print(f"  final mp4 : {artifacts.final_mp4}")
                finals.append(artifacts.final_mp4)
            succeeded.append({
                "variation_id": plan.variation_id,
                "title":        plan.title,
                "hook":         plan.hook,
                "seed":         plan.seed,
                "score_total":  score.total,
                "batch_dir":    str(artifacts.batch_dir),
                "final_mp4":    str(artifacts.final_mp4) if artifacts.final_mp4 else None,
                "scene_count":  len(artifacts.scene_clips),
                "elapsed_sec":  round(v_elapsed, 1),
            })
        except Exception as e:
            logging.exception("variation failed")
            failures.append(f"v{plan.variation_id}: {e}")

    batch_elapsed = time.time() - batch_t0

    # Group-level manifest for batches > 1 — one place to find every
    # final from a single CLI invocation.
    if args.variations > 1 and succeeded:
        ts = time.strftime("%Y%m%d-%H%M%S")
        prompt_hash = plans[0].prompt_hash
        group_path = out_dir / f"_prompt_batches/group_{prompt_hash[:8]}_{ts}.json"
        group_path.parent.mkdir(parents=True, exist_ok=True)
        group_path.write_text(json.dumps({
            "engine_version":  "prompt_native/1.0",
            "prompt":          args.prompt,
            "prompt_hash":     prompt_hash,
            "format":          args.format,
            "duration":        args.duration,
            "caption_style":   args.caption_style,
            "music_bed":       args.music_bed,
            "variations":      args.variations,
            "succeeded":       len(succeeded),
            "failed":          len(failures),
            "total_wall_sec":  round(batch_elapsed, 1),
            "videos":          succeeded,
            "failures":        failures,
            "created_at":      time.strftime("%Y-%m-%dT%H:%M:%S"),
        }, indent=2, default=str), encoding="utf-8")
        print(f"\n[group manifest] {group_path}")

    print()
    print("=" * 72)
    n_ok = len(plans) - len(failures)
    print(f"DONE  ok={n_ok}/{len(plans)}  failed={len(failures)}  "
          f"total={batch_elapsed:.1f}s  ({batch_elapsed / max(1, n_ok):.1f}s/video)")
    if finals:
        print(f"\n{len(finals)} final MP4{'s' if len(finals) != 1 else ''}:")
        for i, f in enumerate(finals, 1):
            print(f"  [{i}] {f}")
    if failures:
        print("\nFailures:")
        for fail in failures:
            print(f"  {fail}")
    print("=" * 72)
    return 0 if not failures else 3


if __name__ == "__main__":
    sys.exit(main())
