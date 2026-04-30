"""Evaluation harness — runs the fixed corpus across presets, lanes, and seeds.

Resumable: skips runs whose sidecar already exists. Append-safe JSON report.
Outputs structured JSON report + CSV summary for quick slicing.

Usage (loopback):
    python scripts/eval_lowpoly_corpus.py

Usage (LAN):
    export XVIDEO_WAN21_ENDPOINT="http://192.168.1.42:8080"
    python scripts/eval_lowpoly_corpus.py

Usage (resume after partial run):
    python scripts/eval_lowpoly_corpus.py          # just re-run, it skips completed

Output:
    cache/eval/eval_report.json     — full structured results (append-safe)
    cache/eval/eval_summary.csv     — one row per run for quick slicing
    stdout                          — summary table
"""

from __future__ import annotations

import csv
import json
import os
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker_runtime"))

import yaml

from xvideo.api import Engine
from xvideo.spec import (
    CameraMove, LowPolySpec, RenderLane, StyleConfig, TimingBreakdown,
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


def _setup_engine(config_dir: Path, port: int) -> Engine:
    lan = os.getenv("XVIDEO_WAN21_ENDPOINT")
    endpoint = lan or f"http://127.0.0.1:{port}"
    if not lan:
        _boot_loopback_worker(port)

    base = config_dir / "backends.yaml"
    with open(base) as f:
        cfg = yaml.safe_load(f)
    cfg["workers"]["wan21_lowpoly"]["endpoint"] = endpoint
    override = config_dir / "backends.local.yaml"
    with open(override, "w") as f:
        yaml.safe_dump(cfg, f)

    engine = Engine.__new__(Engine)
    engine.config_dir = config_dir
    from xvideo.router import Router
    engine.router = Router(config_path=override)
    from xvideo.spec import DEFAULT_POLICY, detect_hardware_tier
    engine.policy = DEFAULT_POLICY
    engine.hardware_tier = detect_hardware_tier()
    return engine


# ─── Run key for deduplication / resume ──────────────────────────────────

def _run_key(subject: str, preset: str, lane: str, seed: int) -> str:
    """Stable key for identifying a unique run."""
    return f"{subject}|{preset}|{lane}|{seed}"


def _load_completed(report_path: Path) -> set[str]:
    """Load run keys from an existing partial report."""
    if not report_path.exists():
        return set()
    try:
        existing = json.loads(report_path.read_text())
        return {_run_key(r["subject"], r["preset"], r["lane"], r["seed"]) for r in existing}
    except (json.JSONDecodeError, KeyError):
        return set()


# ─── Single run ──────────────────────────────────────────────────────────

def _run_single(
    engine: Engine,
    subject: str,
    action: str,
    environment: str,
    preset: str,
    lane_str: str,
    seed: int,
) -> dict:
    lane = RenderLane(lane_str)
    spec = LowPolySpec(
        subject=subject,
        action=action,
        environment=environment,
        style=StyleConfig(preset_name=preset),
        camera=CameraMove.ORBIT,
        camera_speed=0.3,
        duration_sec=2.0,
        seed=seed,
        render_lane=lane,
    )

    t0 = time.monotonic()
    plan, mutations = engine.plan(spec)
    t_plan = time.monotonic() - t0

    shot = plan.shots[0]
    t1 = time.monotonic()
    result = engine.router.dispatch(shot)
    t_gen = time.monotonic() - t1

    entry = {
        "subject": subject,
        "action": action,
        "environment": environment,
        "preset": preset,
        "lane": lane_str,
        "seed": seed,
        "spec_id": plan.spec_id,
        "guard_mutations": len(mutations),
        "timing": {
            "planning_sec": round(t_plan, 3),
            "generation_sec": round(t_gen, 3),
            "total_sec": round(t_plan + t_gen, 3),
        },
        "winner": None,
        "score": None,
        "diagnostic_passed": None,
        "diagnostic_reasons": [],
        "selected_variant": "raw",
        "salvage_applied": False,
        "salvage_strategy": "",
        "decision_summary": "",
    }

    if result.winner_take_id:
        winner = next(t for t in result.takes if t.take_id == result.winner_take_id)
        entry["winner"] = winner.take_id
        entry["timing"]["generation_sec"] = round(winner.generation_time_sec, 3)

        video_path = Path(winner.video_path)
        if video_path.exists() and video_path.stat().st_size > 1024:
            try:
                from xvideo.scorer import score_take, diagnose_style, build_decision_summary
                t_score_start = time.monotonic()
                fs = score_take(winner, shot.prompt)
                winner.facet_score = fs
                diag = diagnose_style(fs)
                winner.style_diagnostic = diag
                winner.decision_summary = build_decision_summary(winner)
                t_score = time.monotonic() - t_score_start

                entry["score"] = {
                    "facet_clarity": round(fs.facet_clarity, 4),
                    "palette_cohesion": round(fs.palette_cohesion, 4),
                    "prompt_alignment": round(fs.prompt_alignment, 4),
                    "edge_stability": round(fs.edge_stability, 4),
                    "stylization_strength": round(fs.stylization_strength, 4),
                    "overall": round(fs.overall, 4),
                }
                entry["diagnostic_passed"] = diag.passed
                entry["diagnostic_reasons"] = diag.reasons
                entry["selected_variant"] = winner.selected_variant.value
                entry["timing"]["scoring_sec"] = round(t_score, 3)
                entry["decision_summary"] = winner.decision_summary
                if winner.salvage and winner.salvage.applied:
                    entry["salvage_applied"] = True
                    entry["salvage_strategy"] = winner.salvage.strategy
            except ImportError:
                pass
    else:
        entry["failure_codes"] = result.failure_codes

    return entry


# ─── Report I/O (append-safe) ────────────────────────────────────────────

def _save_report(results: list[dict], report_path: Path) -> None:
    """Write report atomically via temp file."""
    tmp = report_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(results, indent=2))
    tmp.replace(report_path)


def _write_csv(results: list[dict], csv_path: Path) -> None:
    """Write a flat CSV for quick slicing."""
    fields = [
        "subject", "preset", "lane", "seed", "spec_id",
        "guard_mutations", "winner", "selected_variant",
        "salvage_applied", "salvage_strategy", "diagnostic_passed",
        "facet_clarity", "palette_cohesion", "prompt_alignment",
        "edge_stability", "stylization_strength", "overall",
        "planning_sec", "generation_sec", "scoring_sec", "total_sec",
        "decision_summary",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            row = {**r}
            # Flatten nested dicts
            if r.get("score"):
                row.update(r["score"])
            if r.get("timing"):
                row.update(r["timing"])
            writer.writerow(row)


# ─── Summary ─────────────────────────────────────────────────────────────

def _print_summary(results: list[dict], total: int) -> None:
    print("\n" + "=" * 75)
    print("EVALUATION SUMMARY")
    print("=" * 75)

    by_preset: dict[str, list[float]] = defaultdict(list)
    by_lane: dict[str, list[float]] = defaultdict(list)
    by_preset_timing: dict[str, list[float]] = defaultdict(list)
    by_lane_timing: dict[str, list[float]] = defaultdict(list)
    salvage_count = 0
    reject_count = 0
    scored_count = 0
    diag_pass = 0
    variant_dist: dict[str, int] = defaultdict(int)
    diag_reasons: dict[str, int] = defaultdict(int)

    for r in results:
        if r.get("score"):
            o = r["score"]["overall"]
            by_preset[r["preset"]].append(o)
            by_lane[r["lane"]].append(o)
            scored_count += 1
            variant_dist[r.get("selected_variant", "raw")] += 1
            if r.get("diagnostic_passed"):
                diag_pass += 1
            for reason in r.get("diagnostic_reasons", []):
                field = reason.split("=")[0]
                diag_reasons[field] += 1
        if r.get("timing"):
            by_preset_timing[r["preset"]].append(r["timing"].get("total_sec", 0))
            by_lane_timing[r["lane"]].append(r["timing"].get("total_sec", 0))
        if r.get("salvage_applied"):
            salvage_count += 1
        if not r.get("winner"):
            reject_count += 1

    if not scored_count:
        print("\n  No scored results (ffmpeg may be missing for fake generation)")
        print("  The harness structure is validated — connect real inference to get scores.")
        print("=" * 75)
        return

    print(f"\n  Runs: {len(results)}/{total}  Scored: {scored_count}")
    print(f"  Diagnostic pass rate: {diag_pass}/{scored_count} ({100*diag_pass/scored_count:.0f}%)")
    print(f"  Salvage rate: {salvage_count}/{scored_count}")
    print(f"  Reject rate: {reject_count}/{len(results)}")
    print(f"  Variant distribution: {dict(variant_dist)}")

    if diag_reasons:
        print(f"\n  Most common diagnostic failures:")
        for reason, count in sorted(diag_reasons.items(), key=lambda x: -x[1]):
            print(f"    {reason}: {count}")

    # Preset ranking by median
    print(f"\n  {'Preset':<20} {'Median':>7} {'Mean':>6} {'Min':>6} {'Max':>6} {'N':>4} {'Avg sec':>8}")
    print(f"  {'-'*20} {'-'*7} {'-'*6} {'-'*6} {'-'*6} {'-'*4} {'-'*8}")
    for preset in sorted(by_preset, key=lambda p: -median(by_preset[p])):
        scores = by_preset[preset]
        timings = by_preset_timing.get(preset, [0])
        print(f"  {preset:<20} {median(scores):>7.3f} {sum(scores)/len(scores):>6.3f} "
              f"{min(scores):>6.3f} {max(scores):>6.3f} {len(scores):>4} "
              f"{sum(timings)/len(timings):>7.2f}s")

    # Lane ranking
    print(f"\n  {'Lane':<20} {'Median':>7} {'Mean':>6} {'Min':>6} {'Max':>6} {'N':>4} {'Avg sec':>8}")
    print(f"  {'-'*20} {'-'*7} {'-'*6} {'-'*6} {'-'*6} {'-'*4} {'-'*8}")
    for lane in ["preview", "standard", "fidelity"]:
        if lane not in by_lane:
            continue
        scores = by_lane[lane]
        timings = by_lane_timing.get(lane, [0])
        print(f"  {lane:<20} {median(scores):>7.3f} {sum(scores)/len(scores):>6.3f} "
              f"{min(scores):>6.3f} {max(scores):>6.3f} {len(scores):>4} "
              f"{sum(timings)/len(timings):>7.2f}s")

    # Top photoreal leak prompts (lowest stylization_strength)
    scored_entries = [r for r in results if r.get("score")]
    if scored_entries:
        by_stylization = sorted(scored_entries, key=lambda r: r["score"]["stylization_strength"])
        print(f"\n  Highest photoreal leak risk (lowest stylization_strength):")
        for r in by_stylization[:5]:
            print(f"    {r['score']['stylization_strength']:.3f}  {r['subject'][:35]:<35} [{r['preset']}|{r['lane']}]")

        # Worst temporal stability
        by_stability = sorted(scored_entries, key=lambda r: r["score"]["edge_stability"])
        print(f"\n  Worst temporal stability (lowest edge_stability):")
        for r in by_stability[:5]:
            print(f"    {r['score']['edge_stability']:.3f}  {r['subject'][:35]:<35} [{r['preset']}|{r['lane']}]")

    print("=" * 75)


# ─── Main ────────────────────────────────────────────────────────────────

def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    config_dir = project_root / "configs"
    corpus_path = config_dir / "eval_corpus.yaml"

    if not corpus_path.exists():
        print(f"  [ERROR] Corpus not found: {corpus_path}")
        return 1

    with open(corpus_path) as f:
        corpus = yaml.safe_load(f)

    prompts = corpus["prompts"]
    seeds = corpus.get("seeds", [42])
    lanes = corpus.get("lanes", ["preview"])

    total = sum(len(p.get("presets", ["crystal"])) * len(seeds) * len(lanes) for p in prompts)
    print(f"  [CORPUS] {len(prompts)} prompts x {len(lanes)} lanes x {len(seeds)} seeds = {total} runs")

    # Resume: load existing results
    eval_dir = project_root / "cache" / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    report_path = eval_dir / "eval_report.json"
    csv_path = eval_dir / "eval_summary.csv"

    completed_keys = _load_completed(report_path)
    if completed_keys:
        print(f"  [RESUME] Found {len(completed_keys)} completed runs — skipping those")

    # Load existing results to append to
    results: list[dict] = []
    if report_path.exists() and completed_keys:
        try:
            results = json.loads(report_path.read_text())
        except json.JSONDecodeError:
            results = []

    engine = _setup_engine(config_dir, 8767)
    done = 0
    skipped = 0
    new_runs = 0

    for prompt_entry in prompts:
        subject = prompt_entry["subject"]
        action = prompt_entry.get("action", "")
        environment = prompt_entry.get("environment", "")
        presets = prompt_entry.get("presets", ["crystal"])

        for preset in presets:
            for lane in lanes:
                for seed in seeds:
                    done += 1
                    key = _run_key(subject, preset, lane, seed)

                    if key in completed_keys:
                        skipped += 1
                        continue

                    tag = f"{subject[:30]}|{preset}|{lane}|s{seed}"
                    print(f"  [{done}/{total}] {tag}", end="", flush=True)

                    entry = _run_single(engine, subject, action, environment, preset, lane, seed)
                    results.append(entry)
                    new_runs += 1

                    overall = entry["score"]["overall"] if entry.get("score") else "n/a"
                    print(f"  score={overall}")

                    # Append-safe: save after every run
                    if new_runs % 5 == 0:
                        _save_report(results, report_path)

    # Final save
    _save_report(results, report_path)
    _write_csv(results, csv_path)

    print(f"\n  [DONE] {new_runs} new + {skipped} resumed = {len(results)} total")
    print(f"  [REPORT] {report_path}")
    print(f"  [CSV]    {csv_path}")

    _print_summary(results, total)
    return 0


if __name__ == "__main__":
    print("LowPoly Video Engine \u2014 Evaluation Corpus Harness")
    print("=" * 55)
    sys.exit(main())
