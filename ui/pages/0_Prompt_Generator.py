"""Prompt-to-Video Factory — primary surface for prompt-native generation.

Promise: NEW PROMPT = NEW ORIGINAL VIDEO EVERY TIME.

Type a prompt. Click *Generate New Video*. A complete VideoPlan is composed
(title / hook / scene plan / voiceover / CTA / motion / caption style)
from a fresh seeded direction. Same prompt → different plan every time
unless a fixed seed is supplied.

The legacy pack-routed flow (route prompt → CSV rows in one of the 6
content packs) is still here under *Advanced: legacy pack mode* for
compatibility with the existing batch tools and the e2e regression
matrix. It is no longer the primary surface.
"""

from __future__ import annotations

import csv
import json
import sys as _sys
from pathlib import Path

import streamlit as st

_sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ui._shared import (
    BATCHES_ROOT, RUNS_ROOT, SCRIPTS, list_formats, list_packs, py_script,
    rel_to_root, run_live,
)
from xvideo.prompt_native import (
    CAPTION_STYLES,
    available_themes,
    default_caption_style_for,
    generate_video_plan,
    plan_meets_thresholds,
    score_plan,
)
from xvideo.prompt_native.safety_filters import audit_plan
from xvideo.prompt_planner import plan_from_prompt


PROMPT_VIDEO_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "generate_prompt_video.py"
)


st.set_page_config(page_title="Prompt-to-Video Factory",
                    page_icon="✨", layout="wide")
st.title("Prompt-to-Video Factory")
st.caption(
    "Type a prompt. Get a brand-new original video — fresh concept, fresh "
    "scene plan, fresh voiceover, fresh final MP4. Same prompt produces a "
    "different video every time unless you pin a seed."
)


# ─── Input panel ────────────────────────────────────────────────────────

formats = list_formats()
fmt_choices = [f["name"] for f in formats] or ["shorts_clean"]

user_prompt = st.text_area(
    "Describe the video you want…",
    value=st.session_state.get(
        "prompt_text",
        "Make a motivational video about discipline. Cinematic, intense.",
    ),
    height=120,
    key="prompt_text",
    help="Style cues like \"intense\", \"dreamy\", \"cinematic\", \"neon\", "
         "\"pastel\" steer the look.",
)

c1, c2, c3, c4 = st.columns([2, 2, 1.2, 1.6])
with c1:
    fmt_choice = st.selectbox(
        "Platform",
        fmt_choices,
        index=(fmt_choices.index("shorts_clean") if "shorts_clean" in fmt_choices else 0),
        help="Drives target duration + primary platform.",
    )
with c2:
    style_pref = st.text_input(
        "Style preference (optional)",
        value="",
        help="Extra cue layered on top of the prompt, e.g. \"cinematic\" or \"dreamy\".",
    )
with c3:
    duration = st.number_input(
        "Duration (s)", min_value=8.0, max_value=60.0, value=20.0, step=1.0,
        help="Target length of the final stitched MP4.",
    )
with c4:
    fixed_seed = st.text_input(
        "Creative seed (optional)",
        value="",
        help="Leave blank for a fresh direction every click. Set to "
             "reproduce a specific plan exactly.",
    )

c5, c6, c7 = st.columns([2, 2, 2])
with c5:
    caption_style_choice = st.selectbox(
        "Caption style",
        ["(auto)"] + CAPTION_STYLES,
        index=0,
        help="Lower-third caption look. Auto picks per platform.",
    )
with c6:
    music_bed_choice = st.selectbox(
        "Music bed",
        ["none", "auto"],
        index=0,
        help="Optional royalty-free loop under voice. 'auto' picks from "
             "assets/music/ if any files are present.",
    )
with c7:
    score_filter = st.toggle(
        "Score & filter weak plans",
        value=False,
        help="Run heuristic QA on each plan and regenerate if below "
             "threshold (hook, scene variety, total >= 70).",
    )


def _parse_seed(s: str) -> int | None:
    s = s.strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        st.warning(f"Ignoring non-integer creative seed: {s}")
        return None


# ─── Generate buttons ───────────────────────────────────────────────────

if "pn_plans" not in st.session_state:
    st.session_state["pn_plans"] = []
if "pn_scores" not in st.session_state:
    st.session_state["pn_scores"] = []

b1, b2, b3 = st.columns(3)

with b1:
    if st.button("✨  Generate New Video", type="primary", use_container_width=True):
        plans = generate_video_plan(
            prompt=user_prompt,
            platform=fmt_choice,
            duration=duration,
            style=(style_pref or None),
            seed=_parse_seed(fixed_seed),
            variations=1,
            score_and_filter=score_filter,
        )
        st.session_state["pn_plans"] = [p.to_dict() for p in plans]
        st.session_state["pn_scores"] = [score_plan(p).to_dict() for p in plans]

with b2:
    if st.button("🎬  Generate 5 Fresh Videos", use_container_width=True):
        plans = generate_video_plan(
            prompt=user_prompt,
            platform=fmt_choice,
            duration=duration,
            style=(style_pref or None),
            seed=_parse_seed(fixed_seed),
            variations=5,
            score_and_filter=score_filter,
        )
        st.session_state["pn_plans"] = [p.to_dict() for p in plans]
        st.session_state["pn_scores"] = [score_plan(p).to_dict() for p in plans]

with b3:
    n_existing = len(st.session_state.get("pn_plans", []))
    if st.button(f"🧹  Clear ({n_existing})", use_container_width=True,
                  disabled=(n_existing == 0)):
        st.session_state["pn_plans"] = []
        st.session_state["pn_scores"] = []
        st.rerun()

st.divider()


# ─── Plan display ───────────────────────────────────────────────────────

plans: list[dict] = st.session_state.get("pn_plans", [])
scores: list[dict] = st.session_state.get("pn_scores", [])

if not plans:
    st.info(
        "Type a prompt above and click **Generate New Video** to start. "
        "Every click produces a fresh creative direction unless you set a "
        "creative seed. Use **Generate 5 Fresh Videos** to fan out five "
        "distinct directions and pick the strongest before you render."
    )
else:
    st.markdown(f"### Generated plans  ·  {len(plans)}")
    if len(plans) == 1:
        plan_tabs = [st.container(border=True)]
    else:
        labels = [f"#{i + 1}: {p['title'][:34]}" for i, p in enumerate(plans)]
        plan_tabs = st.tabs(labels)

    # Default caption style for this format (used if caption_style_choice == "(auto)")
    auto_caption_style = default_caption_style_for(fmt_choice)
    chosen_caption_style = (
        auto_caption_style if caption_style_choice == "(auto)"
        else caption_style_choice
    )

    for tab, plan, score in zip(plan_tabs, plans, scores or [{}] * len(plans)):
        with tab:
            top1, top2 = st.columns([3, 1])
            with top1:
                st.markdown(f"**{plan['title']}**")
                st.caption(
                    f"theme=`{plan['theme']}` · style=`{plan['visual_style']}` · "
                    f"palette=`{plan['color_palette']}` · pacing=`{plan['pacing']}` · "
                    f"voice=`{plan['voice_tone']}` · seed=`{plan['seed']}` · "
                    f"hash=`{plan['prompt_hash']}` · variation=`{plan['variation_id']}`"
                )
            with top2:
                st.metric("Scenes", len(plan["scenes"]))

            # Score banner
            if score:
                total = score.get("total", 0.0)
                badge = "🟢 PASS" if total >= 70 else "🟡 LOW"
                st.caption(
                    f"{badge}  total={total:.1f}/100 · "
                    f"hook={score.get('hook_strength', 0):.1f} · "
                    f"variety={score.get('scene_variety', 0):.1f} · "
                    f"relevance={score.get('prompt_relevance', 0):.1f}"
                )
                if score.get("notes"):
                    with st.expander("Score notes", expanded=False):
                        for n in score["notes"]:
                            st.caption(f"· {n}")

            cc1, cc2 = st.columns(2)
            with cc1:
                st.markdown("**Concept**")
                st.write(plan["concept"])
                st.markdown("**Hook**")
                st.write(plan["hook"])
                st.markdown("**Emotional angle**")
                st.write(plan["emotional_angle"])
                st.markdown("**Audience**")
                st.write(plan["audience"])
            with cc2:
                st.markdown("**Voiceover**")
                for line in plan["voiceover_lines"]:
                    st.write(f"· {line}")
                st.markdown("**Call to action**")
                st.write(plan["cta"])

            st.markdown("**Scene plan**")
            scene_table = [
                {
                    "scene": s["scene_id"],
                    "duration": s["duration"],
                    "subject": s["subject"],
                    "environment": s["environment"],
                    "camera": s["camera_motion"],
                    "transition": s["transition"],
                    "caption": s["on_screen_caption"],
                    "narration": s["narration_line"],
                }
                for s in plan["scenes"]
            ]
            st.dataframe(scene_table, use_container_width=True, hide_index=True)

            with st.expander("Visual prompts (per scene)"):
                for s in plan["scenes"]:
                    st.code(f"[{s['scene_id']}] {s['visual_prompt']}", language="text")

            with st.expander("Negative prompt + raw plan JSON"):
                st.code(plan["negative_prompt"], language="text")
                st.json(plan)

            # Soft warnings from the audit (non-blocking)
            try:
                from xvideo.prompt_native.schema import VideoPlan as _VP, Scene as _S

                def _hydrate(d):
                    sc = [_S(**dict(s)) for s in d["scenes"]]
                    other = {k: v for k, v in d.items() if k != "scenes"}
                    return _VP(scenes=sc, **other)

                warnings = audit_plan(_hydrate(plan))
            except Exception:
                warnings = []
            if warnings:
                with st.expander(f"Audit warnings ({len(warnings)})"):
                    for w in warnings:
                        st.caption(f"⚠ {w}")

            # ── Render this plan ───────────────────────────────────────
            r1, r2, r3, r4 = st.columns([1, 1, 1, 1])
            with r1:
                voice_on = st.toggle(
                    "Voice", value=True,
                    key=f"voice_{plan['variation_id']}_{plan['prompt_hash']}",
                )
            with r2:
                captions_on = st.toggle(
                    "Captions", value=True,
                    key=f"cap_{plan['variation_id']}_{plan['prompt_hash']}",
                )
            with r3:
                hook_on = st.toggle(
                    "Hook overlay", value=True,
                    key=f"hook_{plan['variation_id']}_{plan['prompt_hash']}",
                )
            with r4:
                st.caption(f"Caption: `{chosen_caption_style}`")
                st.caption(f"Music: `{music_bed_choice}`")

            cmd_render = py_script([
                str(PROMPT_VIDEO_SCRIPT),
                "--prompt", plan["user_prompt"],
                "--format", plan["format_name"],
                "--variations", "1",
                "--seed", str(plan["seed"]),
                "--duration", str(plan["duration_target"]),
                "--voice", "on" if voice_on else "off",
                "--captions", "on" if captions_on else "off",
                "--hook", "on" if hook_on else "off",
                "--caption-style", chosen_caption_style,
                "--music-bed", music_bed_choice,
            ])

            br1, br2 = st.columns(2)
            with br1:
                if st.button(
                    f"🎥  Render Scenes — {plan['title'][:30]}",
                    use_container_width=True,
                    key=f"scenes_{plan['variation_id']}_{plan['prompt_hash']}",
                ):
                    st.warning(
                        "Stage 1: SDXL-Turbo scene clips only "
                        "(no voice / captions / final). Per-scene render ~20s."
                    )
                    log = st.empty()
                    code = run_live(cmd_render, log)
                    if code == 0:
                        st.success("Scenes rendered — see batch_dir/clips/")
                    else:
                        st.error(f"Render exit={code}.")

            with br2:
                if st.button(
                    f"🚀  Finish Final MP4 — {plan['title'][:30]}",
                    type="primary",
                    use_container_width=True,
                    key=f"render_{plan['variation_id']}_{plan['prompt_hash']}",
                ):
                    cmd_finish = cmd_render + ["--finish"]
                    st.warning(
                        "Stage 1+2: SDXL-Turbo scenes + TTS + captions + final MP4. "
                        "Keep this tab open."
                    )
                    log = st.empty()
                    code = run_live(cmd_finish, log)
                    if code == 0:
                        st.success(
                            "Final MP4 ready — check "
                            "`cache/batches/prompt_*/final_exports/`."
                        )
                    else:
                        st.error(f"Render exit={code}. See log above.")


# ─── Advanced: legacy pack-routed flow ──────────────────────────────────

st.divider()
with st.expander(
    "Advanced: legacy pack-routed prompt → CSV rows",
    expanded=False,
):
    st.caption(
        "The old behavior: route the prompt into one of the 6 packs "
        "(motivational_quotes, ai_facts, history_mystery, product_teaser, "
        "music_visualizer, abstract_loop) and emit pack CSV rows. Useful "
        "for bulk daily content with fixed-pack publishing or for the e2e "
        "regression matrix. The prompt-native path above is the default "
        "for one-off original videos."
    )
    packs = list_packs()
    pack_name_choices = ["auto"] + [p["name"] for p in packs]
    fmt_legacy_choices = ["(none)"] + fmt_choices

    lp1, lp2, lp3, lp4 = st.columns([2, 2, 1, 2])
    with lp1:
        legacy_pack = st.selectbox("Pack", pack_name_choices, index=0,
                                     key="legacy_pack")
    with lp2:
        legacy_fmt = st.selectbox("Format", fmt_legacy_choices, index=0,
                                    key="legacy_fmt")
    with lp3:
        legacy_count = st.number_input("Rows", min_value=1, max_value=50,
                                          value=5, step=1, key="legacy_count")
    with lp4:
        legacy_seeds = st.text_input("Seeds per row", value="42",
                                       key="legacy_seeds")

    if st.button("Generate pack rows (legacy)", use_container_width=True,
                 key="legacy_gen_btn"):
        try:
            seeds = [int(s.strip()) for s in legacy_seeds.split(",") if s.strip()] or [42]
            result = plan_from_prompt(
                user_prompt=user_prompt,
                pack=(None if legacy_pack == "auto" else legacy_pack),
                count=int(legacy_count),
                seeds=seeds,
            )
        except ValueError as e:
            st.error(f"Planner error: {e}")
            st.stop()
        st.session_state["legacy_rows"] = result.rows
        st.session_state["legacy_pack_resolved"] = result.pack
        st.session_state["legacy_notes"] = result.notes

    legacy_rows = st.session_state.get("legacy_rows", [])
    if legacy_rows:
        legacy_pack_resolved = st.session_state["legacy_pack_resolved"]
        legacy_notes = st.session_state.get("legacy_notes", [])
        st.caption(f"Routed to `{legacy_pack_resolved}`")
        for n in legacy_notes:
            st.caption(f"· {n}")
        edited = st.data_editor(
            legacy_rows, num_rows="dynamic", use_container_width=True,
            key=f"legacy_editor_{legacy_pack_resolved}",
        )
        work_dir = RUNS_ROOT / f"{legacy_pack_resolved}_prompt"
        csv_path = work_dir / "input.csv"

        lc1, lc2 = st.columns(2)
        with lc1:
            if st.button("💾 Save legacy CSV", use_container_width=True):
                work_dir.mkdir(parents=True, exist_ok=True)
                fields = list(legacy_rows[0].keys())
                kept = [r for r in edited
                         if any((str(v) or "").strip() for v in r.values())]
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=fields)
                    w.writeheader()
                    w.writerows(kept)
                st.success(f"Saved {len(kept)} rows → `{rel_to_root(csv_path)}`")
        with lc2:
            if st.button("▶️ Run legacy pack batch", use_container_width=True):
                if not csv_path.exists():
                    st.error("Save CSV first.")
                else:
                    cmd = py_script([
                        str(SCRIPTS["batch"]),
                        "--pack", legacy_pack_resolved,
                        "--csv", str(csv_path),
                        "--batch-name",
                        f"{legacy_pack_resolved}_legacy_" + (
                            legacy_fmt if legacy_fmt != "(none)" else "nofmt"
                        ),
                    ])
                    if legacy_fmt != "(none)":
                        cmd += ["--format", legacy_fmt]
                    log = st.empty()
                    code = run_live(cmd, log)
                    (st.success if code == 0 else st.error)(
                        f"Legacy batch exit={code}"
                    )
