"""New Batch — pick a pack + format, scaffold a CSV, run the batch."""

from __future__ import annotations

import csv
import sys as _sys
from pathlib import Path

import streamlit as st

_sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ui._shared import (
    PACKS_ROOT, RUNS_ROOT, SCRIPTS, list_formats, list_packs,
    py_script, rel_to_root, run_live,
)

st.set_page_config(page_title="New Batch", page_icon="🎬", layout="wide")
st.title("New Batch")

packs = list_packs()
formats = list_formats()
pack_names = [p["name"] for p in packs]
fmt_names = ["(none)"] + [f["name"] for f in formats]

if not packs:
    st.error("No packs found under `content_packs/`. Nothing to run.")
    st.stop()


# ─── Selection ──────────────────────────────────────────────────────────
c1, c2, c3 = st.columns([2, 2, 1])
with c1:
    pack_name = st.selectbox("Pack", pack_names, index=0, key="new_batch_pack")
with c2:
    fmt_choice = st.selectbox("Format", fmt_names, index=0, key="new_batch_fmt")
with c3:
    rows_n = st.number_input("Rows to scaffold", min_value=1, max_value=50,
                              value=10, step=1, key="new_batch_rows")

pack = next(p for p in packs if p["name"] == pack_name)
fmt = None
if fmt_choice != "(none)":
    fmt = next(f for f in formats if f["name"] == fmt_choice)

with st.expander("Pack details", expanded=False):
    st.write(pack)
if fmt:
    with st.expander("Format details", expanded=False):
        st.write(fmt)

st.divider()


# ─── Step 1: scaffold an editable CSV ───────────────────────────────────
st.subheader("1. Scaffold input CSV")

# Stable per-pack working dir so re-opens don't lose edits
work_dir = RUNS_ROOT / f"{pack_name}_ui"
csv_path = work_dir / "input.csv"

col_init, col_path = st.columns([1, 3])
with col_init:
    init_clicked = st.button("Init pack (refresh starter rows)", type="secondary")
with col_path:
    st.caption(f"Working dir: `{rel_to_root(work_dir)}`  ·  CSV: `{rel_to_root(csv_path)}`")

if init_clicked or not csv_path.exists():
    work_dir.mkdir(parents=True, exist_ok=True)
    tpl = PACKS_ROOT / pack_name / "template.csv"
    if not tpl.exists():
        st.error(f"Template missing: {rel_to_root(tpl)}")
        st.stop()
    with open(tpl, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        template_rows = list(reader)
    # Shape to requested N (truncate, or cycle with _v2/_v3 suffix)
    shaped: list[dict] = []
    for i in range(rows_n):
        base = dict(template_rows[i % len(template_rows)])
        cycle = i // len(template_rows)
        if cycle > 0:
            rid = (base.get("id") or f"{pack_name}_row{i+1}").strip()
            base["id"] = f"{rid}_v{cycle+1}"
        shaped.append(base)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(shaped)
    st.toast(f"Wrote {len(shaped)} rows → {csv_path.name}")

# Load current CSV into data_editor
with open(csv_path, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    current_fields = list(reader.fieldnames or [])
    current_rows = list(reader)

edited = st.data_editor(
    current_rows,
    num_rows="dynamic",
    key=f"editor_{pack_name}",
    use_container_width=True,
)

if st.button("💾 Save CSV edits", type="primary"):
    # Preserve original column order
    fields = current_fields
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        # edited is a list of dicts; drop any entirely-empty rows
        kept = [r for r in edited if any((str(v) or "").strip() for v in r.values())]
        w.writerows(kept)
    st.success(f"Saved {len(kept)} rows.")

st.divider()


# ─── Step 2: run (dry or full) ──────────────────────────────────────────
st.subheader("2. Run batch")

col_name, col_backlog = st.columns([3, 1])
with col_name:
    batch_name = st.text_input(
        "Batch name", value=f"{pack_name}_{fmt_choice if fmt else 'nofmt'}_run",
        key="new_batch_name",
    )
with col_backlog:
    allow_backlog = st.checkbox("--allow-backlog", value=False)

col_dry, col_run = st.columns(2)
dry_clicked = col_dry.button("🧪 Dry run", use_container_width=True)
run_clicked = col_run.button("▶️ Run full batch",
                              type="primary", use_container_width=True)

def _base_cmd() -> list[str]:
    cmd = py_script([str(SCRIPTS["batch"]),
                     "--pack", pack_name,
                     "--csv", str(csv_path),
                     "--batch-name", batch_name.strip() or f"{pack_name}-run"])
    if fmt:
        cmd += ["--format", fmt["name"]]
    if allow_backlog:
        cmd.append("--allow-backlog")
    return cmd


if dry_clicked:
    st.caption("Running dry-run (no SDXL)…")
    log = st.empty()
    code = run_live(_base_cmd() + ["--dry-run"], log)
    (st.success if code == 0 else st.error)(f"Dry run exit={code}")

if run_clicked:
    st.warning("Full render starts SDXL-Turbo. ~20s per clip. Keep this tab open.")
    log = st.empty()
    code = run_live(_base_cmd(), log)
    if code == 0:
        st.success(f"Batch complete. Open **Batches** page to review "
                   f"`cache/batches/{batch_name}`.")
    else:
        st.error(f"Batch exit={code}. See log above.")
