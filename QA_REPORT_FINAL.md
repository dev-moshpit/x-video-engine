# QA report — Prompt-to-Video Factory (final, 2026-04-30)

Distinguishes **machine-verified** results from items that need a human
to drive (anything gated on real Clerk sign-up flows, paid-tier billing
webhooks, or per-provider model installation).

---

## 1. Executive summary

- **305 / 305 pytests pass** (`tests/api` + `tests/worker` + prompt-native unit tests).
- **`pnpm --filter @xve/web typecheck`** clean.
- **`python -m compileall apps tests xvideo worker_runtime`** clean.
- **Migrations 0001 → 0012** apply cleanly against a fresh SQLite dev DB. 18 tables present.
- **Full local infra runs**: Redis, MinIO, API, render worker, exports worker, clipper worker, editor worker, generation worker, presenter worker, publishing worker — all 7 worker entrypoints boot without error.
- **8 / 8 fast templates** render end-to-end (auto_captions, fake_text, roblox_rant, split_video, top_five, twitter, voiceover, would_you_rather). `.local/qa_harness.py --scope fast` produced playable MP4s + contact sheets; A/V drift ≤ 40 ms; resolutions 576×1024 (9:16) on every output.
- **Health dashboard reflects real machine state.** ffmpeg / Redis / MinIO / GPU detected; faster-whisper Python package missing; Wan 2.1 weights cached locally; SDXL / SVD / Hunyuan / CogVideoX / Wav2Lip / SadTalker / MuseTalk / YouTube all show as "Setup required" with the exact install command.
- **One real bug found and fixed** during browser sweep — see §3.

## 2. QA harness — fast scope

`py -3.11 .local/qa_harness.py --scope fast --report QA_REPORT_FINAL.md`

| Template | Status | Duration | Resolution | Audio | Δ a-v | Size |
|----------|--------|----------|------------|-------|-------|------|
| auto_captions | OK | 11.4 s | 576×1024 | yes | -0.02s | 190 KB |
| fake_text | OK | 11.1 s | 576×1024 | yes | -0.02s | 229 KB |
| roblox_rant | OK | 8.8 s | 576×1024 | yes | -0.04s | 156 KB |
| split_video | OK | 10.1 s | 576×1024 | yes | -0.03s | 171 KB |
| top_five | OK | 34.0 s | 576×1024 | yes | -0.03s | 696 KB |
| twitter | OK | 8.1 s | 576×1024 | yes | -0.04s | 111 KB |
| voiceover | OK | 12.7 s | 576×1024 | yes | -0.02s | 188 KB |
| would_you_rather | OK | 10.7 s | 576×1024 | yes | -0.01s | 206 KB |

Contact sheets: `.local/qa_sheets/*.png`. Each shows three frames sampled from the rendered MP4.

## 3. Bug fixed in this pass

| # | Surface | Symptom | Fix | Verified |
|---|---------|---------|-----|----------|
| 1 | `/create` hub — Long Video → Clips tile | Stuck on `CHECKING…` badge forever; never resolved to `Setup required` even after `/api/system/health` returned. | Probe key mismatch — frontend searched for `faster-whisper` (hyphen) but the api emits `faster_whisper` (underscore). Updated `apps/web/app/create/page.tsx` and `apps/web/app/settings/system/page.tsx` to match. | Reloaded `/create` — tile now correctly shows `SETUP REQUIRED` with the install hint inline. |

## 4. Heavy-template status

`ai_story` and `reddit_story` not re-run today. Last verified at commit `ba7068d` (production-polish QA pass). Status today:

- **SDXL Base (`stable-diffusion-xl-base-1.0`)** — not installed locally. Probe shows `missing weights`. Install command surfaced in `/settings/system`.
- **Wan 2.1 T2V** — weights cached at `C:\Users\Zohaib ALI\.cache\huggingface\hub\models--Wan-AI--Wan2.1-T2V-1.3B`; provider reports Ready.

## 5. Platform Phase 1 — availability matrix verified

Browser-verified at `/settings/system`:

| Subsystem | Provider | Status | Notes |
|---|---|---|---|
| **Core** | ffmpeg | ✓ Ready | 7.7 essentials build |
| | Redis | ✓ Ready | PONG on :6379 |
| | Object storage | ✓ Ready | bucket `renders-dev` reachable on MinIO :9000 |
| | GPU | ✓ Ready | NVIDIA GeForce GTX 1650 with Max-Q (4 GB) |
| | faster-whisper | ⚠ Needs setup | Python package not importable |
| **AI Models** | Stable Diffusion XL Base | ⚠ Needs setup | weights missing |
| | Stable Video Diffusion | ⚠ Needs setup | weights missing |
| | Wan 2.1 T2V | ✓ Ready | weights cached |
| | HunyuanVideo | ⚠ Needs setup | weights missing |
| | CogVideoX-5b | ⚠ Needs setup | weights missing |
| **Talking Head** | Wav2Lip | ⚠ Needs setup | wav2lip dir not found |
| | SadTalker | ⚠ Needs setup | sadtalker dir not configured |
| | MuseTalk | ⚠ Needs setup | musetalk dir not configured |
| **Publishing** | YouTube (Data API v3) | ⚠ Needs setup | missing env: YOUTUBE_CLIENT_ID, _SECRET, _REFRESH_TOKEN; missing python module: googleapiclient.discovery |

Disabled provider tiles surface the **exact install command** in their setup hint. Click-through on any disabled tile in `/create` routes to `/settings/system` instead of being a dead click.

## 6. Frontend page sweep

| Route | State | Notes |
|---|---|---|
| `/` | OK | Hero + 5-mode tiles + trust strip + CTA |
| `/dashboard` | OK | "+ Create video" CTA, suggestions card, recent projects empty state |
| `/create` | OK | 5 mode tiles, real availability state, YouTube setup prompt |
| `/generate` | OK | Hero textarea + auto-pick (Wan 2.1 T2V) + advanced disclosure |
| `/clips` | OK | Drag-target upload, "Find clips" disabled until file picked |
| `/editor` | OK | Drag-target upload, hero copy, no dev-flavored language |
| `/presenter` | OK | All 3 lipsync providers visible, all disabled with install hints |
| `/settings/system` | OK | Live Setup Status with 5 ready / 14 needs setup / 0 missing |

Nav simplified to: Dashboard / + Create / Library / Pricing / Settings + credit pill (`◆ 30`). Old per-mode links retired.

## 7. Billing

- 3 tiers visible at `/api/billing/tiers`: free (30 credits, watermark on, 1 concurrent), pro (600, no watermark, 3), business (3000, no watermark, 8).
- All 3 tiers report `purchaseable: false` because `STRIPE_PRICE_PRO` and `STRIPE_PRICE_BUSINESS` are blank in `.env`. Setting them turns purchasing on.
- `/api/billing/checkout` and `/api/billing/portal` would 503 with a friendly message if `STRIPE_SECRET_KEY` is missing — confirmed by code path; not exercised live since dev env has no Stripe keys.
- Free-tier watermark verified by prior session artifact `.local/qa_clips/free_watermark.mp4`. Today's QA-harness MP4s used the same seed user — watermark logic unchanged.

## 8. Security

- Owner-scoped routes (`/api/projects/{id}`, `/api/clips/{id}`, etc.) return **401** when no bearer is provided. Will return **404** (not 403) when a token is valid but the resource isn't owned by the user — preventing cross-user existence probing.
- Public share endpoint `/api/public/renders/{token}` returns **404** for non-existent tokens (no info leak).
- No `logger.{info,warn,error,debug}` calls in `apps/api/app` or `apps/worker` reference `token` / `secret` / `key` / `password` / `api_key` substrings.
- `.env.example` contains placeholder strings (`sk_test_...`, blank values) — no real secrets.

## 9. Required setup for full production

| Want | Need |
|---|---|
| Faster Whisper transcription (clipper, captions) | `pip install faster-whisper` + GPU CUDA bindings |
| Prompt → Video with SDXL parallax | download Stable Diffusion XL Base weights into HF cache (~7 GB) |
| Prompt → Video with Wan 2.1 T2V | already cached |
| Image → Video with SVD | download SVD weights (~10 GB) |
| Talking Head | clone Wav2Lip / SadTalker / MuseTalk into `$XVE_MODELS_DIR/...` + download checkpoints |
| YouTube publishing | set YOUTUBE_CLIENT_ID / _SECRET / _REFRESH_TOKEN + `pip install google-api-python-client google-auth-oauthlib` |
| Stripe billing | set STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET / STRIPE_PRICE_PRO / STRIPE_PRICE_BUSINESS |

Every one of these is reflected in `/settings/system` so an operator can see exactly what's missing without reading code.

## 10. Known limitations (non-blocking)

- The `--scope heavy` QA path (ai_story, reddit_story) requires SDXL weights (~7 GB) plus enough disk space; not exercised today.
- Watermark on QA-harness fast outputs not visually re-verified today, but identical render path as `ba7068d`.
- `/share/[token]` page wasn't drive-tested in this session — exists in code (apps/web/app/share/[token]/page.tsx) and unit-tested in `tests/api/test_shares.py`.

## 11. CI gate

```bash
py -3.11 -m pytest tests/ -q                                      # 305 tests
pnpm --filter @xve/web typecheck                                  # tsc --noEmit
py -3.11 -m compileall apps tests xvideo worker_runtime           # bytecode sanity
.local/qa_harness.py --scope fast                                 # render proof
```

All four pass at HEAD.
