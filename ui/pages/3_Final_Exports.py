"""Final Exports — voice + captions + hook composite for starred clips."""

from __future__ import annotations

import sys as _sys
import webbrowser
from pathlib import Path

import streamlit as st

_sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ui._shared import (
    SCRIPTS, list_batches, py_script, rel_to_root, run_live,
)

st.set_page_config(page_title="Final Exports", page_icon="🎞️", layout="wide")
st.title("Final Exports")
st.caption(
    "Compose starred clips into uploadable MP4s: voiceover + burned "
    "captions + hook overlay. Wraps `scripts/render_final_video.py`."
)

batches = list_batches()
eligible = [b for b in batches if b.has_selection and b.starred > 0]

if not eligible:
    st.info(
        "No batches have a saved selection with starred clips yet. Go to "
        "**Batches**, star some winners, then come back here."
    )
    st.stop()

options = [f"{b.name}  ·  ⭐ {b.starred}  ·  {b.mtime_iso}" for b in eligible]
idx = st.selectbox(
    "Select batch", range(len(options)),
    format_func=lambda i: options[i], key="final_picker",
)
batch = eligible[idx]

# ─── Controls ───────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
with c1:
    caption_mode = st.radio(
        "Caption mode",
        ("line", "word"),
        index=1,
        horizontal=True,
        help="'line' = one sentence at a time (SRT). 'word' = per-word ASS "
             "bold single-word bottom-center (Shorts/TikTok style).",
    )
with c2:
    want_voice = st.toggle("Voice on", value=True)
    want_hook = st.toggle("Hook overlay", value=True)
with c3:
    want_captions = st.toggle("Captions on", value=True)
    limit = st.number_input("Limit (0 = all starred)", min_value=0,
                             max_value=100, value=0, step=1)

voice_name = st.text_input(
    "Override voice (blank = pack default)",
    value="", placeholder="e.g. en-US-ChristopherNeural",
)
voice_rate = st.text_input("Voice rate", value="+0%", help="edge-tts format: '+10%', '-5%'")

st.divider()

# ─── Run ────────────────────────────────────────────────────────────────
if st.button("🎬  Render finals", type="primary", use_container_width=True):
    cmd = py_script([str(SCRIPTS["final"]),
                     "--batch-dir", str(batch.path),
                     "--caption-mode", caption_mode,
                     "--voice", "on" if want_voice else "off",
                     "--captions", "on" if want_captions else "off",
                     "--hook", "on" if want_hook else "off",
                     "--voice-rate", voice_rate])
    if voice_name.strip():
        cmd += ["--voice-name", voice_name.strip()]
    if limit > 0:
        cmd += ["--limit", str(limit)]

    log = st.empty()
    code = run_live(cmd, log)
    if code == 0:
        st.success("Render complete. Scroll down to preview.")
    else:
        st.error(f"Render exit={code}. See log above.")

st.divider()

# ─── Preview existing final_exports ─────────────────────────────────────
st.subheader("Finished exports")
final_dir = batch.path / "final_exports"
if not final_dir.is_dir():
    st.caption("No finals rendered yet for this batch.")
else:
    mp4s = sorted(final_dir.glob("*_final.mp4"))
    if not mp4s:
        st.caption("final_exports/ exists but no _final.mp4 files yet.")
    else:
        col_open, _ = st.columns([1, 3])
        with col_open:
            if st.button("📂  Open final_exports folder",
                         use_container_width=True):
                webbrowser.open(final_dir.as_uri())
                st.toast("Opened folder in file manager.")

        st.caption(f"{len(mp4s)} finished clip(s) in "
                   f"`{rel_to_root(final_dir)}`")
        # Show 3-col grid of video previews
        cols = st.columns(min(3, len(mp4s)))
        for i, mp4 in enumerate(mp4s):
            col = cols[i % len(cols)]
            with col:
                st.video(str(mp4))
                st.caption(f"`{mp4.name}`")
