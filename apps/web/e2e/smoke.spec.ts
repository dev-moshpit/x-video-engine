import { expect, test } from "@playwright/test";

/**
 * PR 10 smoke. Verifies the app's public surface comes up, navigation
 * is intact, and protected routes correctly redirect to /sign-in.
 *
 * What's NOT in this file (yet):
 * - Actually signing up + rendering a video. Programmatic Clerk auth
 *   for tests needs either a saved storageState or Clerk's testing
 *   tokens — both belong in a Phase 1.5 PR.
 *
 * Run: pnpm e2e   (from project root, with the api+web running)
 */

test.describe("public surface", () => {
  test("landing page renders with sign-in / sign-up CTAs", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/x-video-engine/);
    // Signed-out state shows both CTAs.
    await expect(page.getByRole("link", { name: /sign in/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /sign up/i })).toBeVisible();
  });

  test("sign-in page mounts the Clerk widget", async ({ page }) => {
    await page.goto("/sign-in");
    // Clerk renders a heading + form. Don't assert exact copy in case
    // Clerk tweaks it; just check we're still on /sign-in and not 404.
    await expect(page).toHaveURL(/\/sign-in/);
    await expect(page.locator("body")).toContainText(/sign[\s-]?in/i);
  });

  test("/dashboard redirects to /sign-in when unauthenticated", async ({ page }) => {
    const res = await page.goto("/dashboard");
    expect(res?.status()).toBeLessThan(500);
    // Either we got a 307 → /sign-in, or the page rendered the sign-in
    // form via Clerk's keyless redirect. Either way the URL ends up
    // pointing at /sign-in.
    await page.waitForURL(/\/sign-in/);
  });

  test("/templates redirects to /sign-in when unauthenticated", async ({ page }) => {
    await page.goto("/templates");
    await page.waitForURL(/\/sign-in/);
  });
});
