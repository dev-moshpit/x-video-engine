import { defineConfig, devices } from "@playwright/test";

/**
 * E2E smoke for the SaaS web app.
 *
 * Run from the project root:
 *
 *   pnpm dev:infra      # postgres + redis + minio (PR 7)
 *   pnpm dev:db:upgrade # apply alembic migrations (PR 3)
 *   pnpm dev:api        # FastAPI on :8000
 *   pnpm dev:web        # Next.js on :3000
 *   pnpm e2e            # this config — playwright runs against :3000
 *
 * The default test (e2e/smoke.spec.ts) only exercises the public
 * surface (landing + auth redirects); a full sign-up→render→download
 * loop is gated on getting a programmatic Clerk test user, which
 * lands in Phase 1.5 (PR 14+).
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: process.env.WEB_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
