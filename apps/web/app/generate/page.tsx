"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  generateVideo,
  getVideoGeneration,
  getVideoModels,
  uploadFileDirect,
  type VideoGeneration,
  type VideoModelInfo,
} from "@/lib/api";


/**
 * Prompt → video. Hero-first layout: prompt textarea + Generate is
 * the only thing visible by default. The chosen model is auto-picked
 * (highest-quality installed provider). Provider override + duration
 * + fps + seed + aspect + image upload all sit behind an "Advanced"
 * disclosure so a first-time user can ship a video without reading
 * any technical labels.
 *
 * Disabled state: when no provider is installed, the hero refuses to
 * render the form and points the user at /settings/system instead.
 */

// Quality preference order — first installed model wins as the
// auto-pick. Wan 2.1 / Hunyuan are top-tier, then CogVideoX, then
// SVD (img2vid → needs image), then SDXL parallax (CPU fallback).
const QUALITY_ORDER: readonly string[] = [
  "wan21",
  "hunyuan",
  "cogvideox",
  "svd",
  "sdxl_parallax",
] as const;


export default function GeneratePage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();

  const [models, setModels] = useState<VideoModelInfo[] | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [prompt, setPrompt] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [duration, setDuration] = useState(4);
  const [fps, setFps] = useState(24);
  const [aspect, setAspect] = useState<"9:16" | "1:1" | "16:9">("9:16");
  const [seed, setSeed] = useState<string>("");

  const [job, setJob] = useState<VideoGeneration | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stopPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = null;
  };
  useEffect(() => () => stopPolling(), []);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    (async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const res = await getVideoModels(token);
        setModels(res.providers);
        if (!picked) setPicked(autoPickProvider(res.providers));
      } catch (e) {
        setLoadErr(e instanceof Error ? e.message : "load failed");
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoaded, isSignedIn, getToken]);

  const startPolling = useCallback((jobId: string) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const next = await getVideoGeneration(jobId, token);
        setJob(next);
        if (next.status === "complete" || next.status === "failed") stopPolling();
      } catch (e) {
        setError(e instanceof Error ? e.message : "poll failed");
        stopPolling();
      }
    }, 2500);
  }, [getToken]);

  const installed = useMemo(
    () => (models ?? []).filter((m) => m.installed),
    [models],
  );
  const pickedProvider = models?.find((m) => m.id === picked) ?? null;
  const requiresImage = pickedProvider?.mode === "image-to-video";

  const onSubmit = async () => {
    if (!picked || !pickedProvider) return;
    if (!prompt.trim()) {
      setError("write a prompt first");
      return;
    }
    if (requiresImage && !image) {
      setError("this model needs a starter image — open Advanced to upload one");
      setShowAdvanced(true);
      return;
    }
    setSubmitting(true);
    setError(null);
    setJob(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");

      let imageUrl: string | undefined;
      if (requiresImage && image) {
        const upload = await uploadFileDirect(image, "image", token);
        imageUrl = upload.public_url;
      }

      const created = await generateVideo(
        {
          provider_id: picked,
          prompt,
          image_url: imageUrl,
          duration_seconds: duration,
          fps,
          aspect_ratio: aspect,
          seed: seed.trim() ? Number(seed) : null,
        },
        token,
      );
      setJob(created);
      startPolling(created.job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "submit failed");
    } finally {
      setSubmitting(false);
    }
  };

  if (isLoaded && !isSignedIn) {
    return (
      <AppShell>
        <p className="text-sm text-zinc-400">Sign in to generate videos.</p>
      </AppShell>
    );
  }

  // No installed providers → don't pretend the form works.
  if (models !== null && installed.length === 0) {
    return (
      <AppShell>
        <h1 className="text-2xl font-semibold tracking-tight">Prompt → Video</h1>
        <Card className="mt-4 border-amber-700/40 bg-amber-950/20">
          <CardHeader>
            <CardTitle className="text-base">No video models installed</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-amber-100/80">
            <p>
              Install at least one of: SDXL parallax, SVD, Wan 2.1, HunyuanVideo,
              or CogVideoX. The /settings/system page lists each model&apos;s
              install hint.
            </p>
            <a
              href="/settings/system"
              className="inline-block text-amber-200 underline-offset-4 hover:underline"
            >
              Open Setup Status →
            </a>
          </CardContent>
        </Card>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">
          Prompt → Video
        </h1>
        <p className="mt-2 text-sm text-zinc-400">
          Describe what you want to see. Hit Generate.
        </p>
      </div>

      {loadErr ? (
        <div className="mb-4 rounded-md border border-red-900 bg-red-950/30 p-3 text-sm text-red-200">
          {loadErr}
        </div>
      ) : null}
      {error ? (
        <div className="mb-4 rounded-md border border-red-900 bg-red-950/30 p-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      <Card className="mb-4">
        <CardContent className="grid gap-4 pt-6">
          <Textarea
            placeholder="A neon-lit alley at night. Slow zoom in. Rain on the asphalt."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={4}
            className="text-base"
          />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-xs text-zinc-500">
              Using:{" "}
              <span className="text-zinc-200">
                {pickedProvider?.name ?? "auto"}
              </span>
              {pickedProvider?.required_vram_gb
                ? ` · ${pickedProvider.required_vram_gb} GB VRAM`
                : null}
              {" · "}
              <button
                type="button"
                onClick={() => setShowAdvanced((v) => !v)}
                className="text-zinc-400 underline-offset-4 hover:text-zinc-200 hover:underline"
              >
                {showAdvanced ? "hide advanced" : "advanced"}
              </button>
            </div>
            <Button
              onClick={onSubmit}
              disabled={submitting || !prompt.trim() || !picked}
              size="lg"
            >
              {submitting ? "Submitting…" : "Generate"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {showAdvanced ? (
        <Card className="mb-6 border-zinc-900">
          <CardHeader>
            <CardTitle className="text-sm font-medium text-zinc-300">
              Advanced
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="grid gap-2">
              <Label>Model</Label>
              <div className="grid gap-2 sm:grid-cols-2">
                {(models ?? []).map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => m.installed && setPicked(m.id)}
                    disabled={!m.installed}
                    className={`text-left rounded-md border p-2 text-sm transition-colors ${
                      picked === m.id
                        ? "border-emerald-700 bg-emerald-950/20"
                        : "border-zinc-900 bg-zinc-950/40 hover:border-zinc-700"
                    } ${m.installed ? "" : "opacity-60 cursor-not-allowed"}`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-zinc-100">{m.name}</span>
                      {m.installed ? (
                        <span className="text-[10px] uppercase text-emerald-300">
                          ready
                        </span>
                      ) : (
                        <span className="text-[10px] uppercase text-zinc-500">
                          not installed
                        </span>
                      )}
                    </div>
                    <div className="mt-1 text-xs text-zinc-500">
                      {m.mode}
                      {m.required_vram_gb > 0
                        ? ` · ${m.required_vram_gb} GB`
                        : null}
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {requiresImage ? (
              <div className="grid gap-1">
                <Label>Starter image (required for this model)</Label>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => setImage(e.target.files?.[0] ?? null)}
                  className="block w-full text-sm text-zinc-300 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-800 file:px-3 file:py-1.5 file:text-zinc-100 hover:file:bg-zinc-700"
                />
              </div>
            ) : null}

            <div className="grid gap-2 sm:grid-cols-4">
              <div className="grid gap-1">
                <Label>Duration (s)</Label>
                <Input
                  type="number"
                  min={1}
                  max={30}
                  value={duration}
                  onChange={(e) => setDuration(Number(e.target.value))}
                />
              </div>
              <div className="grid gap-1">
                <Label>FPS</Label>
                <Input
                  type="number"
                  min={8}
                  max={60}
                  value={fps}
                  onChange={(e) => setFps(Number(e.target.value))}
                />
              </div>
              <div className="grid gap-1">
                <Label>Aspect</Label>
                <select
                  value={aspect}
                  onChange={(e) => setAspect(e.target.value as "9:16" | "1:1" | "16:9")}
                  className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm"
                >
                  <option value="9:16">9:16 (Shorts)</option>
                  <option value="1:1">1:1 (Square)</option>
                  <option value="16:9">16:9 (Landscape)</option>
                </select>
              </div>
              <div className="grid gap-1">
                <Label>Seed</Label>
                <Input
                  placeholder="random"
                  value={seed}
                  onChange={(e) => setSeed(e.target.value)}
                />
              </div>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {job ? (
        <Card className="mb-4">
          <CardContent className="pt-6">
            {!job.output_url && job.status !== "failed" ? (
              <div className="flex items-center gap-3">
                <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
                <span className="text-sm text-zinc-300">
                  {job.status === "pending"
                    ? "Queued…"
                    : `Rendering · ${Math.round(job.progress * 100)}%`}
                </span>
              </div>
            ) : job.output_url ? (
              <div className="grid gap-3">
                <video
                  src={job.output_url}
                  controls
                  className="max-h-96 w-full rounded-md border border-zinc-900 bg-black"
                />
                <div className="flex items-center gap-3">
                  <a
                    href={job.output_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm text-emerald-400 underline"
                  >
                    Download MP4 →
                  </a>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setJob(null);
                      setPrompt("");
                    }}
                  >
                    Generate another
                  </Button>
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {job?.status === "failed" ? (
        <Card className="border-red-900">
          <CardContent className="py-3 text-sm text-red-200">
            Generation failed: {job.error}
          </CardContent>
        </Card>
      ) : null}
    </AppShell>
  );
}


function autoPickProvider(providers: readonly VideoModelInfo[]): string | null {
  // Prefer the highest-quality installed model so first-time users
  // get the best result with no clicks. Falls back to any installed.
  for (const id of QUALITY_ORDER) {
    const found = providers.find((p) => p.id === id && p.installed);
    if (found) return found.id;
  }
  const first = providers.find((p) => p.installed);
  return first?.id ?? null;
}
