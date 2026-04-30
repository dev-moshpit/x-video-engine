"""Batches — inspect a batch's manifest, star/reject clips, export selection."""

from __future__ import annotations

import sys as _sys
import webbrowser
from pathlib import Path

import streamlit as st

_sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ui._shared import (
    BATCHES_ROOT, SCRIPTS, list_batches, load_manifest, load_selection,
    py_script, rel_to_root, run_live, save_selection,
)

st.set_page_config(page_title="Batches", page_icon="📦", layout="wide")
st.title("Batches")

batches = list_batches()
if not batches:
    st.info(f"No batches yet under `{rel_to_root(BATCHES_ROOT)}`.")
    st.stop()

# ─── Picker ─────────────────────────────────────────────────────────────
options = [f"{b.name}  ·  {b.mtime_iso}  ·  {b.completed}/{b.total}"
           for b in batches]
idx = st.selectbox(
    "Select batch", range(len(options)),
    format_func=lambda i: options[i], key="batch_picker",
)
batch = batches[idx]
clips_dir = batch.path / "clips"

# ─── Top metrics for this batch ─────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total", batch.total)
c2.metric("Done", batch.completed)
c3.metric("Failed", batch.failed)
c4.metric("clips/min", batch.clips_per_minute or "—")
c5.metric("Starred", batch.starred)

colg, cole = st.columns(2)
with colg:
    gallery_path = batch.path / "index.html"
    if gallery_path.exists():
        if st.button("🖼  Open gallery in browser", use_container_width=True):
            webbrowser.open(gallery_path.as_uri())
            st.toast("Opened gallery in your default browser.")
    else:
        st.caption("No gallery index.html in this batch.")
with cole:
    if batch.has_selection:
        if st.button("📤  Export selection (publish_ready.csv/json)",
                     use_container_width=True):
            log = st.empty()
            code = run_live(
                py_script([str(SCRIPTS["export"]),
                           "--batch-dir", str(batch.path)]),
                log,
            )
            (st.success if code == 0 else st.error)(f"export exit={code}")
    else:
        st.caption("No selection.json yet — star some clips below first.")

st.divider()

# ─── Manifest + selection UI ────────────────────────────────────────────
manifest = load_manifest(batch.path)
selection = load_selection(batch.path)
starred_set = set(selection.get("starred", []))
rejected_set = set(selection.get("rejected", []))

if not manifest:
    st.warning("No manifest.csv in this batch.")
    st.stop()

# Visible columns
view_cols = [
    "star", "reject", "job_id", "preset", "motion", "format",
    "seed", "duration_sec", "status", "title", "caption", "hashtags",
]

table_rows: list[dict] = []
for row in manifest:
    jid = row.get("job_id", "")
    table_rows.append({
        "star":         jid in starred_set,
        "reject":       jid in rejected_set,
        "job_id":       jid,
        "preset":       row.get("preset", ""),
        "motion":       row.get("motion", ""),
        "format":       row.get("format", ""),
        "seed":         row.get("seed", ""),
        "duration_sec": row.get("duration_sec", ""),
        "status":       row.get("status", ""),
        "title":        (row.get("title") or "")[:80],
        "caption":      (row.get("caption") or "")[:120],
        "hashtags":     (row.get("hashtags") or "")[:100],
    })

edited = st.data_editor(
    table_rows,
    use_container_width=True,
    disabled=[c for c in view_cols if c not in ("star", "reject")],
    hide_index=True,
    column_config={
        "star":   st.column_config.CheckboxColumn("★",  width="small"),
        "reject": st.column_config.CheckboxColumn("✕",  width="small"),
    },
    key=f"manifest_editor_{batch.name}",
)

col_save, col_preview = st.columns([1, 3])
with col_save:
    if st.button("💾 Save selection", type="primary", use_container_width=True):
        starred = [r["job_id"] for r in edited if r.get("star") and not r.get("reject")]
        rejected = [r["job_id"] for r in edited if r.get("reject")]
        save_selection(batch.path, starred, rejected)
        st.success(f"Saved: {len(starred)} starred, {len(rejected)} rejected.")
with col_preview:
    st.caption(
        "Tick ★ to star or ✕ to reject, then Save selection. "
        "Starred clips feed into Final Exports."
    )

# ─── Preview row ────────────────────────────────────────────────────────
st.divider()
st.subheader("Preview starred clips")

current_starred = [r["job_id"] for r in edited if r.get("star")]
if not current_starred:
    st.caption("Star some clips above to preview them here.")
else:
    # Show up to 6 in 3-column grid
    preview_ids = current_starred[:6]
    cols = st.columns(min(3, len(preview_ids)))
    for i, jid in enumerate(preview_ids):
        clip = clips_dir / f"{jid}.mp4"
        col = cols[i % len(cols)]
        with col:
            if clip.exists():
                st.video(str(clip))
                st.caption(f"`{jid}`")
            else:
                st.warning(f"Missing: {rel_to_root(clip)}")
    if len(current_starred) > 6:
        st.caption(f"+ {len(current_starred) - 6} more starred (not shown).")
