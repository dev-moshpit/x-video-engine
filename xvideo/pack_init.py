"""Initialize a pack working directory with a ready-to-edit CSV + README.

One command → ready-to-edit CSV with real ideas. The pack's shipped
`template.csv` is already a curated set of high-quality starter rows, so
init copies that into a dated working folder. `--rows N` truncates or
cycles (with unique ID suffixes) to hit the requested row count.
"""

from __future__ import annotations

import csv
import datetime as _dt
import re
from pathlib import Path

from xvideo.packs import PackConfig, load_pack


def _unique_output_dir(base: Path, pack_name: str, date_str: str) -> Path:
    candidate = base / f"{pack_name}_{date_str}"
    if not candidate.exists():
        return candidate
    i = 2
    while True:
        c = base / f"{pack_name}_{date_str}-{i}"
        if not c.exists():
            return c
        i += 1


def _read_template(pack: PackConfig) -> tuple[list[str], list[dict]]:
    tpl = pack.pack_dir / "template.csv"
    if not tpl.exists():
        raise FileNotFoundError(f"Pack template missing: {tpl}")
    with open(tpl, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if not rows:
        raise ValueError(f"Pack template has no rows: {tpl}")
    return fieldnames, rows


def _shape_rows(rows: list[dict], pack_name: str, n: int | None) -> list[dict]:
    """Return exactly n rows, or all rows if n is None.

    n > len(rows): cycle template rows with unique id suffixes (`_v2`, `_v3`…)
    n < len(rows): take first n
    """
    if n is None or n == len(rows):
        return [dict(r) for r in rows]
    if n <= 0:
        raise ValueError("--rows must be positive")
    if n < len(rows):
        return [dict(r) for r in rows[:n]]
    out: list[dict] = []
    for i in range(n):
        base = dict(rows[i % len(rows)])
        cycle = i // len(rows)
        if cycle > 0:
            rid = (base.get("id") or f"{pack_name}_row{i+1}").strip()
            base["id"] = f"{rid}_v{cycle+1}"
        out.append(base)
    return out


def _column_for_table(pack: PackConfig, table_name: str) -> str | None:
    """Find which CSV column keys into TABLE by scanning row_transformer
    and publish templates."""
    pattern = re.compile(rf"\b{re.escape(table_name)}\[(\w+)\]")
    for tpl in pack.row_transformer.values():
        m = pattern.search(tpl)
        if m:
            return m.group(1)
    pub = pack.raw_config.get("publish", {})
    for section in ("title_templates", "caption_templates"):
        for tpl in pub.get(section, {}).values():
            m = pattern.search(tpl)
            if m:
                return m.group(1)
    return None


def _render_readme(pack: PackConfig, csv_name: str, row_count: int) -> str:
    lines: list[str] = [
        f"Pack: {pack.name}",
        f"Title: {pack.title}",
        "",
        pack.description,
        "",
        "Required columns:",
    ]
    for col in pack.required_columns:
        lines.append(f"  - {col}")

    if pack.tables:
        lines.append("")
        lines.append("Valid values for table-driven columns:")
        for tname, entries in pack.tables.items():
            col = _column_for_table(pack, tname) or tname.lower()
            keys = list(entries.keys())
            lines.append(f"  {col:<14} ({tname}): {', '.join(keys)}")

    lines += [
        "",
        "Optional columns (blank = pack default):",
        f"  preset    allowed: {', '.join(pack.allowed_presets)}",
        f"  motion    allowed: {', '.join(pack.allowed_motion)}",
        f"  duration  blank = motion profile default",
        f"  aspect    default {pack.default_aspect}",
        f"  seeds     default {','.join(str(s) for s in pack.default_seeds)}"
        " (each seed = one variant clip)",
        "",
        f"Rows pre-filled: {row_count}  (edit {csv_name} before running)",
        "",
        "Run:",
        f"  python scripts/run_shorts_batch.py --pack {pack.name} \\",
        f"      --csv {csv_name} --batch-name <batch_name>",
        "",
        "Dry-run first (no rendering, just print the job plan):",
        f"  python scripts/run_shorts_batch.py --pack {pack.name} \\",
        f"      --csv {csv_name} --dry-run",
        "",
        "Tips:",
        "  - visual_subject should be concrete: \"a faceted fox\", \"a low-poly castle\".",
        "  - Keep subjects 3-6 words. The prompt compiler handles style + environment.",
        "  - Multiple seeds per row = free A/B variants.",
    ]
    return "\n".join(lines) + "\n"


def init_pack_dir(
    pack_name: str,
    packs_root: Path,
    out_dir: Path,
    rows: int | None = None,
) -> Path:
    """Materialize a ready-to-edit working folder for a pack.

    Returns the created folder path.
    """
    pack = load_pack(pack_name, packs_root)
    fieldnames, template_rows = _read_template(pack)
    shaped = _shape_rows(template_rows, pack_name, rows)

    out_dir.mkdir(parents=True, exist_ok=True)
    today = _dt.date.today().isoformat()
    target = _unique_output_dir(out_dir, pack_name, today)
    target.mkdir(parents=True, exist_ok=False)

    csv_path = target / "input.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in shaped:
            writer.writerow({k: r.get(k, "") for k in fieldnames})

    readme = _render_readme(pack, csv_path.name, len(shaped))
    (target / "README.txt").write_text(readme, encoding="utf-8")

    return target
