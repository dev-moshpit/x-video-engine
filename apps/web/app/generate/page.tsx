"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
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
 * Direct video-model generation page — Platform Phase 1.
 *
 * Lists every registered provider with its installed/missing state.
 * Disabled cards show the install command instead of a fake render
 * button. Selecting an installed provider unlocks the prompt form;
 * submitting enqueues a real worker job.
 */
export default function GeneratePage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();

  const [models, setModels] = useState<VideoModelInfo[] | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);

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
      } catch (e) {
        setLoadErr(e instanceof Error ? e.message : "load failed");
      }
    })();
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

  const pickedProvider = models?.find((m) => m.id === picked) ?? null;

  const onSubmit = async () => {
    if (!picked || !pickedProvider) return;
    setSubmitting(true);
    setError(null);
    setJob(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");

      let imageUrl: string | undefined;
      if (pickedProvider.mode === "image-to-video") {
        if (!image) throw new Error("this model requires an input image");
        const upload = await uploadFileDirect(image, "image", token);
        imageUrl = upload.public_url;
      }

      const created = await generateVideo(
        {
          provider_id: picked,
          prompt: prompt || pickedProvider.name,
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

  return (
    <AppShell>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">
          Direct generation
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-400">
          Pick a video model, write a prompt, generate. Models that
          aren't installed on this worker show their install command —
          we never silently fall back to a different model.
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

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>1. Pick a model</CardTitle>
          <CardDescription>
            {models
              ? `${models.filter((m) => m.installed).length} of ${models.length} installed`
              : "Loading registry…"}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          {(models ?? []).map((m) => (
            <button
              key={m.id}
              type="button"
              onClick={() => m.installed && setPicked(m.id)}
              disabled={!m.installed}
              className={`text-left rounded-md border p-3 transition-colors ${
                picked === m.id
                  ? "border-emerald-700 bg-emerald-950/20"
                  : "border-zinc-900 bg-zinc-950/40 hover:border-zinc-700"
              } ${m.installed ? "" : "opacity-60 cursor-not-allowed"}`}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-zinc-100">
                  {m.name}
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wider ${
                    m.installed
                      ? "bg-emerald-950/50 text-emerald-300 border border-emerald-900"
                      : "bg-zinc-900 text-zinc-400 border border-zinc-800"
                  }`}
                >
                  {m.installed ? "ready" : "not installed"}
                </span>
              </div>
              <p className="mt-1 text-xs text-zinc-500">
                {m.mode}
                {m.required_vram_gb > 0
                  ? ` · ${m.required_vram_gb} GB VRAM`
                  : null}
              </p>
              {m.description ? (
                <p className="mt-1 text-xs text-zinc-400">{m.description}</p>
              ) : null}
              {!m.installed ? (
                <p className="mt-2 text-[11px] text-zinc-500">
                  install:{" "}
                  <code className="rounded bg-zinc-900 px-1 py-0.5">
                    {m.install_hint}
                  </code>
                </p>
              ) : null}
            </button>
          ))}
        </CardContent>
      </Card>

      {pickedProvider ? (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>2. Configure</CardTitle>
            <CardDescription>
              {pickedProvider.name} · {pickedProvider.mode}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            <div className="grid gap-1">
              <Label>Prompt</Label>
              <Textarea
                placeholder="A neon-lit alley at night, slow zoom, cinematic"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={3}
              />
            </div>
            {pickedProvider.mode === "image-to-video" ? (
              <div className="grid gap-1">
                <Label>Input image (required)</Label>
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
                  <option value="9:16">9:16</option>
                  <option value="1:1">1:1</option>
                  <option value="16:9">16:9</option>
                </select>
              </div>
              <div className="grid gap-1">
                <Label>Seed</Label>
                <Input
                  placeholder="optional"
                  value={seed}
                  onChange={(e) => setSeed(e.target.value)}
                />
              </div>
            </div>
            <div className="flex items-center gap-3 pt-1">
              <Button onClick={onSubmit} disabled={submitting || !prompt}>
                {submitting ? "Submitting…" : "Generate"}
              </Button>
              {job ? (
                <span className="text-xs text-zinc-500">
                  {job.status} · {Math.round(job.progress * 100)}%
                </span>
              ) : null}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {job?.output_url ? (
        <Card>
          <CardHeader>
            <CardTitle>3. Output</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <video
              src={job.output_url}
              controls
              className="max-h-96 w-full rounded-md border border-zinc-900 bg-black"
            />
            <a
              href={job.output_url}
              target="_blank"
              rel="noreferrer"
              className="text-sm text-emerald-400 underline"
            >
              Download MP4 →
            </a>
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
