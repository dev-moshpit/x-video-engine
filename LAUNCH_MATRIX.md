# LowPoly Shorts Engine — Production Status

**Status**: Product-stable. Full pipeline from prompt → original video → finished uploadable Short (voiceover + captions + hook + optional music bed). Prompt-native is the primary path; the legacy 6 packs × 3 formats = 18-combination pack matrix still ships green end-to-end as fallback / regression coverage.

**Product promise**: **New prompt in. New original video out. Every time. No templates. No pack picking. No recycled structure.**

## Prompt-Native Video Generation (primary)

One prompt produces a brand-new, fully-composed video from scratch — original concept, original scene plan, original voiceover script, original final MP4. Same prompt produces a different video on every call unless you pin a creative seed.

**Pipeline**:
```
prompt
  └─► creative brief        (title, hook, concept, audience, emotional angle)
       └─► scene plan       (4-8 scenes: subject, environment, camera motion,
                              transition, mood, on-screen caption, narration line,
                              full visual prompt)
            └─► render jobs (one SDXL-Turbo + parallax background clip per scene)
                 └─► voiceover (edge-tts on the full narration)
                      └─► chosen caption style (6 styles, e.g. bold_word /
                            kinetic_word / clean_subtitle / impact_uppercase /
                            minimal_lower_third / karaoke_3word)
                           └─► optional music bed (-18 dB under voice)
                                └─► hook overlay + scene concat → single final MP4
```

**Package**: [`xvideo/prompt_native/`](xvideo/prompt_native/) — public API for prompt-native generation. Module map:

| Module | Role |
|--------|------|
| `schema.py` | `VideoPlan` / `Scene` / `RenderJob` dataclasses |
| `director.py` | `generate_video_plan(prompt, …) -> list[VideoPlan]` (no LLM) |
| `variation_engine.py` | Seed math + `mutate_concept` / `mutate_visual_world` / `mutate_script_angle` |
| `script_engine.py` | Hook / VO / CTA composition |
| `scene_engine.py` | Recommended scene count + duration distribution |
| `visual_prompt_engine.py` | Render-ready SDXL prompt + global negative |
| `motion_engine.py` | camera_motion → parallax profile mapping |
| `caption_style_engine.py` | 6 caption styles (ASS writers) |
| `safety_filters.py` | Prompt sanitisation + plan content audit |
| `scoring.py` | Heuristic plan QA + threshold gate |
| `plan_renderer_bridge.py` | VideoPlan → finished MP4 |

The flat-file modules `xvideo/prompt_video_director.py` and `xvideo/prompt_video_runner.py` are still the underlying implementation; the new package is the canonical public import path going forward.

**Variation**: a *combinatorial concept graph* (archetype × setting × moment × tension × resolution × camera lens × visual style × palette × pacing) seeded by `prompt_hash` + a fresh-per-call OS-entropy seed. Pin `--seed` for full reproducibility.

**CLI**:
```bash
# Generate a video plan + render its scene clips
python scripts/generate_prompt_video.py \
    --prompt "Make a motivational video about discipline" \
    --format shorts_clean

# Same thing but produce the final 9:16 MP4 (TTS, captions, hook, mux)
python scripts/generate_prompt_video.py \
    --prompt "Make a motivational video about discipline" \
    --format shorts_clean --finish

# Five distinct creative directions for the same prompt
python scripts/generate_prompt_video.py \
    --prompt "AI tools are replacing boring work" \
    --format tiktok_fast --variations 5

# Reproducible (pin the seed)
python scripts/generate_prompt_video.py \
    --prompt "Luxury villa open house in Dubai" \
    --format reels_aesthetic --seed 1234 --finish

# Pick a caption style (6 supported; default depends on --format)
python scripts/generate_prompt_video.py --prompt "..." \
    --caption-style karaoke_3word --finish

# Drop a royalty-free loop in assets/music/, then mix it in
python scripts/generate_prompt_video.py --prompt "..." \
    --music-bed auto --finish

# Plan-only (no GPU): inspect title/hook/scenes/voiceover/score
python scripts/generate_prompt_video.py --prompt "..." --dry-run

# List supported caption styles / themes
python scripts/generate_prompt_video.py --list-caption-styles
python scripts/generate_prompt_video.py --list-themes
```

**Variation behavior** (validated with the example prompt "Make a motivational video about discipline" — 5 calls produce 5 different concepts, e.g.):
- Run 1: A boxer training alone before sunrise.
- Run 2: A student deleting distractions at midnight while everyone parties.
- Run 3: A future self watching the current self make excuses.
- Run 4: A warehouse worker stacking small wins while the city sleeps.
- Run 5: A lonely runner pushing through rain in a tiny apartment.

These are not keyword swaps inside a single template — they are different combinations of (archetype, setting, moment, tension, resolution) drawn from the theme's pool by the seeded RNG.

**UI** (Prompt-to-Video Factory page):
- **Generate New Video** — produce one fresh `VideoPlan` from the prompt.
- **Generate 5 Fresh Videos** — fan out five distinct creative directions for the same prompt; preview all before committing GPU time.
- **Render Scenes** — produce the per-scene background clips for one plan (no voice, no captions, no final).
- **Finish Final MP4** — full pipeline: scenes + voice + chosen caption style + hook + optional music bed → single 9:16 MP4.
- Per-plan controls: voice on/off, captions on/off, hook overlay on/off, caption style override, music bed override.
- The page no longer shows a "best matched pack" as the main output. It shows the generated **concept**, **hook**, **scene plan**, **voiceover lines**, **visual prompts per scene**, **score**, and **audit warnings**.
- Legacy pack-routed flow lives under *Advanced: legacy pack-routed prompt → CSV rows*.

**Quality scoring** ([`xvideo/prompt_native/scoring.py`](xvideo/prompt_native/scoring.py)) — every generated plan gets a heuristic score across 10 dimensions (hook strength, visual uniqueness, scene variety, emotional clarity, caption punch, prompt relevance, platform fit, coherence, CTA fit, safety). Default thresholds: `total >= 70`, `hook_strength >= 7`, `scene_variety >= 7`. With `--score-and-filter` (CLI) or the toggle in the UI, the director regenerates plans that fail the gate.

**Caption styles** ([`xvideo/prompt_native/caption_style_engine.py`](xvideo/prompt_native/caption_style_engine.py)):

| Style | Look | Default for |
|-------|------|-------------|
| `bold_word` | One bold word per event, lower-third | shorts_clean |
| `kinetic_word` | Bold word + per-word fade pop | tiktok_fast |
| `clean_subtitle` | Multi-word subtitle, smaller | reels_aesthetic |
| `impact_uppercase` | UPPERCASE punch, larger | tone=intense |
| `minimal_lower_third` | Small thin lower-third | tone=ambient/story |
| `karaoke_3word` | 3-word sliding window, accent-coloured current word | (opt-in) |

All styles render as ASS subtitle files burned in by ffmpeg's `subtitles=` filter. PlayResY=video height so positioning is in real video pixels.

**Music bed** — drop royalty-free instrumental loops in [`assets/music/`](assets/music/) and pass `--music-bed auto` (or a path). Mixed under voice at `-18 dB` (configurable via `--music-bed-db`), faded in/out, looped to fit. Voice and captions are unaffected.

**Sidecar provenance** (`{batch}/video_plan.json` + `{batch}/video_plan_sidecar.json` + per-scene `.meta.json` + per-final `_final_metadata.json`):
- `generation_mode: "prompt_native"`
- `engine_version: "prompt_native/1.0"`
- `video_plan` (the full VideoPlan, including every scene + every voiceover line)
- `concept_seed` (the resolved 32-bit RNG seed)
- `prompt_hash` (sha256 of the user prompt, first 16 hex chars)
- `variation_id` (per-call variation index)
- `caption_style` / `voice` / `music_bed` (post-stage selections)
- `render_jobs` (RenderJob[] — what the renderer actually saw)
- `plan_score` (10-dimension scoring snapshot at generation time)

**Themes available** (`detect_theme` routes by keyword score; fallback is `motivation`):
`motivation`, `mystery`, `ai_tech`, `product`, `ambient`, `story`, `horror`. Each theme owns its own archetype/setting/moment/tension/resolution pools, voice tones, hook templates, narration templates, caption pool, and CTA pool.

**Planner mode** — CLI `--planner prompt_native|legacy_pack|llm`:
- `prompt_native` (default) — combinatorial director, no LLM, deterministic-with-seed.
- `legacy_pack` — routes to the pack-row CSV path; use `scripts/run_shorts_batch.py` directly.
- `llm` — placeholder; the public API is stable and an LLM backend can plug into `script_engine.build_script` and `visual_prompt_engine.compile_visual_prompt` without disturbing the rest.

**Compatibility — what still works**:
- Existing pack workflow (`--pack motivational_quotes` / `ai_facts` / etc.) still ships. Available in the Prompt-to-Video Factory UI under the *Advanced* expander. Used by `e2e_smoke_matrix.py`.
- Existing format presets (`shorts_clean`, `tiktok_fast`, `reels_aesthetic`) work for both prompt-native and pack paths — they share the same duration window + primary-platform mapping.
- Existing 6-pack × 3-format e2e regression matrix is unaffected. Prompt-native is **additive**.
- The flat-file imports `from xvideo.prompt_video_director import ...` keep working unchanged.

**Tests**: `tests/test_prompt_native_*.py` cover schema, variations, director, CLI, caption styles, scoring (54 tests). End-to-end smoke at `scripts/e2e_prompt_native.py` (dry-run by default; `--render` for the full GPU pipeline).

---

## Operator regression (legacy pack matrix)

**Prompt-native smoke** (no GPU; verifies director / runner wiring):
```bash
python scripts/generate_prompt_video.py \
    --prompt "Make a motivational video about discipline" \
    --variations 5 --dry-run
```

**Prompt-native end-to-end** (15 cases, ~3s without --render):
```bash
python scripts/e2e_prompt_native.py            # default: dry-run, ~3s
python scripts/e2e_prompt_native.py --render   # full pipeline (~3 min)
```

**Prompt-native unit tests** (54 tests, ~20s):
```bash
python -m pytest tests/ -q
```

**Pack-matrix regression** (run before any release):
```bash
python scripts/e2e_smoke_matrix.py --dry-run    # ~1 min, CLI + wiring
python scripts/e2e_smoke_matrix.py --render     # ~11 min, full pipeline
```

**Operator UI** (local control panel):
```bash
streamlit run ui/app.py
# Opens http://localhost:8501 with Dashboard / Prompt Generator / New Batch / Batches / Final Exports
```

**Prompt mode** (fastest operator path):
> "Make 10 motivational videos about discipline, pain, comeback, and success. Style should be intense and cinematic."

The **Prompt Generator** page auto-routes to the right pack (`motivational_quotes` in this example), detects the style cue (`fierce`), extracts topics (`discipline, pain, comeback, success`), and drops ready-to-edit pack rows into the batch CSV. Everything downstream (batch → gallery → final exports) is unchanged.

## Product Surface (locked)

**Input**: CSV of prompts with per-row preset, motion profile, seeds.
**Output**: 9:16 vertical MP4 clips + PNG keyframes + JSON sidecars.
**Hardware target**: GTX 1650 Max-Q 4GB laptop (proven).
**Throughput**: 3 clips/min, ~180 clips/hour.

## Ship Presets (4)

| Preset | Aesthetic | Best subjects |
|--------|-----------|---------------|
| crystal | Translucent pastel facets | animals, figures, landscapes |
| papercraft | Folded-paper, earth tones | cottages, villages, cozy scenes |
| neon_arcade | Retrowave neon on dark | cars, runners, cyber subjects |
| monument | Monument Valley pastel geometry | staircases, towers, impossible architecture |

Style guards enforce preset identity at compile time — e.g. `neon_arcade` automatically forces neon palette and dark background. Recorded in every sidecar's `guard_mutations`.

## Motion Profiles (operator knobs, not raw numbers)

| Name | Zoom | Pan | Default duration |
|------|------|-----|------------------|
| calm | 1.00 → 1.15 | 8% | 3.5s |
| medium | 1.00 → 1.25 | 15% | 3.0s |
| energetic | 1.00 → 1.35 | 22% | 2.5s |

## Backlog Presets (not in operator CSV unless `--allow-backlog`)

| Preset | Issue | Fix |
|--------|-------|-----|
| wireframe | Subject good, background drifts soft | Prompt compiler: weight preset extra_tags higher |
| geometric_nature | Overlaps visually with crystal | Differentiate: push toward drama/scale |

## How to Use (daily)

```bash
# 1. Write your prompts in a CSV (see configs/prompts_example.csv).
# 2. Run the batch:
python scripts/run_shorts_batch.py --csv my_prompts.csv --batch-name 2026-04-21

# 3. Review outputs in cache/batches/2026-04-21/clips/
# 4. Sort by column in manifest.csv (preset/motion/time)
# 5. Upload the winners.

# If batch dies mid-run (Ctrl+C, power, crash): just re-run.
# Completed clips are detected and skipped. Only failed/remaining jobs re-render.
python scripts/run_shorts_batch.py --csv my_prompts.csv --batch-name 2026-04-21  # same command
```

## CSV Schema

```
id,subject,action,environment,preset,motion,duration,aspect,seeds
fox_calm,a geometric fox,sitting alert,low poly forest,crystal,calm,,9:16,42
fox_energetic,a geometric fox,running through snow,pine trees,crystal,energetic,,9:16,"42,137,2024"
```

- `id`: unique row key (used for resume)
- `seeds`: comma-separated → each becomes a variant clip
- `duration`: blank = use motion profile default
- `aspect`: 9:16 (Shorts), 16:9, or 1:1

**Variant fanout**: `fox_energetic` row above with 3 seeds → 3 clips. Same idea, different seeds → easy A/B selection.

## Operational Guarantees

| Feature | How |
|---------|-----|
| **Resume** | Each job's output is validated before re-render. Completed = skip. |
| **Retry** | Up to 3 attempts per job with exponential backoff (5s, 15s, 30s). |
| **Validation** | File size >= 20KB + OpenCV can read frames, else treat as failed. |
| **Signal-safe** | Ctrl+C marks running job as failed (not stuck "running"). Next run resumes cleanly. |
| **Per-job logs** | `batches/{name}/logs/{job_id}.log` has full exception traceback on failure. |
| **Error summary** | `batches/{name}/errors.log` aggregates all failure messages. |
| **Atomic writes** | Manifest + stats written via `.tmp → rename` so no half-written files. |

## Output Layout

```
cache/batches/{batch_name}/
  manifest.csv        # one row per job with status, timing, output path, error
  stats.json          # batch-level KPIs (clips/min, per-preset, per-motion)
  errors.log          # all failure messages aggregated
  clips/
    {job_id}.mp4      # the Short
    {job_id}.png      # keyframe for quick visual audit
    {job_id}.meta.json # reproducibility sidecar (seed, prompt hash, guards, timing)
  logs/
    {job_id}.log      # full traceback on failure
```

## KPIs Tracked

Every batch emits `stats.json` with:
- total_jobs, completed, failed, skipped_resumed
- total_wall_sec, avg_total_sec, avg_image_gen_sec
- **clips_per_minute**
- per_preset: count, completed, failed, avg_total_sec
- per_motion: count, completed, failed, avg_total_sec

Operator can answer instantly: *which preset is slowest, which is failing, where is time going*.

## Validated Numbers (3-clip smoke batch)

| Metric | Value |
|--------|-------|
| Pipeline boot | 8.8s (one-time) |
| Per-clip (SDXL + parallax + write) | 19.7s avg |
| Throughput | **3.04 clips/min** |
| Resume (all skipped) | 0.03s total |
| VRAM peak | < 4GB (stays within laptop limit) |
| Per-preset variance | 19.1s (neon_arcade) to 20.8s (crystal) — negligible |

## Content Packs (6 shipped)

Packs are the operator abstraction layer: simple CSV columns map to full prompts via `config.json` lookup tables and templates. Operators never edit prompt internals. Each pack also drives a deterministic publish-metadata generator (title, caption, CTA, hashtags, per-platform variants).

| Pack | Title | Required columns | Default preset | Best for |
|------|-------|------------------|----------------|----------|
| `motivational_quotes` | Motivational Quote Shorts | quote, tone, visual_subject | crystal | Daily motivation, mindset, growth |
| `ai_facts` | AI Facts Shorts | topic, angle, visual_subject | neon_arcade | Tech/AI explainer Shorts |
| `music_visualizer` | Music Visualizer Loops | track_mood, energy, visual_subject | neon_arcade | Audio-visual loops |
| `product_teaser` | Product Teaser Shorts | product, category, vibe, visual_subject | (by category) | Commercial/brand promo |
| `history_mystery` | History & Mystery Shorts | topic, mystery_angle, visual_subject | monument | Unsolved / eerie / historical hooks |
| `abstract_loop` | Abstract Loops | mood, color_theme, visual_subject | crystal | Filler / aesthetic / mood pages |

Each pack ships with `config.json` + `template.csv` (10 starter rows) + `README.md`.

**Usage:**
```bash
# List all packs
python scripts/run_shorts_batch.py --list-packs

# Scaffold a working folder (copies curated template.csv + pack-specific README)
python scripts/run_shorts_batch.py --init-pack motivational_quotes
# → ./runs/motivational_quotes_2026-04-22/{input.csv, README.txt}
#
# Optional:
#   --rows 15          N rows (truncate or cycle template with _v2 IDs)
#   --out-dir /path    override default ./runs/

# Then edit input.csv and run
python scripts/run_shorts_batch.py \
    --pack motivational_quotes \
    --csv runs/motivational_quotes_2026-04-22/input.csv \
    --batch-name quotes-2026-04-22
```

**What packs add automatically:**
- Tone/angle/mood → action + environment phrases (so operator writes `tone=triumphant` not `rising into the light, dramatic sky with rays of sun`)
- Energy → motion profile (so `energy=high` → `motion=energetic`)
- Color bias → preset hint
- Pack-specific negative prompt (e.g. quotes pack auto-suppresses text/typography so your later overlay is clean)

**Template language (tiny, no jinja):**
```
{col}                       — pack row column
{col|default}               — fallback to config.defaults[col]
{col|"literal"}             — fallback to quoted literal
{TABLE[col].prop}           — table lookup
{col|TABLE[col].prop}       — column with lookup fallback (recursive)
```

**Validated:** all 6 packs smoke-tested end-to-end on GTX 1650. Examples of publish output:

| Pack | Title | Hook (TikTok) | CTA |
|------|-------|---------------|-----|
| motivational_quotes (triumphant) | Your moment is now | This one is for the grinders. | Save this for later. |
| ai_facts (future) | Why GPUs changed AI forever | This is closer than you think. | Follow for more AI visuals. |
| music_visualizer (driving+high) | Driving neon energy | Put this one on full screen. | Headphones on. |
| product_teaser (luxury+premium) | Presenting The Arc Watch | Designed without compromise. | Available now. |
| history_mystery (unsolved) | Still unsolved: The Dyatlov Pass incident | No one has ever explained this. | Follow for part 2. |
| abstract_loop (dreamy+pastel) | Drift | (reused) | More loops daily. |

## Social-format presets (3 shipped)

Thin packaging layer on top of any pack. One flag changes pacing + publish metadata across the whole batch without touching pack internals. Format overrides > row values > pack defaults.

| Format | Platform | Duration | Motion bias | Best with |
|--------|----------|----------|-------------|-----------|
| `shorts_clean` | YouTube Shorts | 18-22s | down (cleaner pacing) | motivational_quotes, ai_facts, history_mystery |
| `tiktok_fast` | TikTok | 12-18s | up (punchier) | music_visualizer, ai_facts, abstract_loop |
| `reels_aesthetic` | Instagram Reels | 15-20s | keep | abstract_loop, product_teaser, music_visualizer |

Each format can override: duration window (clamped), motion bias (within pack's `allowed_motion`), CTA pool (replaces), hashtag additions (appended), max_hashtags, primary platform (promotes that platform's title/caption to manifest top-level).

Formats CANNOT override: required columns, subject/action/environment logic, pack negative prompts, row_transformer.

**Usage:**
```bash
python scripts/run_shorts_batch.py --list-formats

python scripts/run_shorts_batch.py --pack history_mystery \
    --csv runs/history_mystery_2026-04-22/input.csv \
    --format shorts_clean --batch-name history-shorts

python scripts/run_shorts_batch.py --pack music_visualizer \
    --csv runs/music_visualizer_2026-04-22/input.csv \
    --format tiktok_fast --batch-name mv-tiktok
```

Format info is recorded in: batch manifest (`format` column), sidecar JSON (`format` block with full provenance), gallery tile badge, clip modal, and `publish_ready` export column.

## Post-production (shipped MVP)

Starred clip -> finished upload: TTS voiceover + burned captions + hook overlay. Uses the same publish metadata already generated at batch time — no regeneration, no LLM.

**Pipeline order** per starred clip:
1. `build_script(publish, primary_platform)` -> hook text + VO lines (+ explicit CTA append so short platform variants still voice the CTA)
2. `synthesize(...)` -> MP3 via edge-tts (pack-specific voice: Jenny, Guy, Aria, Andrew), duration probed via ffmpeg stderr
3. `build_captions(lines, vo_duration, start_offset=hook_end)` -> proportional-by-word-count timing; line 1 is skipped while hook is on-screen so hook+caption don't double up
4. `render_final(...)` -> ffmpeg composite: bg video + voice + `subtitles=...` burn-in (FontSize=22, Bold, black-stroked, bottom-center MarginV=40) + `drawtext` hook overlay (fontsize=52, 0.3-2.5s window)

**Usage:**
```bash
# 1. Export a selection from the gallery (star the winners)
# 2. Run post-production
python scripts/render_final_video.py --batch-dir cache/batches/quotes-2026-04-24

# Turn off pieces if you want a partial export
python scripts/render_final_video.py --batch-dir ... --hook off --captions off

# Override voice
python scripts/render_final_video.py --batch-dir ... --voice-name en-US-ChristopherNeural --voice-rate "+10%"
```

**Output layout:**
```
<batch-dir>/final_exports/
  {job_id}_final.mp4            # H.264/AAC 9:16, burned captions + hook
  {job_id}_final.srt            # standalone captions for external edit
  {job_id}_final_metadata.json  # provenance: script, voice, segments, publish snapshot
  {job_id}_voice.mp3            # TTS output (re-usable)
```

**Validated** end-to-end across motivational_quotes/shorts_clean, product_teaser/reels_aesthetic, history_mystery/shorts_clean, abstract_loop/tiktok_fast. Typical cost: **~3.5s per finished clip** (bottleneck is the 2-pass ffmpeg encode with subtitles + drawtext; TTS is ~1.5s).

### Word-level captions (`--caption-mode word`)

Per-word ASS captions rendered in the bold-single-word, bottom-center lower-third TikTok/Reels style. Font size 72, white primary, 6px black outline, PlayResY=1024 so positioning is in video pixels.

**Timing source:** Microsoft's edge-tts backend stopped emitting `WordBoundary` events (v7+ only emits `SentenceBoundary`). We capture sentence boundaries exactly, then distribute each sentence's duration across its words by syllable count. For our typical 3-6 word sentences the per-word drift is <~100ms. Metadata records `timing_source="syllable_est"` so this is explicit.

If tighter sync is needed later, `estimate_word_events()` in `xvideo/post/word_captions.py` is the single drop-in point for a forced aligner (faster-whisper / aeneas / etc.) — the ASS writer and orchestrator don't change.

```bash
python scripts/render_final_video.py --batch-dir cache/batches/... --caption-mode word
```

## Next (backlog, ranked)

1. **LLM-backed prompt planner** — add `--planner llm` to `prompt_planner.plan_from_prompt()` so it can generate novel quotes / angles / visual subjects beyond the hand-curated topic libraries. Keyword router + style extractor stay as cheap fallback.
2. **Tighter word-caption sync** — if syllable-proportional drift is noticeable, slot in `faster-whisper` (tiny.en model, ~150MB, ~1.5s CPU per clip) as a forced aligner inside `estimate_word_events()`. No other code changes.
3. **Karaoke-highlight word style** — 3-word sliding window with the current word accent-colored. Requires switching ASS event generation to per-window groups with `\c` inline overrides.
4. **Auto-ranking** — wait until ~100+ starred clips accumulated across packs; use real operator selection history to train/tune.
4. **Background music bed** — optional royalty-free loop mixed under voice at -18 dB; select track per-pack or per-format.
5. **E2E harness extension** — add post-production phase to `e2e_smoke_matrix.py --render` so the regression covers final_exports too.
6. **Scorer recalibration** — thresholds tuned for Wan 2.1 video not SDXL stills; fix then wire into batch runner for auto-pass/fail gating.
7. **Pack × format compatibility warnings** — e.g. history_mystery + tiktok_fast allowed but discouraged; print a soft warning so operator can override with --allow-mismatch.
8. **wireframe + geometric_nature** prompt tuning → promote from backlog to ship.
9. **Pack-specific scorers** — e.g. product_teaser should score "commercial cleanliness" differently than abstract_loop scores "loop-ability".
10. **More packs** as content direction demands: `quote_stitching`, `cooking_snippets`, `fitness_mindset`, etc.
11. **`scripts/new_pack.py`** — scaffold a new pack folder with config.json + template.csv + README stubs.

## Files Added This Session

- `xvideo/batch.py` — BatchJob, BatchRunner, resume/retry/validate/KPI engine
- `xvideo/gallery.py` — self-contained HTML review gallery generator
- `xvideo/packs.py` — content pack loader, template resolver, row expander
- `xvideo/pack_init.py` — `--init-pack` scaffolder (dated working folder + curated CSV + pack-specific README)
- `xvideo/formats/` — social format preset layer (shorts_clean, tiktok_fast, reels_aesthetic) + FormatConfig loader + apply helpers
- `xvideo/post/` — post-production pipeline: `script_builder.py` (publish -> VO script + hook), `tts.py` (edge-tts adapter, pack-specific voice map, captures sentence boundaries), `captions.py` (line distribution + SRT writer with hook offset), `word_captions.py` (syllable-proportional per-word timing anchored to sentence boundaries + ASS writer), `ffmpeg_render.py` (bg video + voice + burned captions (SRT or ASS) + hook overlay -> final mp4 via bundled imageio-ffmpeg)
- `scripts/run_shorts_batch.py` — CLI with `--pack`, `--list-packs`, `--init-pack`, `--rows`, `--out-dir`, `--format`, `--list-formats`
- `scripts/render_final_video.py` — starred clips -> finished uploads. Flags: `--voice on/off`, `--captions on/off`, `--hook on/off`, `--caption-mode line|word`, `--voice-name`, `--voice-rate`, `--limit`. Line mode outputs `{clip_id}_final.srt`; word mode outputs `{clip_id}_word.ass`.
- `scripts/e2e_smoke_matrix.py` — regression harness: 6 packs × 3 formats = 18 combinations validated end-to-end (clip/sidecar/manifest/gallery/publish export)
- `xvideo/prompt_planner.py` — natural-language prompt → pack rows. Deterministic, no LLM. Pack routing by keyword score, style detection by pack-specific cue words (e.g. "intense/cinematic" → `fierce` for motivational_quotes, `cautionary` for ai_facts), topic extraction from "about X, Y, Z" phrases, per-pack curated row libraries (~16 topics for motivational, 8-10 for each other pack) with generic fallbacks.
- `ui/` — Streamlit operator dashboard. Thin wrapper over the CLI (CLI remains source of truth). Pages: Dashboard (`app.py` — pack/format/batch summary), Prompt Generator (`0_Prompt_Generator.py` — prompt box → auto-router → editable rows → run, wraps `xvideo.prompt_planner`), New Batch (pack+format picker, init, editable CSV via `st.data_editor`, live-log dry-run/run), Batches (manifest table with in-UI ★/✕ checkboxes, preview grid, gallery launcher, export selection), Final Exports (caption-mode/voice/hook toggles, live-log render, MP4 preview grid). Shared helpers in `ui/_shared.py` handle filesystem reads + subprocess streaming.
- `scripts/build_gallery.py` — standalone gallery regenerator
- `configs/shorts_batch.yaml` — ship presets + motion profiles + validation/retry config
- `configs/prompts_example.csv` — starter CSV showing variant fanout
- `content_packs/motivational_quotes/` — full pack (config + template + README)
- `content_packs/ai_facts/` — full pack
- `content_packs/music_visualizer/` — full pack
- `content_packs/product_teaser/` — full pack (commercial copy + category-driven presets)
- `content_packs/history_mystery/` — full pack (unsolved/forgotten/conspiracy hooks)
- `content_packs/abstract_loop/` — full pack (volume filler, 2.5s loops, 4 seeds/row)
- `xvideo/publish_helper.py` — deterministic title/caption/hashtags/CTA/platform variants
- `scripts/export_selection.py` — gallery selection → publish-ready CSV/JSON
- `worker_runtime/sdxl_parallax/backend.py` — SDXL-Turbo + CPU offload pipeline
- `worker_runtime/sdxl_parallax/parallax.py` — Ken Burns / zoom / pan animators
