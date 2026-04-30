"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  getSystemHealth,
  getVideoModels,
  listPresenterProviders,
  listPublishingProviders,
  listTemplates,
  type PresenterProviders,
  type PublishingProviders,
  type SystemHealth,
  type TemplateMeta,
  type VideoModels,
} from "@/lib/api";


/**
 * Unified create hub. The five entry points the engine exposes
 * (prompt → video, templates, script → video, long-form → clips,
 * talking head) are surfaced as tiles. Each tile reflects real
 * availability — when the underlying provider isn't installed or
 * the host is missing ffmpeg/redis the tile turns into a
 * "Setup required" with a link to the setup page instead of a
 * dead-end click.
 *
 * This is the only entry point the rest of the app should link
 * to from "Create" / "New project" buttons. /generate, /clips,
 * /editor, /presenter, /templates remain reachable as the actual
 * mode pages.
 */

type Availability = "ready" | "setup" | "loading";

interface ModeTile {
  id: string;
  title: string;
  blurb: string;
  href: string;
  helper: string;
  availability: Availability;
  setupHint?: string;
  emoji: string;
  emphasis?: boolean;
}


export default function CreateHubPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [system, setSystem] = useState<SystemHealth | null>(null);
  const [videoModels, setVideoModels] = useState<VideoModels | null>(null);
  const [presenter, setPresenter] = useState<PresenterProviders | null>(null);
  const [publishing, setPublishing] = useState<PublishingProviders | null>(null);
  const [templateCount, setTemplateCount] = useState<number | null>(null);
  const [apiReachable, setApiReachable] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const [sys, vm, pr, pub, tpl] = await Promise.all([
          getSystemHealth(token).catch(() => null),
          getVideoModels(token).catch(() => null),
          listPresenterProviders(token).catch(() => null),
          listPublishingProviders(token).catch(() => null),
          listTemplates().catch(() => [] as TemplateMeta[]),
        ]);
        if (cancelled) return;
        // If every probe failed, the API is down. Show one clear
        // banner instead of leaving every tile stuck on "checking…".
        const anySucceeded =
          sys !== null || vm !== null || pr !== null || pub !== null;
        setApiReachable(anySucceeded);
        setSystem(sys);
        setVideoModels(vm);
        setPresenter(pr);
        setPublishing(pub);
        setTemplateCount(Array.isArray(tpl) ? tpl.length : null);
      } catch (e) {
        if (!cancelled) {
          setApiReachable(false);
          setError(e instanceof Error ? e.message : "load failed");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, getToken]);

  const ffmpegOk = system ? system.probes.find((p) => p.name === "ffmpeg")?.ok ?? null : null;
  const redisOk = system ? system.probes.find((p) => p.name === "redis")?.ok ?? null : null;
  const whisperOk = system
    ? system.probes.find((p) => p.name === "faster-whisper")?.ok ?? null
    : null;

  const baseInfraReady = ffmpegOk === true && redisOk === true;
  const baseInfraLoading = system === null;

  // Once apiReachable===false we don't keep tiles in "loading"; flip
  // them to setup so the user sees actionable state instead of an
  // indefinite spinner.
  const dead = apiReachable === false;

  const promptAvailability = ((): Availability => {
    if (dead) return "setup";
    if (!videoModels || baseInfraLoading) return "loading";
    return baseInfraReady && videoModels.installed > 0 ? "ready" : "setup";
  })();

  const templatesAvailability = ((): Availability => {
    if (dead) return "setup";
    if (baseInfraLoading) return "loading";
    return baseInfraReady ? "ready" : "setup";
  })();

  const scriptAvailability = ((): Availability => {
    if (dead) return "setup";
    if (baseInfraLoading) return "loading";
    return baseInfraReady ? "ready" : "setup";
  })();

  const clipsAvailability = ((): Availability => {
    if (dead) return "setup";
    if (baseInfraLoading || whisperOk === null) return "loading";
    return baseInfraReady && whisperOk ? "ready" : "setup";
  })();

  const presenterAvailability = ((): Availability => {
    if (dead) return "setup";
    if (!presenter || baseInfraLoading) return "loading";
    return baseInfraReady && presenter.installed > 0 ? "ready" : "setup";
  })();

  const tiles: ModeTile[] = [
    {
      id: "prompt",
      emoji: "✨",
      title: "Prompt → Video",
      blurb:
        "One sentence in. A finished short out. Best for ideas you want to test fast.",
      href: "/generate",
      availability: promptAvailability,
      helper: videoModels
        ? `${videoModels.installed}/${videoModels.total} models ready`
        : "checking models…",
      setupHint:
        "Install at least one video model (SDXL parallax, SVD, Wan21, Hunyuan, or CogVideoX).",
      emphasis: true,
    },
    {
      id: "templates",
      emoji: "🎬",
      title: "From a Template",
      blurb:
        "Ten production-ready formats. AI Story, Reddit Story, Top 5, Tweet Video, more.",
      href: "/templates",
      availability: templatesAvailability,
      helper: templateCount ? `${templateCount} templates` : "10 templates",
      setupHint: "Templates need ffmpeg + redis on the host.",
    },
    {
      id: "script",
      emoji: "📝",
      title: "Script → Video",
      blurb:
        "Paste your script. We synthesize voice, burn captions, add b-roll. Faceless.",
      href: "/create/voiceover",
      availability: scriptAvailability,
      helper: "Voiceover + captions",
      setupHint: "ffmpeg + redis must be running.",
    },
    {
      id: "clips",
      emoji: "✂️",
      title: "Long Video → Clips",
      blurb:
        "Upload a podcast or stream. We pull the most viral 30-60s moments and export them.",
      href: "/clips",
      availability: clipsAvailability,
      helper: whisperOk ? "Whisper ready" : "needs faster-whisper",
      setupHint:
        "Install faster-whisper to enable transcript-based clip detection.",
    },
    {
      id: "presenter",
      emoji: "🗣",
      title: "Talking Head",
      blurb:
        "Avatar image + a script → an AI presenter with lipsync. Optional news lower-third.",
      href: "/presenter",
      availability: presenterAvailability,
      helper: presenter
        ? `${presenter.installed}/${presenter.total} lipsync providers ready`
        : "checking presenters…",
      setupHint:
        "Install Wav2Lip, SadTalker, or MuseTalk to enable the talking-head pipeline.",
    },
  ];

  const anyReady = tiles.some((t) => t.availability === "ready");

  return (
    <AppShell>
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">
          What do you want to create?
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-zinc-400">
          Five ways into the same render queue. Pick the one that fits your
          input — we&apos;ll handle voice, captions, and pacing automatically.
        </p>
      </div>

      {apiReachable === false ? (
        <Card className="mb-6 border-red-900 bg-red-950/20">
          <CardHeader>
            <CardTitle className="text-base">Couldn&apos;t reach the API</CardTitle>
            <CardDescription>
              The web app is up but the api server isn&apos;t responding. Start
              it with <code className="rounded bg-zinc-900 px-1 py-0.5 text-xs">pnpm dev:api</code>{" "}
              and a Redis + Postgres instance, then refresh.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link
              href="/settings/system"
              className="text-sm text-red-200 underline-offset-4 hover:underline"
            >
              Open Setup Status →
            </Link>
          </CardContent>
        </Card>
      ) : null}

      {!baseInfraLoading && !baseInfraReady ? (
        <Card className="mb-6 border-amber-700/40 bg-amber-950/20">
          <CardHeader>
            <CardTitle className="text-base">Setup not finished</CardTitle>
            <CardDescription>
              {ffmpegOk === false
                ? "ffmpeg is missing or not on PATH. "
                : null}
              {redisOk === false ? "Redis isn't reachable. " : null}
              The render queue can&apos;t run until both are ready.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link
              href="/settings/system"
              className="text-sm text-amber-200 underline-offset-4 hover:underline"
            >
              Open Setup Status →
            </Link>
          </CardContent>
        </Card>
      ) : null}

      {!baseInfraLoading && baseInfraReady && !anyReady ? (
        <Card className="mb-6 border-zinc-800 bg-zinc-950/40">
          <CardHeader>
            <CardTitle className="text-base">No models installed yet</CardTitle>
            <CardDescription>
              Templates can run on a CPU-only host. To unlock prompt → video,
              long-video → clips, and the talking-head pipeline, install at
              least one model.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link
              href="/settings/system"
              className="text-sm text-zinc-300 underline-offset-4 hover:underline"
            >
              Show me what&apos;s missing →
            </Link>
          </CardContent>
        </Card>
      ) : null}

      {error ? (
        <div className="mb-4 rounded-md border border-red-900 bg-red-950/30 p-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {tiles.map((tile) => (
          <ModeCard key={tile.id} tile={tile} />
        ))}
      </div>

      <div className="mt-12 rounded-lg border border-zinc-900 bg-zinc-950/30 p-5">
        <div className="flex items-start gap-4">
          <span className="text-2xl">📦</span>
          <div className="flex-1">
            <h3 className="text-sm font-medium text-zinc-100">
              Publish to YouTube when you&apos;re done
            </h3>
            <p className="mt-1 text-xs text-zinc-400">
              {publishing
                ? publishing.configured > 0
                  ? "YouTube is connected — finished renders can be uploaded directly."
                  : "Connect a YouTube refresh token in your environment to upload finished renders without leaving the app."
                : "Checking publishing providers…"}
            </p>
            {publishing && publishing.configured === 0 ? (
              <Link
                href="/settings/system"
                className="mt-2 inline-block text-xs text-zinc-400 underline-offset-4 hover:text-zinc-200 hover:underline"
              >
                Setup instructions →
              </Link>
            ) : null}
          </div>
        </div>
      </div>
    </AppShell>
  );
}


function ModeCard({ tile }: { tile: ModeTile }) {
  const isReady = tile.availability === "ready";
  const isLoading = tile.availability === "loading";

  const card = (
    <Card
      className={`group relative h-full overflow-hidden transition-colors ${
        tile.emphasis && isReady
          ? "border-emerald-700/40 hover:border-emerald-600"
          : isReady
            ? "hover:border-zinc-700"
            : "border-zinc-900 opacity-70"
      }`}
    >
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <span className="text-3xl">{tile.emoji}</span>
          {isLoading ? (
            <Badge tone="muted">checking…</Badge>
          ) : isReady ? (
            <Badge tone="ok">Ready</Badge>
          ) : (
            <Badge tone="warn">Setup required</Badge>
          )}
        </div>
        <CardTitle className="mt-3 text-lg">{tile.title}</CardTitle>
        <CardDescription className="text-sm text-zinc-400">
          {tile.blurb}
        </CardDescription>
      </CardHeader>
      <CardContent className="pt-0">
        <p className="text-xs text-zinc-500">{tile.helper}</p>
        {!isReady && !isLoading && tile.setupHint ? (
          <p className="mt-2 text-xs text-zinc-500">
            {tile.setupHint}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );

  if (isReady) {
    return (
      <Link href={tile.href} className="block">
        {card}
      </Link>
    );
  }
  if (isLoading) {
    return <div>{card}</div>;
  }
  return (
    <Link href="/settings/system" className="block">
      {card}
    </Link>
  );
}
