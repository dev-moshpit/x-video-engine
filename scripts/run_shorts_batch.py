"""Production Shorts batch runner.

Reads a CSV of prompts, renders each as a 9:16 vertical clip with our
SDXL-Turbo + parallax backend. Resumable, retries on failure, validates
output, emits KPIs.

Usage:
    # Quick test with example CSV:
    python scripts/run_shorts_batch.py --csv configs/prompts_example.csv --batch-name first_batch

    # Your own prompt list:
    python scripts/run_shorts_batch.py --csv my_prompts.csv --batch-name 2026-04-21-morning

    # Resume after Ctrl+C:
    python scripts/run_shorts_batch.py --csv my_prompts.csv --batch-name 2026-04-21-morning

CSV schema (see configs/prompts_example.csv):
    id, subject, action, environment, preset, motion, duration, aspect, seeds

    - id: unique row identifier (used for resume)
    - subject: main scene subject (required)
    - action: verb phrase (optional)
    - environment: backdrop/setting (optional)
    - preset: one of crystal, papercraft, neon_arcade, monument
    - motion: calm | medium | energetic
    - duration: override motion profile default (optional)
    - aspect: 9:16 (default), 16:9, 1:1
    - seeds: comma-separated — each seed produces one variant clip
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

# Heavy / optional imports (yaml, SDXL pipeline, engine spec) are deferred
# into main() so lightweight paths like --init-pack and --list-packs work on
# any Python without the full render environment.
from xvideo.formats import (
    FormatConfig, apply_format_to_job, format_as_publish_overrides,
    list_formats, load_format,
)
from xvideo.pack_init import init_pack_dir
from xvideo.packs import list_packs, load_pack


def _motion_to_camera(motion: str) -> CameraMove:
    return {
        "calm": CameraMove.STATIC,
        "medium": CameraMove.ORBIT,
        "energetic": CameraMove.PAN_RIGHT,
    }.get(motion, CameraMove.ORBIT)


def build_generate_fn(backend, configs_dir: Path, batch_cfg: dict,
                      pack_config: dict | None = None,
                      fmt_config=None):
    """Closure that the BatchRunner will call for each job.

    Handles: prompt compilation with style guards, SDXL+parallax render,
    sidecar write, PNG keyframe save. If pack_config is provided, also
    computes publish metadata (title, caption, hashtags, CTA, platform
    variants) and writes it into both the sidecar and the BatchJob fields
    that feed the manifest. If fmt_config is provided, its overrides are
    layered into publish metadata and recorded in the sidecar for repro.
    """

    from sdxl_parallax.parallax import animate_still, write_video

    def _generate(job: BatchJob, output_dir: Path, motion_profile: dict) -> dict:
        # 1. Build LowPolySpec and resolve style
        spec = LowPolySpec(
            subject=job.subject,
            action=job.action,
            environment=job.environment,
            style=StyleConfig(preset_name=job.preset),
            camera=_motion_to_camera(job.motion),
            camera_speed={"calm": 0.2, "medium": 0.4, "energetic": 0.7}.get(job.motion, 0.4),
            duration_sec=job.duration_sec,
            aspect_ratio=job.aspect_ratio,
            seed=job.seed,
            render_lane=RenderLane.PREVIEW,
        )
        resolved_style = resolve_style(
            preset_name=spec.style.preset_name,
            overrides=spec.style.model_dump(exclude={"preset_name"}),
            styles_dir=configs_dir / "styles",
        )
        spec = spec.model_copy(update={"style": resolved_style})

        # 2. Compile prompt (style guards applied; returns mutations)
        positive, negative, mutations = compile_prompt(spec)

        # 2b. Append pack-contributed negative prompt fragments (e.g. suppress typography)
        if getattr(job, "extra_negative", ""):
            negative = f"{negative}, {job.extra_negative}"

        # 3. Generate keyframe via SDXL-Turbo
        t_img = time.time()
        image = backend.generate_image(
            prompt=positive,
            negative_prompt=negative,
            seed=job.seed,
            steps=2,
            guidance=0.0,
        )
        image_gen_sec = time.time() - t_img

        # 4. Animate via parallax using motion profile numbers
        aspect = job.aspect_ratio
        if aspect == "9:16":
            out_size = (576, 1024)
        elif aspect == "16:9":
            out_size = (1024, 576)
        else:
            out_size = (768, 768)

        frames = animate_still(
            image,
            mode=motion_profile.get("anim_mode", "ken_burns"),
            duration_sec=job.duration_sec,
            fps=24,
            out_size=out_size,
            zoom_range=tuple(motion_profile.get("zoom_range", (1.0, 1.25))),
            pan_fraction=motion_profile.get("pan_fraction", 0.15),
        )

        # 5. Write outputs
        clip_path = output_dir / f"{job.job_id}.mp4"
        write_video(frames, str(clip_path), fps=24)

        # 6. Save keyframe PNG for quick visual audit
        try:
            import cv2
            from PIL import Image
            import numpy as np
            Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).save(
                output_dir / f"{job.job_id}.png"
            )
        except Exception:
            pass

        # 7. Write artifact metadata sidecar
        meta = ArtifactMeta(
            spec_id=job.job_id,
            seed=job.seed,
            preset_name=resolved_style.preset_name,
            compiled_prompt=positive,
            compiled_negative=negative,
            style_config=resolved_style,
            render_lane=RenderLane.PREVIEW,
            num_inference_steps=2,
            guidance_scale=0.0,
            resolution=f"{out_size[0]}x{out_size[1]}",
            fps=24,
            duration_sec=job.duration_sec,
            backend=BackendName.WAN21_LOWPOLY,
            guard_mutations=mutations,
        )
        meta.timing = TimingBreakdown(
            generation_sec=round(image_gen_sec, 2),
            postprocess_sec=0.0,
            total_sec=round(time.time() - t_img, 2),
        )
        meta_d = json.loads(meta.model_dump_json())
        meta_d["real_backend"] = f"sdxl-turbo+parallax ({backend.model_id})"
        meta_d["motion"] = job.motion
        meta_d["row_id"] = job.row_id
        if job.pack_name:
            meta_d["pack"] = job.pack_name
        # Deterministic prompt hash for reproducibility + E2E assertions.
        import hashlib as _hashlib
        meta_d["prompt_hash"] = _hashlib.sha256(
            f"{positive}|{negative}".encode("utf-8")
        ).hexdigest()[:16]

        # 8. Publish metadata (only in pack mode)
        if pack_config and getattr(job, "pack_row", None):
            try:
                fmt_overrides = (
                    format_as_publish_overrides(fmt_config) if fmt_config else None
                )
                publish = build_publish_metadata(
                    pack_config=pack_config,
                    row=job.pack_row,
                    seed=job.seed,
                    format_overrides=fmt_overrides,
                )
                meta_d["publish"] = publish.to_dict()
                # Also mirror into manifest-visible fields on the job
                job.title = publish.title
                job.caption = publish.caption
                job.hashtags = " ".join(publish.hashtags)
            except Exception as e:
                logging.warning("Publish metadata generation failed for %s: %s",
                                job.job_id, e)

        # 8b. Record format in sidecar for reproducibility.
        if fmt_config:
            meta_d["format"] = fmt_config.to_sidecar()

        (output_dir / f"{job.job_id}.meta.json").write_text(json.dumps(meta_d, indent=2))

        return {
            "video_path": str(clip_path),
            "image_gen_sec": image_gen_sec,
        }

    return _generate


def main() -> int:
    parser = argparse.ArgumentParser(description="Production Shorts batch runner")
    parser.add_argument("--csv", default=None,
                        help="CSV path (pack CSV if --pack, else raw batch CSV). "
                             "Required unless --init-pack or --list-packs.")
    parser.add_argument("--pack", default=None,
                        help="Content pack name under content_packs/ (e.g. motivational_quotes)")
    parser.add_argument("--batch-name", default=None,
                        help="Batch folder name (default: timestamp)")
    parser.add_argument("--config", default="configs/shorts_batch.yaml",
                        help="Batch config YAML (ship presets, motion profiles)")
    parser.add_argument("--allow-backlog", action="store_true",
                        help="Allow backlog presets (wireframe, geometric_nature)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse CSV and print job plan without rendering")
    parser.add_argument("--list-packs", action="store_true",
                        help="List available content packs and exit")
    parser.add_argument("--init-pack", default=None, metavar="NAME",
                        help="Scaffold a working folder for pack NAME with a "
                             "ready-to-edit input.csv and README.txt, then exit.")
    parser.add_argument("--rows", type=int, default=None,
                        help="With --init-pack: number of rows in input.csv "
                             "(default = template size)")
    parser.add_argument("--out-dir", default="runs",
                        help="With --init-pack: parent dir for working folder (default: runs)")
    parser.add_argument("--format", default=None, metavar="NAME",
                        help="Social format preset (shorts_clean, tiktok_fast, "
                             "reels_aesthetic). Overrides duration + motion bias + "
                             "publish CTA/hashtags/primary platform.")
    parser.add_argument("--list-formats", action="store_true",
                        help="List available social format presets and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s",
                        datefmt="%H:%M:%S")

    project_root = Path(__file__).resolve().parents[1]
    packs_root = project_root / "content_packs"

    # --list-packs short-circuits everything else
    if args.list_packs:
        packs = list_packs(packs_root)
        if not packs:
            print(f"[INFO] No packs in {packs_root}")
        else:
            print(f"Available packs ({packs_root}):")
            for name in packs:
                try:
                    pack = load_pack(name, packs_root)
                    print(f"  {name:<24} {pack.title}")
                except Exception as e:
                    print(f"  {name:<24} [ERROR: {e}]")
        return 0

    # --list-formats also short-circuits
    if args.list_formats:
        names = list_formats()
        if not names:
            print("[INFO] No format presets found")
        else:
            print("Available formats:")
            for name in names:
                try:
                    f = load_format(name)
                    window = ""
                    if f.duration_min or f.duration_max:
                        window = (f" duration={f.duration_min or '?'}-"
                                  f"{f.duration_max or '?'}s")
                    print(f"  {name:<20} platform={f.primary_platform:<6} "
                          f"motion_bias={f.motion_bias:<4}{window}")
                    print(f"    {f.description}")
                except Exception as e:
                    print(f"  {name:<20} [ERROR: {e}]")
        return 0

    # --init-pack scaffolds a working folder then exits
    if args.init_pack:
        out_dir = Path(args.out_dir)
        if not out_dir.is_absolute():
            out_dir = (Path.cwd() / out_dir).resolve()
        try:
            target = init_pack_dir(
                pack_name=args.init_pack,
                packs_root=packs_root,
                out_dir=out_dir,
                rows=args.rows,
            )
        except (FileNotFoundError, ValueError) as e:
            print(f"[ERROR] {e}")
            return 2
        csv_path = target / "input.csv"
        row_count = sum(1 for _ in csv_path.open(encoding="utf-8")) - 1
        print("=" * 68)
        print(f"INITIALIZED: {args.init_pack}")
        print("=" * 68)
        print(f"  Folder:    {target}")
        print(f"  CSV:       {csv_path.name}  ({row_count} rows)")
        print(f"  README:    README.txt")
        print()
        print("Next:")
        print(f"  1. Edit {csv_path}")
        print(f"  2. Run:")
        print(f"       python scripts/run_shorts_batch.py --pack {args.init_pack} \\")
        print(f"           --csv {csv_path} --batch-name <batch_name>")
        print("=" * 68)
        return 0

    if not args.csv:
        parser.error("--csv is required (omit only with --init-pack or --list-packs)")

    # Heavy imports only reached when actually rendering or dry-running.
    import yaml
    global BatchJob, BatchRunner, JobStatus, load_jobs_from_csv, pack_csv_to_jobs
    global compile_prompt, build_publish_metadata
    global ArtifactMeta, BackendName, CameraMove, LowPolySpec, RenderLane
    global StyleConfig, TimingBreakdown, resolve_style
    from xvideo.batch import (
        BatchJob, BatchRunner, JobStatus, load_jobs_from_csv,
    )
    from xvideo.packs import pack_csv_to_jobs
    from xvideo.prompt import compile_prompt
    from xvideo.publish_helper import build_publish_metadata
    from xvideo.spec import (
        ArtifactMeta, BackendName, CameraMove, LowPolySpec, RenderLane,
        StyleConfig, TimingBreakdown,
    )
    from xvideo.styles import resolve_style

    config_path = project_root / args.config
    with open(config_path) as f:
        batch_cfg = yaml.safe_load(f)

    csv_path = Path(args.csv).resolve()
    if not csv_path.exists():
        print(f"[ERROR] CSV not found: {csv_path}")
        return 1

    # Load jobs — pack mode expands pack CSV → BatchJobs; raw mode parses directly
    pack_config_dict: dict | None = None
    pack_allowed_motion: list[str] | None = None
    try:
        if args.pack:
            pack = load_pack(args.pack, packs_root)
            jobs = pack_csv_to_jobs(
                pack=pack,
                csv_path=csv_path,
                motion_profiles=batch_cfg.get("motion_profiles", {}),
            )
            # Enforce ship-preset gate unless --allow-backlog
            ship = set(batch_cfg.get("ship_presets", []))
            backlog = set(batch_cfg.get("backlog_presets", []))
            allowed = ship | backlog if args.allow_backlog else ship
            for j in jobs:
                if j.preset not in allowed:
                    raise ValueError(
                        f"Job {j.job_id}: preset '{j.preset}' not allowed. "
                        f"Pass --allow-backlog to use {sorted(backlog)}."
                    )
            pack_config_dict = pack.raw_config
            pack_allowed_motion = list(pack.allowed_motion)
            print(f"[PACK] Loaded '{pack.name}' ({pack.title})")
        else:
            jobs = load_jobs_from_csv(csv_path, batch_cfg, allow_backlog=args.allow_backlog)
    except ValueError as e:
        print(f"[ERROR] CSV parse failed: {e}")
        return 2
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return 2

    if not jobs:
        print("[ERROR] No jobs parsed from CSV")
        return 2

    # --format: apply social packaging preset AFTER jobs are built so it
    # overrides both pack defaults and row values, as designed.
    fmt_config: FormatConfig | None = None
    if args.format:
        try:
            fmt_config = load_format(args.format)
        except FileNotFoundError as e:
            print(f"[ERROR] {e}")
            return 2
        for j in jobs:
            apply_format_to_job(j, fmt_config, pack_allowed_motion)
        win = ""
        if fmt_config.duration_min or fmt_config.duration_max:
            win = (f" duration={fmt_config.duration_min or '?'}-"
                   f"{fmt_config.duration_max or '?'}s")
        print(f"[FORMAT] Applied '{fmt_config.name}' "
              f"(primary={fmt_config.primary_platform}, "
              f"motion_bias={fmt_config.motion_bias}){win}")

    batch_name = args.batch_name or time.strftime("batch-%Y%m%d-%H%M%S")
    output_root = project_root / batch_cfg.get("batch_output_root", "cache/batches")

    print("=" * 68)
    print(f"SHORTS BATCH: {batch_name}")
    print(f"  CSV:     {csv_path}")
    print(f"  Jobs:    {len(jobs)} (including variant seeds)")
    print(f"  Output:  {output_root / batch_name}")
    print("=" * 68)

    # Dry-run: show plan and exit
    if args.dry_run:
        from collections import Counter
        preset_ct = Counter(j.preset for j in jobs)
        motion_ct = Counter(j.motion for j in jobs)
        print("\n[DRY RUN] Job plan:")
        if fmt_config:
            print(f"  format:  {fmt_config.name}  "
                  f"(primary={fmt_config.primary_platform}, "
                  f"motion_bias={fmt_config.motion_bias})")
        print(f"  presets: {dict(preset_ct)}")
        print(f"  motion:  {dict(motion_ct)}")
        durations = sorted({round(j.duration_sec, 1) for j in jobs})
        print(f"  duration values: {durations}s")
        print("\n  First 10 jobs:")
        for j in jobs[:10]:
            fmt_tag = f"  fmt={j.format}" if j.format else ""
            print(f"    {j.job_id}  preset={j.preset}  motion={j.motion}  "
                  f"seed={j.seed}  dur={j.duration_sec}s{fmt_tag}")
        if len(jobs) > 10:
            print(f"    ... +{len(jobs)-10} more")
        print("\n  Est. wall time (20s/clip): "
              f"{len(jobs) * 20 / 60:.1f} minutes")
        return 0

    # Load SDXL backend once
    print("\n[BOOT] Loading SDXL-Turbo pipeline...")
    from sdxl_parallax.backend import SDXLParallaxBackend
    backend = SDXLParallaxBackend()
    t0 = time.time()
    backend.load()
    print(f"[BOOT] Ready in {time.time()-t0:.1f}s\n")

    # Run the batch
    configs_dir = project_root / "configs"
    generate_fn = build_generate_fn(
        backend, configs_dir, batch_cfg, pack_config_dict, fmt_config,
    )
    runner = BatchRunner(
        batch_name=batch_name,
        jobs=jobs,
        output_root=output_root,
        batch_config=batch_cfg,
        generate_fn=generate_fn,
    )
    stats = runner.run()

    # Final summary
    print("\n" + "=" * 68)
    print("BATCH COMPLETE")
    print("=" * 68)
    print(f"  Total jobs:      {stats.total_jobs}")
    print(f"  Completed:       {stats.completed}")
    print(f"  Failed:          {stats.failed}")
    print(f"  Skipped (resume):{stats.skipped_resumed}")
    print(f"  Wall time:       {stats.total_wall_sec:.1f}s "
          f"({stats.total_wall_sec/60:.1f} min)")
    if stats.completed:
        print(f"  Avg clip time:   {stats.avg_total_sec:.1f}s")
        print(f"  Throughput:      {stats.clips_per_minute:.2f} clips/min")
    print()
    if stats.per_preset:
        print("  Per-preset:")
        for p, v in sorted(stats.per_preset.items()):
            fail_mark = f" ({v['failed']} failed)" if v["failed"] else ""
            print(f"    {p:<20} {v['completed']}/{v['count']} done  "
                  f"avg {v['avg_total_sec']}s{fail_mark}")
    print()
    print(f"  Outputs:  {runner.clips_dir}")
    print(f"  Manifest: {runner.manifest_path}")
    print(f"  Stats:    {runner.stats_path}")
    if stats.failed:
        print(f"  Errors:   {runner.errors_path}")
    print("=" * 68)
    return 0 if stats.failed == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
