"""LowPoly Shorts — operator dashboard.

Run:
    streamlit run ui/app.py

Source of truth is still the CLI; this UI wraps:
    - scripts/run_shorts_batch.py
    - scripts/export_selection.py
    - scripts/render_final_video.py

Navigate via the sidebar to New Batch / Batches / Final Exports.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

# Keep `from ui._shared import ...` working when launched via `streamlit run ui/app.py`
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui._shared import (
    BATCHES_ROOT, list_batches, list_formats, list_packs, rel_to_root,
)

st.set_page_config(
    page_title="LowPoly Shorts",
    page_icon="🎬",
    layout="wide",
)

st.title("LowPoly Shorts — Dashboard")
st.caption(
    "Local operator control panel. Pages in the sidebar wrap the CLI: "
    "New Batch → Batches → Final Exports."
)

packs = list_packs()
formats = list_formats()
batches = list_batches()

# ─── Top metrics ────────────────────────────────────────────────────────
total_clips = sum(b.completed for b in batches)
total_starred = sum(b.starred for b in batches)
batches_with_finals = sum(1 for b in batches if b.has_final_exports)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Packs", len(packs))
col2.metric("Formats", len(formats))
col3.metric("Batches", len(batches))
col4.metric("Clips rendered", total_clips)
col5.metric("Starred winners", total_starred)

st.divider()

# ─── Packs + Formats side-by-side ───────────────────────────────────────
col_l, col_r = st.columns(2, gap="large")

with col_l:
    st.subheader("Content Packs")
    if not packs:
        st.info("No packs found in content_packs/.")
    else:
        for p in packs:
            with st.container(border=True):
                st.markdown(f"**{p['title']}**  `{p['name']}`")
                st.caption(
                    f"Required: {', '.join(p['required']) or '—'}  "
                    f"·  Presets: {', '.join(p['presets'])}  "
                    f"·  Motion: {', '.join(p['motion'])}"
                )

with col_r:
    st.subheader("Social Formats")
    if not formats:
        st.info("No formats found in xvideo/formats/.")
    else:
        for f in formats:
            with st.container(border=True):
                window = ""
                if f["duration_min"] or f["duration_max"]:
                    window = f" · duration {f['duration_min']}-{f['duration_max']}s"
                st.markdown(f"**{f['name']}**  `primary={f['primary']}`")
                st.caption(
                    f"motion_bias: {f['motion_bias']}{window}"
                )
                st.caption(f["description"])

st.divider()

# ─── Recent batches table ───────────────────────────────────────────────
st.subheader("Recent Batches")
if not batches:
    st.info(f"No batches yet. Use **New Batch** to run one. (Looking in: `{rel_to_root(BATCHES_ROOT)}`)")
else:
    rows = []
    for b in batches[:20]:
        status = "✅" if b.completed and not b.failed else ("⚠️" if b.failed else "·")
        rows.append({
            "Batch": b.name,
            "When": b.mtime_iso,
            "Status": status,
            "Done": f"{b.completed}/{b.total}" if b.total else "—",
            "Failed": b.failed,
            "clips/min": b.clips_per_minute or "—",
            "Starred": b.starred if b.has_selection else "—",
            "Finals": "✅" if b.has_final_exports else "—",
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)

    st.caption(
        "Open **Batches** to view a batch's gallery, star winners, and "
        "export the selection. Open **Final Exports** to produce finished "
        "uploadable MP4s with voice + captions."
    )
