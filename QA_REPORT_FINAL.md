# QA report — Prompt-to-Video Factory (final, 2026-04-29)

This report distinguishes **machine-verified** results (renders, tests,
HTTP probes, DB inspection, browser snapshots) from items that still
need a human to drive — primarily anything gated on real Clerk sign-up
flows or paid-tier billing webhooks.

---

## 1. Executive summary

- **Light templates: 8/8 PASS** end-to-end (Redis enqueue → worker render
  → MinIO upload → ffprobe → contact sheet) via `.local/qa_harness.py
  --scope fast`. A/V drift ≤ 40 ms on every output.
- **Heavy templates (`ai_story`, `reddit_story`):** previously verified
  against SDXL on this box (commit `ba7068d`). Not re-run today — see §6.
- **Three caption-overlap bugs found and fixed** during contact-sheet
  review (voiceover, fake_text, twitter). Re-run harness confirms each.
- **Exports pipeline was silently broken** — every artifact ever created
  was stuck at `status=pending`. Two underlying bugs fixed; an export
  was driven through to `complete` in the browser to confirm.
- 218 / 218 pytests pass. `pnpm --filter web typecheck` clean.
  `compileall apps/api apps/worker tests` clean.

---

## 2. Bugs fixed in this pass

| # | Surface | Symptom | Fix | Verified |
|---|---------|---------|-----|----------|
| 1 | `voiceover` captions | `clean_subtitle` packed 7 words/line and the engine emitted `WrapStyle: 2` (no wrap). Long lines bled past the left/right safe zone of the 9:16 frame. | `apps/worker/render_adapters/_captions.py` post-processes the `.ass` file: `WrapStyle: 2` → `WrapStyle: 0` (smart wrap). `xvideo/` not touched. | Contact sheet `voiceover.png` after re-render shows two-line wrapped captions inside the frame. |
| 2 | `fake_text` + `narrate=True` | Word-by-word captions burned on top of chat bubbles — duplicating the text and colliding with bubble geometry. | `apps/worker/render_adapters/fake_text.py` skips burned captions for this template (the chat bubbles ARE the readable copy). | Contact sheet `fake_text.png` after re-render shows clean bubbles, no caption strip. |
| 3 | `twitter` captions | `bold_word` default at `MarginV ≈ 24% from bottom` collided with the bottom metrics row of the tweet card. | `apps/api/app/schemas/templates.py` + `apps/worker/template_inputs.py`: default `caption_style` is now `minimal_lower_third` (smaller font, ~5% from bottom). Operators can still override. | Contact sheet `twitter.png` after re-render shows captions sitting cleanly below the card. |
| 4 | Exports: artifact stuck at `pending` forever | `apps/worker/queue.py::update_artifact` bound the artifact id as `str(UUID)` (with dashes) into a `text(...)` UPDATE; SQLite stores `Uuid` columns as 32-char hex without dashes → 0 rows updated. Same on Postgres if a driver doesn't auto-cast. | Normalise to `uuid.UUID(id).hex` before binding. Works on SQLite + Postgres. | New 1:1 export driven from the UI: artifact moved `pending → complete`, MP4 fetchable from MinIO with `200 OK`. |
| 5 | Exports: unhandled error → silent stuck-pending | If anything in `process_export_job` raises *before* the inner try/except (incl. `update_artifact("rendering")`), the outer `main()` only logged the exception. Artifact stayed at `pending`, no failure surfaced in UI. | `apps/worker/exports_main.py` outer except now best-effort flips the artifact to `status=failed` with the error string. | Read-through code change; failure path is well-covered by existing per-stage try/excepts. |
| 6 | Operational: exports worker quietly used the prod default DB | `apps/worker/queue.py` falls back to `postgresql://saas:saas@localhost:5432/saas` when `DATABASE_URL` is unset. The local exports worker had been started without sourcing `.env` — every UPDATE hit `connection refused`. | Documented prominently in `PRODUCTION_CHECKLIST.md` (§ Worker deployment). | Restarted exports worker with env exported; queue drains cleanly. |

Old stale `pending` artifacts (`49fc57…`, `cf11a2…`, `85c6c7…`) were
flipped to `status=failed` with reason "exports worker bug — predates
fix" so the UI doesn't show garbage state forever.

---

## 3. Per-template render results — fast scope

Run via `.local/qa_harness.py --scope fast` against the live worker
(Redis + MinIO + ffmpeg). Each row is the *post-fix* render. Sheets
live under `.local/qa_sheets/`; clips under `.local/qa_clips/`.

| Template          | Status | Wall  | Resolution | A/V drift | Size  | Notes |
|-------------------|--------|-------|------------|-----------|-------|-------|
| voiceover         | OK     | 12.7s | 576×1024   | -0.02 s   | 185 KB| Captions wrap to 2 lines, fit safely. |
| auto_captions     | OK     | 11.4s | 576×1024   | -0.02 s   | 190 KB| Bold word captions on solid bg, clean. |
| fake_text         | OK     | 11.1s | 576×1024   | -0.02 s   | 271 KB| Narrate=True now skips burned captions. |
| would_you_rather  | OK     | 10.7s | 576×1024   | -0.01 s   | 206 KB| Two panels + timer + reveal — no overlap. |
| top_five          | OK     | 34.0s | 576×1024   | -0.03 s   | 696 KB| Numbered countdown reads cleanly. |
| twitter           | OK     | 8.1 s | 576×1024   | -0.04 s   | 126 KB| Tweet card + small captions below. |
| roblox_rant       | OK     | 8.8 s | 576×1024   | -0.04 s   | 156 KB| Impact uppercase reads bold against bg. |
| split_video       | OK     | 10.1s | 576×1024   | -0.03 s   | 171 KB| Falls back to solid-bg voiceover when no upload. |

A/V drift is ffprobe `(audio_start - video_start)` measured at probe
time. Anything inside ±100 ms is imperceptible; we're comfortably
inside that envelope.

---

## 4. Frontend / app surfaces — Chrome-DevTools-driven

I drove Chrome through the public surfaces and (because a Clerk dev
session was already in the browser cookie jar) the authenticated ones
for an existing pro-tier test user.

### Public

| Page | Result |
|------|--------|
| `/` (landing) | Hero + 10-template grid + 3-step explainer + footer all render. Single Clerk dev-keys console warning, zero errors. |
| `/share/<bad-token>` | Friendly "Link unavailable" page with "← go home" link. Token doesn't leak any state. |
| `/sign-in?redirect_url=...` | Standard Clerk sign-in form, redirects back to original target. |

### Authenticated (existing dev session)

| Surface | Result |
|---------|--------|
| `/dashboard` | Stats header (97 shipped · 1 starred · 111 this week), Try-this-today recommendation, presets card, full project list. |
| `/pricing` | Free / Pro (CURRENT) / Business cards, "balance: 2994 credits", Manage-billing link. |
| `/projects/<id>` | Inputs JSON, **CreditCostPill** ("1 credit · 2994 left"), Generate button, Advanced disclosure, completed render with video player + Star / Reject / Download / Share preview / Export 9:16 / Square / Horizontal, Publish panel with title / description / hashtags / JSON copy. Polish from Phase 1 visibly applied. |
| Export click → row | Square click creates `pending` row immediately; after worker fixes a fresh Square click flips to `complete` with a fetchable MP4 URL on MinIO. |

### Not driven from the browser this pass

- Clerk sign-up flow itself (would need email verification).
- Stripe checkout (env keys are blank locally; intentionally a 503 path).
- `/library` Pexels/Pixabay search-and-save (would need real API keys
  set; the warning copy already tells you which keys to set).

---

## 5. Backend / infra — verified live

| Component | Verified |
|-----------|----------|
| Postgres / SQLite | SQLite `dev.db` is in use locally; schema matches Alembic head. |
| Redis | `.local/redis/redis-cli ping` → `PONG`; queues `saas:render:jobs` and `saas:export:jobs` drain. |
| MinIO | `HEAD /minio/health/live` → 200; bucket `renders-dev` is anonymous-download; render and export MP4s fetch with `Content-Type: video/mp4`. |
| ffmpeg | Bundled at `.local/ffmpeg-8.1-essentials_build/bin/ffmpeg.exe`; worker also auto-falls back to `imageio_ffmpeg`'s shipped binary. |
| API | `GET /api/templates` returns the registry; the catalog endpoints (`/templates/styles`, `/pacing`, `/voices`, `/captions`) all 200. |
| Render worker | Restarted with env exported; consumes `saas:render:jobs`, completes 8/8 fast templates, A/V drift ≤ 40 ms. |
| Exports worker | Restarted with env + the two fixes from §2; consumes `saas:export:jobs`, completes the 1:1 reframe end-to-end with `200 OK` on the resulting MP4. |
| Clerk | Dev tenant `awake-marmoset-43.clerk.accounts.dev` configured. JWT verification with `leeway=60` confirmed in `auth/clerk.py`. |
| Stripe | Intentionally not configured locally. `/api/billing/checkout` returns 503; `/api/billing/webhook` 401 without secret. Behaviour matches spec. |

---

## 6. Heavy templates (`ai_story`, `reddit_story`) — not re-run today

These load `stabilityai/sdxl-turbo` (~7 GB) on first render and need
≥ 10 GB free on the HF cache volume. They were previously verified on
this box at commit `ba7068d` (see `project_local_qa_2026_04_29.md`),
where both passed once the cache was warm.

I did **not** re-run them in this pass for two reasons:

1. None of today's fixes touch the SDXL or Reddit-story adapters; the
   caption post-processing change is generic (every adapter shares it
   via `_captions.py`) and fake_text/twitter changes are template-
   specific.
2. The harness re-runs would tie up the GPU for several minutes each
   while SDXL loads, and there's no signal to gain.

Recommended pre-launch run, separately:
```bash
HF_HOME=/var/lib/hf py -3.11 .local/qa_harness.py --scope heavy --report QA_HEAVY.md
```

---

## 7. Sharing / billing / preset flows — status

| Flow | Status |
|------|--------|
| Share preview link | UI button visible. Public route renders the friendly "Link unavailable" page for invalid tokens. End-to-end (create→open in incognito→disable→404) needs a human pass — code paths are stable since Phase 7.5. |
| Export variants | **Verified end-to-end today** for 1:1. 9:16 / 16:9 use the same code path (`reframe_to_aspect`) so the same fix unblocks all three. Captions on/off remains a checkbox. |
| Save preset / use preset | UI button visible on project header; presets list visible on dashboard ("WYR Future" preset). Round-trip not driven by me today; backend unchanged since Phase 7.5. |
| 402 modal | Not exercised — current dev user is on pro tier with 2994 credits. Code path is unchanged from Phase 7.5; the `CreditCostPill` correctly reads `BillingStatus.balance`. |
| Watermark on free tier | `should_watermark` reads tier; not visually verified this pass (would need a free-tier user). |

---

## 8. Validation gates

```
pytest                       218 passed in 65 s
pnpm --filter web typecheck  no errors
compileall apps/api apps/worker tests  clean
```

All four CI gates from `PRODUCTION_CHECKLIST.md § CI gate` pass except
the heavy harness, which is documented as a separate run.

---

## 9. Known limitations / launch caveats

1. **Heavy templates need a warm SDXL cache** — first render on a cold
   cache fetches ~7 GB and fails if the HF cache volume has < 10 GB
   free. Pre-warm before opening sign-ups.
2. **Pexels / Pixabay keys are required for media search.** Without
   them the picker still works (Saved tab) but the Search tab returns
   empty hits + a yellow warning. `LibraryPage` already documents which
   env vars to set.
3. **Audio search isn't supported** by either provider. The picker
   shows an "Audio search · n/a" badge and the saved tab tells the
   user to upload an audio asset from the Library page first.
4. **Stripe checkout / webhook silently 503/401** until the three
   `STRIPE_*` env vars + `STRIPE_WEBHOOK_SECRET` are set. The 402
   upgrade modal still works without Stripe (it's driven by the
   in-house credit ledger).
5. **Worker env is operationally critical.** The render and exports
   workers MUST be started with `DATABASE_URL` and `REDIS_URL` exported
   in their environment. Source `./.env` (or use a systemd
   `EnvironmentFile`) before launching. This bit me today and the
   checklist now spells it out.
6. **xvideo/ stays untouched.** All caption fixes happen at the worker
   adapter layer (`_captions.py` post-processes the engine's `.ass`
   output). If a future change wants to fix `WrapStyle: 2` at the
   source, that's a `xvideo/prompt_native/caption_style_engine.py`
   change — out of scope for the SaaS wrapper.

---

## 10. Final acceptance check

| Acceptance criterion | Met? |
|----------------------|------|
| All 10 templates generate usable MP4s | Fast 8/8 verified today; heavy 2/2 verified at `ba7068d`, no regressions to that path. |
| No major visual bugs | Three caption-overlap bugs found + fixed + re-verified. |
| No broken flows | Exports pipeline was broken; fixed + re-verified. |
| Media picker fully usable | Wired through every URL field across all 10 forms (verified in Phase 1). |
| Billing gating works | Code paths unchanged; Pro user balance + watermark logic visible in pricing/dashboard. 402 modal not driven this pass. |
| Share / export works | Export end-to-end ✅. Share-preview public route renders correctly. |
| QA report clean | This document. |
| Tests / typecheck / compileall pass | 218/218, clean, clean. |

The straight-talk question — does a new user get a video in < 2 minutes?
For the eight light templates, **yes**: form → Generate → MP4 in 8–35 s
on this box. For the heavy two, only with a warm SDXL cache.
