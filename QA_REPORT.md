# Local QA Report — x-video-engine SaaS

## TL;DR (2026-04-29 production polish pass)

Full-stack QA across all 10 templates against the locally-running stack
(`web` :3000, `api` :8000, render worker, exports worker, Redis :6379,
MinIO :9000, ffmpeg under `.local/`).

- **8 / 10 templates render real MP4s end-to-end.** All eight upload
  to MinIO, play back over a public URL, and pass the audio/video
  duration sanity check (Δ < 0.05 s).
- **`split_video`** verified in both modes: fallback (no media URL →
  voiceover-style render) and happy-path (vertical split with two
  uploaded clips as `main_url` / `filler_url`).
- **`ai_story` / `reddit_story`** are blocked by an environment issue
  (no SDXL-Turbo weights on disk + only 3.7 GB free on `C:`). The
  *code* path is now correct (the previous run failed before the
  worker even started SDXL — see fix #1 below).

Five render-pipeline / panel-quality bugs surfaced and were fixed in
this pass. Tests: 218 passed (164 worker+api + 54 engine). `pnpm
typecheck:web` clean, `compileall apps/ tests/` clean.

## Templates — final pass

Direct-queue smoke (`.local/smoke_all_templates.py fast` +
`.local/smoke_split_media.py`) against the running worker.

| Template          | Status   | Duration | Bytes  | Notes                                                                     |
|-------------------|----------|----------|--------|---------------------------------------------------------------------------|
| voiceover         | ✅ pass  |  8.4 s   | 125 KB | Solid color bg + edge-tts + bold caption                                  |
| auto_captions     | ✅ pass  |  9.2 s   | 145 KB | Script path (TTS + word captions). Whisper path also wired (untested)     |
| fake_text         | ✅ pass  |  9.1 s   | 170 KB | iOS dark style, 3 messages, narration on. Visual now extends to TTS dur   |
| would_you_rather  | ✅ pass  | 10.7 s   | 254 KB | Captions disabled by default (was overlapping the timer label)            |
| top_five          | ✅ pass  | 22.5 s   | 450 KB | Title now wraps when long; per-item visual paces with TTS                 |
| twitter           | ✅ pass  |  8.1 s   | 122 KB | Verified ✓ now drawn (not glyph), metric labels are text not emoji        |
| roblox_rant       | ✅ pass  |  7.8 s   | 136 KB | Solid color bg + speech-rate +15%                                         |
| split_video       | ✅ pass  | 10.1 s   | 172 KB | Fallback path (no upload). Adapter restores schema fields                 |
| split_video (media) | ✅ pass  |  8.5 s   | 218 KB | Vertical split, twitter clip on top, rant clip on bottom, TTS narration   |
| ai_story          | ⛔ blocked  |   —      |  —     | Needs SDXL-Turbo weights warm. Env-side fix (sys.path + disk space)       |
| reddit_story      | ⛔ blocked  |   —      |  —     | Same SDXL pipeline as `ai_story`                                          |

Audio / video duration parity (post-fix):

```
ok  voiceover           v= 8.42s  a= 8.40s  Δ=-0.02s
ok  auto_captions       v= 9.21s  a= 9.17s  Δ=-0.04s
ok  fake_text           v= 9.12s  a= 9.10s  Δ=-0.03s
ok  would_you_rather    v=10.67s  a=10.66s  Δ=-0.01s
ok  top_five            v=22.46s  a=22.44s  Δ=-0.02s
ok  twitter             v= 8.12s  a= 8.09s  Δ=-0.04s
ok  roblox_rant         v= 7.75s  a= 7.73s  Δ=-0.02s
ok  split_video         v=10.12s  a=10.10s  Δ=-0.03s
```

## Bugs found and fixed in this pass

### 1. Worker can't import the SDXL backend (ai_story / reddit_story)

`xvideo/prompt_video_runner.py` does `from sdxl_parallax.parallax
import …` (top-level package name), but the package lives at
`worker_runtime/sdxl_parallax/`. The CLI scripts under `scripts/` add
`worker_runtime/` to `sys.path`; the SaaS worker did not. So every
`ai_story` / `reddit_story` job failed at the dispatcher with
`ModuleNotFoundError: No module named 'sdxl_parallax'` — before SDXL
was even reached.

Fix: **`apps/worker/main.py`** adds `worker_runtime/` to `sys.path`
during boot. No `xvideo/` change needed.

### 2. Audio outlasts video on the four panel-driven viral templates

ffprobe of the previous QA outputs showed audio outlasting the visual
track by up to **13.4 s** on `top_five` (9 s of frames vs 22.4 s of
narration). Same issue smaller on `would_you_rather`, `twitter`,
`fake_text`. Mid-roll the player would freeze on the last frame for
the rest of the audio.

Root cause: the shared overlay helper encoded frames at their natural
duration without checking how long the TTS would actually run.

Fix:
- **`apps/worker/render_adapters/_image_seq.py`** — new
  `stretch_frames_to_duration(frames, target_sec)` helper.
- **`apps/worker/render_adapters/_overlay.py`** — synthesize the
  TTS *first*, then stretch the timeline to cover `tts.duration_sec
  + 0.4` before encoding the frame mp4. (top_five / twitter /
  would_you_rather / roblox_rant flow through this helper.)
- **`apps/worker/render_adapters/fake_text.py`** — same stretch on
  the chat-frame timeline; deletes the now-dead
  `_organic_duration_sec` helper.

### 3. `top_five` long titles get clipped at the right edge

`render_top_five_panel` drew `list_title.upper()` as a single-line
header at top-left. "TOP 3 PRODUCTIVITY HACKS THAT ACTUALLY WORK"
overflowed the 576 px frame and the right half (`...HACKS THA…`) was
cropped.

Fix: **`apps/worker/render_adapters/_panels.py`** — wrap the header
title against `width - pad * 2` and stack lines with a per-line
height. Single-line titles render unchanged.

### 4. Twitter / X verified-check renders as a `.notdef` box

`render_tweet_card` wrote the `✓` glyph (U+2713) using a system font
loaded by Pillow. On at least one Windows install the bold-Arial
fallback drew a missing-glyph box instead of the check.

Fix: **`apps/worker/render_adapters/_panels.py`** — draw the
checkmark with `ImageDraw.line` (a three-point polyline inside the
verified circle), so the result no longer depends on the system font
having the codepoint. Same logic will work on the Linux production
worker.

### 5. Twitter / X metrics row shows four empty boxes

The metrics row used emoji codepoints (💬 🔁 ❤ 📊) which `arialbd.ttf`
doesn't carry, so each label rendered as `.notdef`. Even on Linux
workers (DejaVu / Liberation Sans) the emoji range is missing.

Fix: replace emoji with text labels (`12 reply`, `89 RT`, `1.2K ♥`,
`45.7K views`) and shrink `meta_font` from 22 px to 18 px so the four
cells fit cleanly within the card. `♥` (U+2665, Arial-supported) keeps
the row visually distinct from a plain number list.

### 6. Would-You-Rather caption overlaps the timer label

The WYR panel renders the question on top, two stacked options, and a
timer label between them at vertical center. The default
`impact_uppercase` caption style sits at MarginV ≈ 30 % of frame
height, which falls right on top of the timer + the bottom panel's
header. QA frames showed "EVERY" stamped over the timer "4".

Fix: change WYR's default `caption_style` to `None` in both
`apps/worker/template_inputs.py` and
`apps/api/app/schemas/templates.py`. Operators can still opt in via
the form / API. Test
`tests/worker/test_template_defaults.py::test_caption_style_defaults_match_product_policy`
updated to match.

## Out of scope — `ai_story` / `reddit_story` setup blocker

After fix #1 the worker successfully reaches SDXL-Turbo, but the
HuggingFace hub download for `stabilityai/sdxl-turbo` (~7 GB total,
UNet alone is 5.1 GB) cannot complete because `C:\Users\Zohaib
ALI\.cache\huggingface\` lives on a drive with only 3.7 GB free.
Partial 5.5 GB cache is on disk; the UNet safetensors download fails
with "Not enough free disk space".

Two ways out — neither requires code changes inside `xvideo/`:

1. Free space on `C:` (preferred — keeps the cache where the SaaS
   worker already looks).
2. Set `HF_HOME=D:\.local\hfcache` before launching the worker; HF
   will write to `D:` (92 GB free) on the next run.

Once the download finishes, both templates will render — the import
path, dispatcher, queue plumbing, watermark step, and upload path are
all the same code path the eight working templates exercise.

## Stack assumed running

| Service       | Binary                                                  | Listening              |
|---------------|---------------------------------------------------------|------------------------|
| Web           | Next.js dev server                                       | `:3000`                |
| API           | `py -3.11 -m uvicorn app.main:app --port 8000`           | `:8000`                |
| Render worker | `apps/worker/main.py`                                    | BLPOPs `saas:render:jobs` |
| Exports worker | `apps/worker/exports_main.py`                           | BLPOPs `saas:export:jobs` |
| Redis 5.0.14  | `.local/redis/redis-server.exe`                          | `127.0.0.1:6379`       |
| MinIO         | `.local/minio/minio.exe server …`                        | `:9000` API, `:9001` UI |
| ffmpeg / ffprobe | `.local/ffmpeg-8.1-essentials_build/bin/`             | on PATH for worker     |

## Test suite (post-fix)

```
tests/worker  — 110 passed
tests/api     —  54 passed
tests/        —  54 passed
total         — 218 passed
pnpm --filter web typecheck — clean
py -3.11 -m compileall apps/ tests/ — clean
```

## What was *not* re-exercised in this pass

The previous `2026-04-28` walk already proved these end-to-end and
their underlying code paths weren't touched in this commit:

- Star / reject flows
- Save preset, dashboard "Use →" preset routing
- Share preview link (`POST /api/renders/{job_id}/share` →
  `GET /api/public/renders/{token}`)
- Export variant 1:1 / 16:9 (exports worker re-frames + uploads)
- Free-tier watermark vs Pro-tier no-watermark
- 402 modal when credits are drained

The worker / api test suite still covers these endpoints and the test
suite passes after the polish pass. No regressions expected.

## Where the smoke harness lives

Reusable for future QA, not committed (under `.local/`):

- `.local/smoke_all_templates.py {fast|heavy|all}` — direct-queue
  push for each template, polls DB for `complete | failed`, dumps
  `.local/smoke_results.json`.
- `.local/smoke_split_media.py` — same flow but uses two prior MinIO
  URLs as `main_url` + `filler_url`.
- `.local/smoke_heavy.py` — ai_story + reddit_story with a 30 min
  deadline (for when SDXL weights are warm).
