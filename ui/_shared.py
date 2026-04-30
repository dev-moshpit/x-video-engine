"""Shared helpers for the Streamlit UI.

Principle: the UI wraps CLI scripts via subprocess. The CLI remains the
source of truth — this file only exposes filesystem readers (for listing
packs, formats, batches) and a live-log subprocess runner.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Project paths
ROOT = Path(__file__).resolve().parents[1]
PACKS_ROOT = ROOT / "content_packs"
BATCHES_ROOT = ROOT / "cache" / "batches"
FORMATS_ROOT = ROOT / "xvideo" / "formats"
RUNS_ROOT = ROOT / "runs"
SCRIPTS = {
    "batch":     ROOT / "scripts" / "run_shorts_batch.py",
    "export":    ROOT / "scripts" / "export_selection.py",
    "final":     ROOT / "scripts" / "render_final_video.py",
    "e2e":       ROOT / "scripts" / "e2e_smoke_matrix.py",
}

# Make xvideo importable for direct (non-subprocess) reads
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ─── Packs / Formats discovery ──────────────────────────────────────────

def list_packs() -> list[dict]:
    """Enumerate content packs with title + required columns."""
    out: list[dict] = []
    if not PACKS_ROOT.is_dir():
        return out
    for d in sorted(PACKS_ROOT.iterdir()):
        cfg = d / "config.json"
        if not cfg.exists():
            continue
        try:
            j = json.loads(cfg.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({
            "name":      d.name,
            "title":     j.get("title", d.name),
            "required":  j.get("required_columns", []),
            "presets":   j.get("allowed_presets", []),
            "motion":    j.get("allowed_motion", []),
            "default_seeds": j.get("default_seeds", []),
        })
    return out


def list_formats() -> list[dict]:
    out: list[dict] = []
    if not FORMATS_ROOT.is_dir():
        return out
    for p in sorted(FORMATS_ROOT.glob("*.json")):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({
            "name":     p.stem,
            "description": j.get("description", ""),
            "primary":  j.get("primary_platform", ""),
            "motion_bias": j.get("motion_bias", ""),
            "duration_min": (j.get("duration") or {}).get("min"),
            "duration_max": (j.get("duration") or {}).get("max"),
        })
    return out


# ─── Batch discovery / stats ────────────────────────────────────────────

@dataclass
class BatchInfo:
    name: str
    path: Path
    mtime: float
    total: int = 0
    completed: int = 0
    failed: int = 0
    clips_per_minute: float = 0.0
    has_selection: bool = False
    starred: int = 0
    has_final_exports: bool = False

    @property
    def mtime_iso(self) -> str:
        return datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d %H:%M")


def list_batches() -> list[BatchInfo]:
    """Scan cache/batches/ and enrich each with stats.json + selection state."""
    if not BATCHES_ROOT.is_dir():
        return []
    out: list[BatchInfo] = []
    for d in BATCHES_ROOT.iterdir():
        if not d.is_dir():
            continue
        info = BatchInfo(name=d.name, path=d, mtime=d.stat().st_mtime)
        stats_path = d / "stats.json"
        if stats_path.exists():
            try:
                s = json.loads(stats_path.read_text(encoding="utf-8"))
                info.total = s.get("total_jobs", 0)
                info.completed = s.get("completed", 0)
                info.failed = s.get("failed", 0)
                info.clips_per_minute = s.get("clips_per_minute", 0.0)
            except Exception:
                pass
        sel = d / "selection.json"
        if sel.exists():
            info.has_selection = True
            try:
                info.starred = len(json.loads(sel.read_text(encoding="utf-8")).get("starred", []))
            except Exception:
                pass
        final_dir = d / "final_exports"
        info.has_final_exports = final_dir.is_dir() and any(final_dir.glob("*_final.mp4"))
        out.append(info)
    # Most-recent first
    out.sort(key=lambda b: b.mtime, reverse=True)
    return out


def load_manifest(batch_dir: Path) -> list[dict]:
    mf = batch_dir / "manifest.csv"
    if not mf.exists():
        return []
    import csv
    with open(mf, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_selection(batch_dir: Path) -> dict:
    p = batch_dir / "selection.json"
    if not p.exists():
        return {"starred": [], "rejected": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"starred": [], "rejected": []}


def save_selection(batch_dir: Path, starred: list[str], rejected: list[str]) -> None:
    data = {"starred": starred, "rejected": rejected, "batch_name": batch_dir.name}
    (batch_dir / "selection.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )


# ─── Live-log subprocess runner ─────────────────────────────────────────

def run_live(cmd: list, log_placeholder, max_lines: int = 400) -> int:
    """Run `cmd` streaming stdout+stderr to `log_placeholder.code(...)`.

    Returns the exit code. Uses the same Python that's running Streamlit
    so subprocess sees the same env.
    """
    proc = subprocess.Popen(
        cmd, cwd=str(ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, encoding="utf-8", errors="replace",
    )
    lines: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.append(line.rstrip())
        log_placeholder.code("\n".join(lines[-max_lines:]))
    proc.wait()
    return proc.returncode


def py_script(cmd: list[str]) -> list[str]:
    """Prepend the current interpreter to a script invocation."""
    return [sys.executable, *cmd]


# ─── Misc ───────────────────────────────────────────────────────────────

def rel_to_root(p: Path | str) -> str:
    """Display a path relative to the project root, forward-slashed."""
    p = Path(p)
    try:
        return str(p.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")
