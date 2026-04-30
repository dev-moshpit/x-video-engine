# LowPoly Shorts Engine

> **New prompt in. New original video out. Every time.**

Type a prompt. Get a fully-finished 9:16 vertical Short — original concept,
original scene plan, original voiceover, captions, hook overlay, single MP4.
The same prompt produces a different video every time unless you pin a
creative seed.

```
"Make a motivational video about discipline. Cinematic, intense."
                                ↓
            [VideoPlan: title / hook / 5-7 scenes / VO / CTA]
                                ↓
              [SDXL-Turbo + parallax → scene clips]
                                ↓
                  [TTS → word-level captions]
                                ↓
                    [hook overlay → final MP4]
```

Optimised for laptop GPUs (validated on GTX 1650 4 GB). No cloud dependency
for generation; cloud fallback (RTX 2080 LAN worker) is available for
heavier model variants.

## Quickstart

```bash
pip install -r requirements.txt

# Generate one brand-new video (plan + scenes only)
python scripts/generate_prompt_video.py \
    --prompt "Make a motivational video about discipline"

# Same thing but produce the final MP4 (TTS + captions + hook + mux)
python scripts/generate_prompt_video.py \
    --prompt "Make a motivational video about discipline" --finish

# Generate 5 distinct creative directions for the same prompt
python scripts/generate_prompt_video.py \
    --prompt "AI tools are replacing boring work" --variations 5 --finish

# Reproduce a specific plan exactly (pin the seed)
python scripts/generate_prompt_video.py \
    --prompt "Luxury villa open house in Dubai" \
    --format reels_aesthetic --seed 1234 --finish

# Plan-only mode (no GPU): inspect the creative direction
python scripts/generate_prompt_video.py --prompt "..." --dry-run

# Operator UI
streamlit run ui/app.py
# Open http://localhost:8501 → Prompt-to-Video Factory page
```

## Prompt-Native architecture

The primary path lives in [`xvideo/prompt_native/`](xvideo/prompt_native/):

| Module | Role |
|--------|------|
| [`schema.py`](xvideo/prompt_native/schema.py) | `VideoPlan` / `Scene` / `RenderJob` |
| [`director.py`](xvideo/prompt_native/director.py) | `generate_video_plan(prompt, …)` — no LLM |
| [`variation_engine.py`](xvideo/prompt_native/variation_engine.py) | Seed math + concept mutators |
| [`script_engine.py`](xvideo/prompt_native/script_engine.py) | Hook / VO / CTA composition |
| [`scene_engine.py`](xvideo/prompt_native/scene_engine.py) | Scene count + duration distribution |
| [`visual_prompt_engine.py`](xvideo/prompt_native/visual_prompt_engine.py) | SDXL prompt + global negative |
| [`motion_engine.py`](xvideo/prompt_native/motion_engine.py) | camera_motion → parallax profile |
| [`caption_style_engine.py`](xvideo/prompt_native/caption_style_engine.py) | 6 caption styles (ASS) |
| [`safety_filters.py`](xvideo/prompt_native/safety_filters.py) | Prompt sanitisation + plan audit |
| [`scoring.py`](xvideo/prompt_native/scoring.py) | Heuristic plan QA + threshold gate |
| [`plan_renderer_bridge.py`](xvideo/prompt_native/plan_renderer_bridge.py) | VideoPlan → finished MP4 |

Variation comes from a *combinatorial concept graph* (archetype × setting
× moment × tension × resolution × camera lens × visual style × palette ×
pacing) seeded by `prompt_hash` + a fresh-per-call OS-entropy seed. No LLM
required at runtime; `--planner llm` is reserved for future LLM backends.

## Caption styles (6)

`bold_word` (default for shorts_clean) · `kinetic_word` (default for
tiktok_fast) · `clean_subtitle` (default for reels_aesthetic) ·
`impact_uppercase` · `minimal_lower_third` · `karaoke_3word`. Pick one
with `--caption-style <name>`. Each writes a libass-compatible `.ass`
file burned in by ffmpeg.

## Music bed (optional)

Drop royalty-free instrumental loops in [`assets/music/`](assets/music/),
then pass `--music-bed auto` (or a literal path). Mixed under voice at
`-18 dB`, faded in/out, looped to fit. Default is `none`.

## Legacy pack mode (still supported)

The 6 content packs (`motivational_quotes`, `ai_facts`,
`history_mystery`, `product_teaser`, `music_visualizer`, `abstract_loop`)
remain available for bulk daily content. They live under the *Advanced*
expander in the UI and behind `scripts/run_shorts_batch.py` on the CLI:

```bash
python scripts/run_shorts_batch.py \
    --pack motivational_quotes \
    --csv runs/motivational_quotes_2026-04-22/input.csv \
    --batch-name quotes-2026-04-22
```

The 6 packs × 3 formats = 18-combination regression matrix
(`scripts/e2e_smoke_matrix.py`) is unaffected by the prompt-native work.

## Tests

```bash
# Prompt-native unit tests (~20s)
python -m pytest tests/ -q

# Prompt-native end-to-end (no GPU by default, ~3s)
python scripts/e2e_prompt_native.py

# Pack-matrix regression
python scripts/e2e_smoke_matrix.py --dry-run
```

See [`LAUNCH_MATRIX.md`](LAUNCH_MATRIX.md) for the full production
checklist (output layout, KPIs, motion profiles, ship presets, content
packs, social-format presets, post-production pipeline) and
[`LOWPOLY_VISION.md`](LOWPOLY_VISION.md) for the original architecture.
