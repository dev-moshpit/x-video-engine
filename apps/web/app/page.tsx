import Link from "next/link";
import { auth } from "@clerk/nextjs/server";


// Five modes the platform exposes — same five tiles the app's
// /create hub shows. Landing-page summary is intentionally short:
// the goal is to get the visitor into the app, not to teach them
// the engine.
const MODES: Array<{
  emoji: string;
  title: string;
  blurb: string;
}> = [
  {
    emoji: "✨",
    title: "Prompt → Video",
    blurb: "One sentence in. A finished short out.",
  },
  {
    emoji: "🎬",
    title: "From a Template",
    blurb: "Ten production-ready faceless formats.",
  },
  {
    emoji: "📝",
    title: "Script → Video",
    blurb: "Paste a script. Voice, captions, b-roll handled.",
  },
  {
    emoji: "✂️",
    title: "Long Video → Clips",
    blurb: "Podcast or stream → top viral 30-60s moments.",
  },
  {
    emoji: "🗣",
    title: "Talking Head",
    blurb: "Avatar image + script → AI presenter with lipsync.",
  },
];


export default async function Home() {
  const { userId } = await auth();
  const ctaHref = userId ? "/create" : "/sign-up";
  const ctaLabel = userId ? "Open Create" : "Start free →";

  return (
    <main className="min-h-dvh">
      {/* Hero */}
      <section className="px-6 pt-24 pb-20 text-center">
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-zinc-500">
          x-video-engine
        </p>
        <h1 className="mx-auto max-w-3xl text-4xl font-semibold tracking-tight sm:text-6xl">
          Create viral videos in seconds.
        </h1>
        <p className="mx-auto mt-6 max-w-xl text-base text-zinc-400 sm:text-lg">
          One platform, five ways in. Prompt, template, script, podcast clip,
          or talking head — the engine picks the voice, captions, and pacing
          for you.
        </p>
        <div className="mt-9 flex items-center justify-center gap-3">
          <Link
            href={ctaHref}
            className="rounded-md bg-emerald-500 px-6 py-3 text-sm font-semibold text-emerald-950 hover:bg-emerald-400"
          >
            {ctaLabel}
          </Link>
          <Link
            href="/pricing"
            className="rounded-md border border-zinc-700 px-6 py-3 text-sm hover:bg-zinc-900"
          >
            See pricing
          </Link>
        </div>
        <p className="mt-5 text-xs text-zinc-500">
          30 free credits to start · no credit card required.
        </p>
      </section>

      {/* Five modes */}
      <section className="border-t border-zinc-900 px-6 py-20">
        <div className="mx-auto max-w-5xl">
          <div className="mb-10 text-center">
            <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">
              Five ways into the same render queue
            </h2>
            <p className="mt-3 text-sm text-zinc-400">
              Pick the one that fits your input. Every mode renders a real MP4
              — captions, voice, and pacing already baked in.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {MODES.map((m) => (
              <div
                key={m.title}
                className="rounded-lg border border-zinc-900 bg-zinc-950/40 p-4 transition hover:border-zinc-700 hover:bg-zinc-900/40"
              >
                <div className="text-2xl">{m.emoji}</div>
                <div className="mt-3 text-sm font-medium text-zinc-100">
                  {m.title}
                </div>
                <div className="mt-1 text-xs text-zinc-500">{m.blurb}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="border-t border-zinc-900 px-6 py-20">
        <div className="mx-auto grid max-w-4xl gap-8 sm:grid-cols-3">
          {[
            {
              n: "01",
              title: "Pick a mode",
              body: "Five entry points cover every common workflow — prompts, scripts, templates, long-form clipping, talking head.",
            },
            {
              n: "02",
              title: "Hit Generate",
              body: "Auto-pick the best voice, caption style, and pacing. The render queue handles the rest while you keep working.",
            },
            {
              n: "03",
              title: "Export & post",
              body: "Download 9:16, 1:1, or 16:9. Connect YouTube once and uploads happen straight from the app.",
            },
          ].map((step) => (
            <div key={step.n}>
              <div className="text-xs font-mono text-zinc-600">{step.n}</div>
              <div className="mt-2 text-base font-medium text-zinc-100">
                {step.title}
              </div>
              <p className="mt-2 text-sm text-zinc-400">{step.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Trust strip */}
      <section className="border-t border-zinc-900 px-6 py-16">
        <div className="mx-auto grid max-w-4xl gap-6 text-center sm:grid-cols-3">
          <div>
            <div className="text-xl font-semibold text-zinc-100">No fakes</div>
            <p className="mt-1 text-xs text-zinc-500">
              When a model isn&apos;t installed the UI says so. We never render
              a placeholder and pretend it worked.
            </p>
          </div>
          <div>
            <div className="text-xl font-semibold text-zinc-100">Real MP4s</div>
            <p className="mt-1 text-xs text-zinc-500">
              Every export is a captioned, retimed MP4 — no watermarked
              previews, no proxy renders.
            </p>
          </div>
          <div>
            <div className="text-xl font-semibold text-zinc-100">Your assets</div>
            <p className="mt-1 text-xs text-zinc-500">
              Your prompts, presets, and exports stay in your library. Cancel
              anytime; downloads stay yours.
            </p>
          </div>
        </div>
      </section>

      {/* CTA strip */}
      <section className="border-t border-zinc-900 px-6 py-20 text-center">
        <h3 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          Ship your first video today.
        </h3>
        <p className="mx-auto mt-3 max-w-md text-sm text-zinc-400">
          Free tier includes 30 renders per month. Upgrade anytime.
        </p>
        <div className="mt-7">
          <Link
            href={ctaHref}
            className="rounded-md bg-emerald-500 px-6 py-3 text-sm font-semibold text-emerald-950 hover:bg-emerald-400"
          >
            {ctaLabel}
          </Link>
        </div>
      </section>

      <footer className="border-t border-zinc-900 px-6 py-8 text-center text-xs text-zinc-600">
        x-video-engine ·{" "}
        <Link href="/pricing" className="hover:text-zinc-300">
          pricing
        </Link>
        {" · "}
        <Link href="/sign-in" className="hover:text-zinc-300">
          sign in
        </Link>
      </footer>
    </main>
  );
}
