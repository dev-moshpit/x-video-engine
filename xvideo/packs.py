"""Content pack system.

A pack is a folder under `content_packs/{name}/` containing:
  - config.json     — pack metadata, defaults, allowed values, mappings, template
  - template.csv    — starter CSV the operator copies and edits
  - README.md       — how to use this pack

Each pack defines a **row transformer**: a declarative mapping from the
pack's simple CSV schema (e.g. `quote, tone, visual_subject`) to the
engine's internal batch schema (`subject, action, environment, preset,
motion, duration, aspect, seeds`).

This is what makes non-technical operators productive: they pick a pack,
fill in simple columns, and the pack's config owns all the prompt
structure, tone mapping, negative prompt rules, and motion presets.

Template language (tiny, no jinja):
    {col}                 — pack row column value
    {col|default}         — pack row value, falls back to config.defaults[col]
    {col|"literal"}       — pack row value, falls back to literal string
    {TABLE[col].prop}     — config.tables[TABLE][row[col]][prop]
    {TABLE[col].prop|default} — same with fallback
"""

from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from xvideo.batch import BatchJob

logger = logging.getLogger(__name__)

# Matches {...} slots. Inside group 1 is the expression.
_SLOT_RE = re.compile(r"\{([^{}]+)\}")


# ─── Template resolver (shared — used by packs and publish_helper) ──────

def _lookup_expr(expr: str, row: dict, tables: dict) -> Any:
    """Look up a value given an expression like `col` or `TABLE[col].prop`."""
    expr = expr.strip()
    m = re.fullmatch(r"(\w+)\[(\w+)\]\.(\w+)", expr)
    if m:
        table_name, col, prop = m.group(1), m.group(2), m.group(3)
        table = tables.get(table_name, {})
        key = row.get(col, "")
        entry = table.get(key, {})
        return entry.get(prop)
    return row.get(expr)


def _looks_like_expression(s: str) -> bool:
    if "[" in s and "]" in s and "." in s:
        return True
    if "|" in s:
        return True
    return False


def resolve_slot(expr: str, row: dict, tables: dict, defaults: dict) -> str:
    """Resolve one {...} expression. Supports:
        col, col|default, col|"literal", col|OTHER_EXPR
        TABLE[col].prop, TABLE[col].prop|fallback
    """
    default_part: str | None = None
    if "|" in expr:
        expr, default_raw = expr.split("|", 1)
        expr = expr.strip()
        default_part = default_raw.strip()

    value = _lookup_expr(expr, row, tables)
    if value in (None, ""):
        if default_part is None:
            return ""
        if default_part == "default":
            if "[" in expr:
                col = expr.split("[", 1)[1].split("]", 1)[0]
                value = defaults.get(col, "")
            else:
                value = defaults.get(expr, "")
        elif default_part.startswith('"') and default_part.endswith('"'):
            value = default_part[1:-1]
        elif _looks_like_expression(default_part):
            value = resolve_slot(default_part, row, tables, defaults)
        else:
            value = default_part
    return str(value) if value is not None else ""


def render_template(template: str, row: dict, tables: dict, defaults: dict) -> str:
    """Fill all {...} slots in a template string."""
    if not template:
        return ""
    def repl(m):
        return resolve_slot(m.group(1), row, tables, defaults)
    return _SLOT_RE.sub(repl, template).strip()


@dataclass
class PackConfig:
    """Loaded content pack configuration."""
    name: str
    title: str
    description: str
    pack_dir: Path
    allowed_presets: list[str]
    default_preset: str
    allowed_motion: list[str]
    default_motion: str
    default_duration: float
    default_aspect: str
    default_seeds: list[int]
    required_columns: list[str]
    optional_columns: list[str]
    row_transformer: dict[str, str]
    tables: dict[str, dict]
    defaults: dict[str, Any]
    additional_negative_prompt: list[str]
    raw_config: dict = field(default_factory=dict)   # full config.json for publish section etc.

    @classmethod
    def load(cls, pack_dir: str | Path) -> "PackConfig":
        pack_dir = Path(pack_dir)
        config_path = pack_dir / "config.json"
        if not config_path.exists():
            raise FileNotFoundError(f"Pack config not found: {config_path}")
        cfg = json.loads(config_path.read_text(encoding="utf-8"))

        return cls(
            name=cfg.get("name", pack_dir.name),
            title=cfg.get("title", pack_dir.name),
            description=cfg.get("description", ""),
            pack_dir=pack_dir,
            allowed_presets=cfg.get("allowed_presets", []),
            default_preset=cfg.get("default_preset", "crystal"),
            allowed_motion=cfg.get("allowed_motion", ["calm", "medium", "energetic"]),
            default_motion=cfg.get("default_motion", "medium"),
            default_duration=float(cfg.get("default_duration", 3.0)),
            default_aspect=cfg.get("default_aspect", "9:16"),
            default_seeds=list(cfg.get("default_seeds", [42])),
            required_columns=cfg.get("required_columns", []),
            optional_columns=cfg.get("optional_columns", []),
            row_transformer=cfg.get("row_transformer", {}),
            tables=cfg.get("tables", {}),
            defaults=cfg.get("defaults", {}),
            additional_negative_prompt=cfg.get("additional_negative_prompt", []),
            raw_config=cfg,
        )

    # ── Template resolution ──────────────────────────────────────────────

    def _render(self, template: str, row: dict) -> str:
        """Fill all {...} slots in a template string."""
        return render_template(template, row, self.tables, self.defaults)

    # ── Validation + expansion ───────────────────────────────────────────

    def validate_row(self, row: dict, row_num: int) -> None:
        for col in self.required_columns:
            if not row.get(col):
                raise ValueError(
                    f"Pack '{self.name}' row {row_num}: missing required column '{col}'"
                )
        preset = row.get("preset") or self.default_preset
        if preset not in self.allowed_presets:
            raise ValueError(
                f"Pack '{self.name}' row {row_num}: preset '{preset}' not in "
                f"allowed {self.allowed_presets}"
            )
        motion = row.get("motion") or self.default_motion
        if motion not in self.allowed_motion:
            raise ValueError(
                f"Pack '{self.name}' row {row_num}: motion '{motion}' not in "
                f"allowed {self.allowed_motion}"
            )

    def expand_row(self, row: dict, row_num: int) -> dict:
        """Transform one pack-CSV row into a batch-CSV row dict.

        Returns a dict with the standard batch schema: id, subject, action,
        environment, preset, motion, duration, aspect, seeds.
        Also includes `_extra_negative` if the pack contributes to the
        negative prompt.
        """
        self.validate_row(row, row_num)

        out: dict = {}
        for field_name, template in self.row_transformer.items():
            out[field_name] = self._render(template, row)

        # Fill in defaults from config if not provided
        if not out.get("id"):
            out["id"] = row.get("id") or f"{self.name}_row{row_num}"
        if not out.get("preset"):
            out["preset"] = row.get("preset") or self.default_preset
        if not out.get("motion"):
            out["motion"] = row.get("motion") or self.default_motion
        if not out.get("duration"):
            raw = row.get("duration") or ""
            out["duration"] = raw.strip() if isinstance(raw, str) else str(raw)
        if not out.get("aspect"):
            out["aspect"] = row.get("aspect") or self.default_aspect
        if not out.get("seeds"):
            seeds = row.get("seeds") or ""
            if not seeds:
                seeds = ",".join(str(s) for s in self.default_seeds)
            out["seeds"] = seeds

        # Pack contributes extra negative prompt fragments (e.g. suppress typography)
        out["_extra_negative"] = ", ".join(self.additional_negative_prompt)

        return out

    def expand_csv(self, csv_path: str | Path) -> tuple[list[dict], list[str]]:
        """Expand a pack CSV into batch-CSV rows.

        Returns (batch_rows, warnings).
        """
        csv_path = Path(csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(f"Pack CSV not found: {csv_path}")

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            return [], ["CSV has no data rows"]

        warnings: list[str] = []
        out: list[dict] = []
        for i, row in enumerate(rows, start=2):
            try:
                expanded = self.expand_row(row, i)
                out.append(expanded)
            except ValueError as e:
                warnings.append(str(e))
                raise
        return out, warnings


# ─── Pack discovery ─────────────────────────────────────────────────────

def list_packs(packs_root: Path) -> list[str]:
    if not packs_root.is_dir():
        return []
    return sorted([
        p.name for p in packs_root.iterdir()
        if p.is_dir() and (p / "config.json").exists()
    ])


def load_pack(pack_name: str, packs_root: Path) -> PackConfig:
    pack_dir = packs_root / pack_name
    if not pack_dir.is_dir():
        available = list_packs(packs_root)
        raise FileNotFoundError(
            f"Pack '{pack_name}' not found in {packs_root}. "
            f"Available: {available}"
        )
    return PackConfig.load(pack_dir)


# ─── Pack → BatchJobs ───────────────────────────────────────────────────

def pack_csv_to_jobs(
    pack: PackConfig,
    csv_path: Path,
    motion_profiles: dict,
) -> list[BatchJob]:
    """Top-level: pack CSV → expanded batch rows → BatchJobs (one per seed).

    Each BatchJob carries the original pack-CSV row dict on `pack_row` so
    downstream publish-metadata helpers can access fields like `quote`,
    `tone`, `topic`, `track_mood`, etc.
    """
    batch_rows, _ = pack.expand_csv(csv_path)

    # Re-read the original rows so we can attach them to BatchJobs.
    with open(csv_path, newline="", encoding="utf-8") as f:
        original_rows = list(csv.DictReader(f))
    if len(original_rows) != len(batch_rows):
        raise RuntimeError(
            f"Pack '{pack.name}': row count mismatch "
            f"({len(original_rows)} original vs {len(batch_rows)} expanded)"
        )

    jobs: list[BatchJob] = []
    seen_ids: set[str] = set()

    for row_num, (pack_row, row) in enumerate(zip(original_rows, batch_rows), start=2):
        row_id = row["id"]
        preset = row["preset"]
        motion = row["motion"]
        if motion not in motion_profiles:
            raise ValueError(
                f"Pack-expanded motion '{motion}' for row {row_id} is not in "
                f"motion_profiles {sorted(motion_profiles)}"
            )
        profile = motion_profiles[motion]
        duration_raw = (row.get("duration") or "").strip()
        duration = float(duration_raw) if duration_raw else profile["default_duration_sec"]
        aspect = row.get("aspect") or pack.default_aspect

        seeds_raw = (row.get("seeds") or "").strip()
        seeds = [int(s.strip()) for s in seeds_raw.split(",") if s.strip()]
        if not seeds:
            seeds = pack.default_seeds

        extra_neg = row.get("_extra_negative", "")

        for seed in seeds:
            job_id = f"{row_id}_s{seed}"
            if job_id in seen_ids:
                raise ValueError(f"Duplicate job_id '{job_id}' in pack '{pack.name}'")
            seen_ids.add(job_id)

            job = BatchJob(
                job_id=job_id,
                row_id=row_id,
                subject=row.get("subject", ""),
                action=row.get("action", ""),
                environment=row.get("environment", ""),
                preset=preset,
                motion=motion,
                duration_sec=duration,
                aspect_ratio=aspect,
                seed=seed,
            )
            job.extra_negative = extra_neg
            job.pack_name = pack.name
            job.pack_row = dict(pack_row)  # full original CSV row for publish helper
            jobs.append(job)

    return jobs
