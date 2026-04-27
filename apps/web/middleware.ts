import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

// Routes that require authentication. Anything not listed here is public.
// NOTE: defense-in-depth — protected pages also do their own server-side
// auth() check (see app/dashboard/page.tsx). The middleware is the fast
// path; the page guard is the always-on path. Clerk's keyless dev mode
// short-circuits this middleware before our callback runs (it surfaces
// a claim-keys banner instead), so the page guard is what makes the
// dashboard route actually require auth before claiming Clerk keys.
const isProtected = createRouteMatcher([
  "/dashboard(.*)",
  "/projects(.*)",
  "/create(.*)",
]);

export default clerkMiddleware(async (auth, req) => {
  if (!isProtected(req)) return;
  const { userId } = await auth();
  if (!userId) {
    const url = new URL("/sign-in", req.url);
    url.searchParams.set("redirect_url", req.nextUrl.pathname + req.nextUrl.search);
    return NextResponse.redirect(url);
  }
});

export const config = {
  matcher: [
    // Skip Next internals and static files
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run on API + tRPC routes
    "/(api|trpc)(.*)",
  ],
};
