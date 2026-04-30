"""CLI tests — dry-run / --finish flag plumbing.

We don't run the heavy SDXL render path here. We exercise the planning
path that ``--dry-run`` exposes and confirm the script stays exit-0,
prints the plan, and writes a plan JSON to disk.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "generate_prompt_video.py"


def _run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        **kwargs,
    )


def test_cli_list_themes_works():
    p = _run(["--list-themes"])
    assert p.returncode == 0
    out = p.stdout
    assert "motivation" in out
    assert "mystery" in out


def test_cli_list_caption_styles_works():
    p = _run(["--list-caption-styles"])
    assert p.returncode == 0
    out = p.stdout
    assert "bold_word" in out
    assert "karaoke_3word" in out


def test_cli_dry_run_produces_plan_json(tmp_path: Path):
    p = _run([
        "--prompt", "Make a motivational video about discipline",
        "--dry-run",
        "--out-dir", str(tmp_path),
        "--seed", "42",
    ])
    assert p.returncode == 0, f"CLI failed: {p.stderr}"
    # Plan dump dir created
    dump_dir = tmp_path / "_prompt_plans"
    assert dump_dir.exists()
    files = list(dump_dir.glob("plan_*.json"))
    assert files, "expected at least one plan json file"
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert "video_plan" in payload
    assert "score" in payload
    # The plan records the *resolved* RNG seed (not the user-input seed) —
    # but reproducibility holds: re-running with --seed 42 gives the same
    # plan, which we verify in the variations test suite.
    assert isinstance(payload["video_plan"]["seed"], int)
    assert payload["video_plan"]["generation_mode"] == "prompt_native"


def test_cli_dry_run_with_variations(tmp_path: Path):
    p = _run([
        "--prompt", "discipline",
        "--variations", "3",
        "--dry-run",
        "--out-dir", str(tmp_path),
    ])
    assert p.returncode == 0
    files = sorted((tmp_path / "_prompt_plans").glob("plan_*.json"))
    assert len(files) == 3


def test_cli_legacy_plan_only_alias(tmp_path: Path):
    p = _run([
        "--prompt", "discipline",
        "--plan-only",
        "--out-dir", str(tmp_path),
        "--seed", "1",
    ])
    assert p.returncode == 0


def test_cli_rejects_zero_variations(tmp_path: Path):
    p = _run([
        "--prompt", "discipline",
        "--variations", "0",
        "--dry-run",
        "--out-dir", str(tmp_path),
    ])
    assert p.returncode != 0


def test_cli_planner_legacy_pack_message():
    p = _run(["--prompt", "x", "--planner", "legacy_pack", "--dry-run"])
    assert p.returncode == 4
    assert "run_shorts_batch" in p.stdout
