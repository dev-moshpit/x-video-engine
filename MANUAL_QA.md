# Manual QA flow

End-to-end smoke for a single SaaS user. Runs against the local stack.

## Boot the stack

```bash
pnpm dev:infra            # docker compose: postgres, redis, minio
pnpm dev:db:upgrade       # alembic upgrade head
pnpm dev:api              # fastapi on :8000
pnpm dev:web              # next.js on :3000
py -3.11 apps/worker/main.py            # render worker
py -3.11 apps/worker/exports_main.py    # export-variant worker (Phase 13.5)
```

The web app needs Clerk dev keys (`apps/web/.env.local`) and the api
needs `CLERK_JWT_ISSUER` (`./.env`). Stripe is optional — checkout
returns 503 until `STRIPE_SECRET_KEY` + `STRIPE_PRICE_*` are set.

## Smoke test

1. **Sign in** at `http://localhost:3000/sign-in` (Clerk dev mode).
2. **Create AI Story project** → `/create/ai_story` → fill the prompt
   field → "Save & continue" → lands on `/projects/{id}`.
3. **Generate Video** — primary CTA on the project page. Within ~30s
   the render appears under "Renders" and progresses through
   pending → scripting → rendering → uploading → complete.
4. **Star the result** → preference profile updates; refresh dashboard
   to see "Your top format" populate after a few stars.
5. **Save as preset** — click ★ Save as preset on the project header,
   give it a name. Open `/presets` to verify it shows up; click
   **Create video from preset →** to stamp out a fresh project.
6. **Use preset from dashboard** — saved presets appear inline; clicking
   **Use →** routes to the new project.
7. **Billing 402 modal** — drain the free credit balance (run ~30 renders
   or seed `credits_ledger` with a negative grant) and click Generate
   Video; the upgrade modal appears.
8. **Media library** — `/library` → search "sunset" → save a hit →
   asset appears in the saved list. Use it as a `background_url` in
   voiceover/auto_captions.
9. **Brand kit colors** — `/settings/brand` → set brand color `#1f6feb`
   → render a `top_five` or `would_you_rather`; the palette is applied.
10. **Share preview link** — on a completed render card click
    **↗ Share preview**. Public URL gets copied; open it in an
    incognito window — clean player, no dashboard chrome. Click
    `disable` to return 404 immediately.
11. **Export variants** — under the same render card, click
    **Export 1:1** (or 9:16 / 16:9). Artifact appears with
    `pending` → `rendering` → `complete`; the ↓ link downloads the
    re-framed mp4.
12. **Pricing + portal** — `/pricing` shows the three tiers; current
    tier is badged. With Stripe configured, **Upgrade to Pro** redirects
    to Checkout; `/settings/billing` → **Manage billing** opens the
    customer portal.

## Acceptance bar

- All 12 steps complete without a console / server error.
- Credit balance pill in the app-shell decreases by 1 per render.
- Failed renders mark `stage=failed` and do *not* write a `usage` row.
- Public share page never exposes the user id, template_input, or
  render history.
- xvideo/ remains untouched (no SDXL re-runs for re-exports).
