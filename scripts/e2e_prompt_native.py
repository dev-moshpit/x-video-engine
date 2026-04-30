"""End-to-end smoke test for the prompt-native pipeline.

Default mode (``--dry-run``) is GPU-free: it exercises plan generation,
schema integrity, variation behavior, scoring, caption-style writers,
safety filters, and CLI plumbing. Run this before any release.

A ``--render`` mode exists for the brave: it actually renders one or two
short prompts through SDXL + parallax + TTS + ffmpeg. Costs ~3 minutes
per video on a GTX 1650-class GPU.

Usage::

    python scripts/e2e_prompt_native.py            # dry-run (default, fast)
    python scripts/e2e_prompt_native.py --render   # full pipeline (slow)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from xvideo.prompt_native import (
    CAPTION_STYLES,
    available_themes,
    build_caption_file,
    default_caption_style_for,
    generate_video_plan,
    plan_meets_thresholds,
    plan_to_render_jobs,
    score_plan,
)
from xvideo.prompt_native.safety_filters import audit_plan, sanitize_user_prompt


# ─── Result accounting ──────────────────────────────────────────────────

@dataclass
class CaseResult:
    name: str
    ok: bool
    elapsed: float
    detail: str = ""


def _run_case(name: str, fn, *args, **kwargs) -> CaseResult:
    t0 = time.time()
    try:
        detail = fn(*args, **kwargs) or ""
        elapsed = time.time() - t0
        print(f"  [ok]   {name}  ({elapsed:.2f}s)")
        if detail:
            print(f"         {detail}")
        return CaseResult(name, True, elapsed, detail)
    except AssertionError as e:
        elapsed = time.time() - t0
        print(f"  [FAIL] {name}  ({elapsed:.2f}s) -- assertion failed: {e}")
        return CaseResult(name, False, elapsed, f"assert: {e}")
    except Exception as e:  # pragma: no cover -- sanity
        elapsed = time.time() - t0
        print(f"  [FAIL] {name}  ({elapsed:.2f}s) -- {type(e).__name__}: {e}")
        return CaseResult(name, False, elapsed, f"{type(e).__name__}: {e}")


# ─── Cases ──────────────────────────────────────────────────────────────

def case_themes_listed() -> str:
    themes = available_themes()
    assert "motivation" in themes, "motivation theme missing"
    assert len(themes) >= 5, f"expected >=5 themes, got {len(themes)}"
    return f"{len(themes)} themes available"


def case_same_prompt_diff_videos() -> str:
    """Spec: NEW PROMPT = NEW ORIGINAL VIDEO EVERY TIME."""
    seeds = []
    for _ in range(3):
        p = generate_video_plan("Make a motivational video about discipline",
                                   variations=1)[0]
        seeds.append(p.seed)
    assert len(set(seeds)) == 3, f"3 calls produced overlapping seeds: {seeds}"
    return f"3 distinct seeds: {seeds}"


def case_fixed_seed_reproduces() -> str:
    a = generate_video_plan("discipline", variations=1, seed=42)[0]
    b = generate_video_plan("discipline", variations=1, seed=42)[0]
    assert a.title == b.title and a.hook == b.hook
    assert [s.scene_id for s in a.scenes] == [s.scene_id for s in b.scenes]
    return "seed=42 reproducible across calls"


def case_5_variations_distinct() -> str:
    plans = generate_video_plan("discipline", variations=5)
    seeds = [p.seed for p in plans]
    titles = [p.title for p in plans]
    assert len(set(seeds)) == 5
    return f"5 directions: {len(set(titles))} distinct titles"


def case_scene_count_in_band() -> str:
    plan = generate_video_plan("discipline", variations=1, seed=1)[0]
    n = len(plan.scenes)
    assert 3 <= n <= 8, f"scene count {n} outside 3-8 band"
    return f"{n} scenes"


def case_render_jobs_built(tmp_path: Path) -> str:
    plan = generate_video_plan("discipline", variations=1, seed=1)[0]
    jobs = plan_to_render_jobs(plan, tmp_path / "clips")
    assert len(jobs) == len(plan.scenes)
    for i, j in enumerate(jobs):
        assert j.seed == plan.seed + i
        assert j.prompt and j.negative_prompt
    return f"{len(jobs)} render jobs"


def case_no_text_in_visual_prompt() -> str:
    plan = generate_video_plan("Make a motivational video", variations=1, seed=11)[0]
    banned = ("subtitle", "caption", "watermark", "title card", "lower third")
    for s in plan.scenes:
        for tok in banned:
            assert tok not in s.visual_prompt.lower(), (
                f"scene {s.scene_id} contains {tok!r}"
            )
    return "no text-rendering tokens"


def case_score_thresholds() -> str:
    plan = generate_video_plan("discipline", variations=1, seed=42)[0]
    s = score_plan(plan)
    assert plan_meets_thresholds(s), f"director output failed thresholds: {s.to_dict()}"
    return f"score={s.total:.1f}/100  hook={s.hook_strength:.1f}  variety={s.scene_variety:.1f}"


def case_audit_warnings_clean() -> str:
    plan = generate_video_plan("discipline", variations=1, seed=42)[0]
    warns = audit_plan(plan)
    # Some warnings are acceptable — we just want the function to run cleanly.
    return f"{len(warns)} audit warnings"


def case_safety_sanitizer() -> str:
    cleaned = sanitize_user_prompt("  hello\x00 world  \n\n\n\nfoo  ")
    assert "\x00" not in cleaned
    assert "  " not in cleaned
    assert cleaned == "hello world\n\nfoo"
    return "control chars stripped, whitespace collapsed"


def case_all_caption_styles_writable(tmp_path: Path) -> str:
    # Build fake word events
    from dataclasses import dataclass

    @dataclass
    class W:
        text: str
        start_sec: float
        end_sec: float
    words = [W(t, i * 0.4, (i + 1) * 0.4)
             for i, t in enumerate(["build", "the", "habit", "today"])]
    written = []
    for s in CAPTION_STYLES:
        out = tmp_path / f"{s}.ass"
        build_caption_file(s, words, out)
        body = out.read_text(encoding="utf-8")
        assert "[Events]" in body and "Dialogue:" in body
        written.append(s)
    return f"{len(written)} styles written"


def case_default_styles_per_format() -> str:
    assert default_caption_style_for("shorts_clean") == "bold_word"
    assert default_caption_style_for("tiktok_fast") == "kinetic_word"
    assert default_caption_style_for("reels_aesthetic") == "clean_subtitle"
    return "format-default mapping intact"


def case_cli_dry_run(tmp_path: Path) -> str:
    """Exercises the full CLI plumbing (argparse -> director -> plan dump)."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "generate_prompt_video.py"),
         "--prompt", "Make a motivational video about discipline",
         "--variations", "2",
         "--dry-run",
         "--out-dir", str(tmp_path)],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, f"CLI exit={proc.returncode}: {proc.stderr[-500:]}"
    files = list((tmp_path / "_prompt_plans").glob("plan_*.json"))
    assert len(files) == 2, f"expected 2 plan dumps, got {len(files)}"
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["video_plan"]["generation_mode"] == "prompt_native"
    return f"CLI ok, {len(files)} plans dumped"


def case_legacy_pack_workflow_intact() -> str:
    """Spec: legacy pack workflow must still work."""
    from xvideo.prompt_planner import plan_from_prompt
    result = plan_from_prompt("motivational video about discipline",
                                  pack=None, count=2, seeds=[42])
    assert result.pack
    assert result.rows
    return f"legacy planner routes to {result.pack} with {len(result.rows)} rows"


def case_existing_director_imports_still_work() -> str:
    """Existing UI/CLI imports from prompt_video_director must keep working."""
    from xvideo.prompt_video_director import (
        VideoPlan, Scene, generate_variations, generate_video_plan,
    )
    plans = generate_variations("discipline", n=2, seed=42)
    assert len(plans) == 2
    assert isinstance(plans[0], VideoPlan)
    return "legacy imports green"


# ─── Render mode (slow) ─────────────────────────────────────────────────

def case_render_one_video(out_dir: Path) -> str:
    """Run the actual SDXL+TTS+ffmpeg pipeline on one short prompt.

    Costs ~3 minutes on GTX 1650. Skipped unless --render is passed.
    """
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "generate_prompt_video.py"),
        "--prompt", "Make a motivational video about discipline. Cinematic.",
        "--variations", "1",
        "--seed", "42",
        "--duration", "12",
        "--out-dir", str(out_dir),
        "--finish",
    ]
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    assert proc.returncode == 0, f"render failed exit={proc.returncode}"
    finals = list(out_dir.rglob("*_final.mp4"))
    assert finals, "no final mp4 produced"
    return f"final mp4: {finals[0].relative_to(out_dir)}"


# ─── Driver ─────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true",
                     help="Run the slow GPU render path too (not just dry-run).")
    ap.add_argument("--out-dir", default=None,
                     help="Working directory for artifacts (default: temp).")
    args = ap.parse_args()

    if args.out_dir:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        cleanup = False
    else:
        import tempfile
        out_dir = Path(tempfile.mkdtemp(prefix="e2e_pn_"))
        cleanup = True

    print("=" * 72)
    print("E2E prompt-native smoke")
    print(f"  out_dir = {out_dir}")
    print("=" * 72)

    results: list[CaseResult] = []

    # Plan / schema / variation
    print("\n[1] schema + variation")
    results.append(_run_case("themes listed", case_themes_listed))
    results.append(_run_case("same prompt -> diff videos", case_same_prompt_diff_videos))
    results.append(_run_case("fixed seed reproduces", case_fixed_seed_reproduces))
    results.append(_run_case("5 variations distinct", case_5_variations_distinct))
    results.append(_run_case("scene count in band", case_scene_count_in_band))
    results.append(_run_case("render jobs built",
                                case_render_jobs_built, out_dir / "rj"))
    results.append(_run_case("no text in visual prompt",
                                case_no_text_in_visual_prompt))

    # Score / audit / safety
    print("\n[2] scoring / audit / safety")
    results.append(_run_case("score thresholds", case_score_thresholds))
    results.append(_run_case("audit warnings clean", case_audit_warnings_clean))
    results.append(_run_case("safety sanitizer", case_safety_sanitizer))

    # Caption styles
    print("\n[3] caption styles")
    results.append(_run_case("all 6 caption styles writable",
                                case_all_caption_styles_writable, out_dir / "cap"))
    results.append(_run_case("default styles per format",
                                case_default_styles_per_format))

    # CLI plumbing
    print("\n[4] CLI plumbing")
    results.append(_run_case("CLI --dry-run produces plan json",
                                case_cli_dry_run, out_dir / "cli"))

    # Backward compat
    print("\n[5] backward compatibility")
    results.append(_run_case("legacy pack workflow intact",
                                case_legacy_pack_workflow_intact))
    results.append(_run_case("existing director imports still work",
                                case_existing_director_imports_still_work))

    # Render (slow)
    if args.render:
        print("\n[6] full render (slow)")
        results.append(_run_case("render one video",
                                    case_render_one_video, out_dir / "render"))
    else:
        print("\n[6] full render — skipped (pass --render to enable)")

    # Summary
    n_ok = sum(1 for r in results if r.ok)
    n_total = len(results)
    print("\n" + "=" * 72)
    print(f"DONE  {n_ok}/{n_total} cases passed")
    if n_ok != n_total:
        print("Failures:")
        for r in results:
            if not r.ok:
                print(f"  {r.name}: {r.detail}")
    print("=" * 72)

    if cleanup and n_ok == n_total:
        try:
            shutil.rmtree(out_dir)
        except Exception:
            pass

    return 0 if n_ok == n_total else 3


if __name__ == "__main__":
    sys.exit(main())
