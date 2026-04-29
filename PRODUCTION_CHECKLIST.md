# Production checklist — Prompt-to-Video Factory

A pragmatic launch checklist. Each section is a piece of infra that has
to work for the SaaS to ship. Local-dev shortcuts are documented in
`MANUAL_QA.md`; this document is the production-target view.

## Local-dev shortcut

If you want to bring the stack up on a single laptop without Docker
(no admin / no WSL), the portable recipe is:

```bash
# Background services (no admin)
.local/redis/redis-server.exe --port 6379 --bind 127.0.0.1
MINIO_ROOT_USER=minioadmin MINIO_ROOT_PASSWORD=minioadmin \
    .local/minio/minio.exe server .local/minio/data --address ":9000" --console-address ":9001"
.local/minio/mc.exe alias set local http://localhost:9000 minioadmin minioadmin
.local/minio/mc.exe anonymous set download local/renders-dev

# Migrations
DATABASE_URL=sqlite:///./dev.db py -3.11 -m alembic -c apps/api/alembic.ini upgrade head

# App processes
set -a && . ./.env && set +a
pnpm dev:api                                       # uvicorn :8000
pnpm dev:web                                       # next.js :3000
PATH=.local/ffmpeg-8.1-essentials_build/bin:$PATH py -3.11 apps/worker/main.py
PATH=.local/ffmpeg-8.1-essentials_build/bin:$PATH py -3.11 apps/worker/exports_main.py
```

Acceptance: `.local/qa_harness.py --scope fast` prints all eight fast
templates as `complete` and writes contact sheets to
`.local/qa_sheets/`.

## Production targets

### Postgres

- Managed Postgres 15+ (RDS, Neon, Supabase, etc.). The schema is
  agnostic — Alembic migrations under `apps/api/migrations/versions/`
  ship the canonical structure.
- Connection string lives in `DATABASE_URL`. Pool defaults to 5; bump
  via `SQLALCHEMY_POOL_SIZE` only after measuring.
- **Pre-flight:** `py -3.11 -m alembic -c apps/api/alembic.ini upgrade
  head` against the prod DB before the first API boot.

### Redis

- Managed Redis 6+ (Upstash, ElastiCache, fly.io redis, etc.).
- Worker BLPOPs `saas:render:jobs`; exports worker BLPOPs
  `saas:export:jobs`. Both are durable lists — no streams, no
  pub/sub, so any vanilla Redis works.
- Set `REDIS_URL=redis://...` and **`XVE_DEV_FAKEREDIS=0`** on every
  process. The fakeredis path is for unit tests only — leaving it
  enabled in prod silently drops jobs.

### Object storage (R2 / MinIO / S3)

- Cloudflare R2 in prod; MinIO for local dev. Same boto3 client
  works for both via `R2_ENDPOINT`.
- Required env vars: `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`,
  `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PUBLIC_BASE_URL`.
- Prod bucket should be **private** with a custom domain in front;
  the worker will switch to pre-signed URLs when
  `R2_PUBLIC_BASE_URL` is empty. Until then the worker writes
  publicly readable objects.
- For MinIO local: `mc anonymous set download local/renders-dev`
  (downloads return 403 otherwise).

### Clerk

- Two env vars on **web**: `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`,
  `CLERK_SECRET_KEY`.
- One env var on **api**: `CLERK_JWT_ISSUER` (e.g.
  `https://prod-tenant.clerk.accounts.dev`). The api validates JWTs
  via JWKS off this issuer.
- `CLERK_AUDIENCE` is optional; set it if your Clerk template
  populates `aud`.
- **Clock leeway**: `apps/api/app/auth/clerk.py` already passes
  `leeway=60`. Don't drop that — the prod clock can drift a few
  seconds against Clerk and any token with `iat` slightly ahead
  fails verification without leeway.

### Stripe (billing)

- `/api/billing/checkout` returns 503 until **all three** of
  `STRIPE_SECRET_KEY`, `STRIPE_PRICE_PRO`, `STRIPE_PRICE_BUSINESS`
  are set. The 402 modal still works without Stripe (it's driven by
  the in-house credit ledger).
- Webhook URL goes to `/api/billing/webhook`; verify with
  `STRIPE_WEBHOOK_SECRET`.
- Customer portal: set `STRIPE_PORTAL_RETURN_URL` to the prod web
  origin or the link 404s after the user closes the portal.

### ffmpeg / ffprobe

- Required on **every worker host** (render + exports). The
  bundled `imageio-ffmpeg` falls back to a 40 MB binary baked into
  the wheel, but using the system ffmpeg is faster and gets you
  hardware-accelerated codecs.
- Smoke check: `ffmpeg -version` must print on the worker; if not,
  preset Linux paths in the Dockerfile (`apt-get install ffmpeg`).

### HuggingFace cache (SDXL / Whisper)

- AI Story and Reddit Story templates load
  `stabilityai/sdxl-turbo` (~7 GB) on first render. Auto Captions
  loads `faster-whisper` (~150 MB tiny.en).
- Pre-warm with: `HF_HOME=/var/lib/hf python -c "from diffusers
  import AutoPipelineForText2Image; AutoPipelineForText2Image
  .from_pretrained('stabilityai/sdxl-turbo', variant='fp16')"`.
- **Disk requirement**: ≥ 10 GB free on the cache volume. The
  worker fails the first SDXL render with "Not enough free disk
  space" if the safetensors download can't complete (caught in QA
  on the dev box: 3.7 GB free was not enough).
- Set `HF_HOME` and `TRANSFORMERS_CACHE` to the same volume. On
  Linux: `/var/lib/hf` works; on Windows the default
  `C:\Users\<user>\.cache\huggingface\` is fine if C: has space.

### Worker deployment

- One render-worker process per GPU you want to use. The worker
  is a single Python loop — no Celery / RQ — so the supervisor
  story is "run `apps/worker/main.py`, restart on exit".
- Same deal for the exports worker (`apps/worker/exports_main.py`)
  but it's CPU-only and many can run side by side.
- Both processes need `worker_runtime/` on `sys.path` so the
  `xvideo.prompt_video_runner` SDXL imports resolve (already
  handled in `apps/worker/main.py`).

### Web (Next.js)

- Build: `pnpm --filter web build`. Deploy as a static + edge
  bundle (Vercel) or behind any Node 20 host.
- Env vars: `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`,
  `NEXT_PUBLIC_API_BASE_URL` (point at the API origin),
  `CLERK_SECRET_KEY` (server-side). Plus the Clerk middleware
  routes — already wired in `apps/web/middleware.ts`.

## Background services to monitor

| Service | Healthcheck | Alert when |
|---------|-------------|------------|
| API     | `GET /` returns 200 | 5xx > 1% over 1 min |
| Render worker | last `renders.completed_at` < 5 min OR queue length stable | queue length grows unboundedly |
| Exports worker | same as render worker on `saas:export:jobs` | … |
| Redis   | `PING` / `INFO replication` | replication lag > 30 s |
| MinIO/R2 | `HEAD` on a known object | sustained 5xx |

## Smoke harness

`.local/qa_harness.py --scope fast --report QA_REPORT.md` runs every
fast template against the live worker, ffprobes each MP4, builds a 1×3
contact sheet under `.local/qa_sheets/`, and writes a markdown
summary. Run it after any worker change before promoting a build.

For the heavy templates (`ai_story`, `reddit_story`):

```bash
HF_HOME=/var/lib/hf py -3.11 .local/qa_harness.py --scope heavy --report QA_HEAVY.md
```

## Known blockers

- **SDXL warm cache** — see HuggingFace cache section above. Without
  cached weights ai_story / reddit_story fail at first render with
  either a download timeout or "not enough disk space".
- **MinIO `anonymous=download`** — local dev only. In prod, switch
  the worker to pre-signed URLs (the boto3 client already supports
  it; flip `R2_PUBLIC_BASE_URL=""` and re-test).
- **Stripe webhook signing secret** — without it,
  `/api/billing/webhook` rejects every request as 401 (intentional).
  Wire it before launching paid plans.
- **Clerk keyless** — fine for dev. Production must use a real Clerk
  tenant (the keyless tenant rotates issuers).

## CI gate

Before any production deploy:

```bash
py -3.11 -m pytest tests/ -q                 # 218+ tests
pnpm --filter web typecheck                    # tsc --noEmit
py -3.11 -m compileall apps/ tests/            # bytecode sanity
.local/qa_harness.py --scope fast              # render proof
```

All four must succeed. The smoke harness is the only one that
exercises the queue / MinIO / ffmpeg path — pytest alone won't catch
worker regressions.
