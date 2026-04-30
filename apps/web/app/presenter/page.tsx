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
  getPresenterJob,
  listPresenterProviders,
  renderPresenter,
  uploadFileDirect,
  type PresenterJob,
  type PresenterProviderInfo,
} from "@/lib/api";


/**
 * AI Presenter / Talking-head page — Platform Phase 1.
 *
 * Pick a lipsync provider (Wav2Lip / SadTalker / MuseTalk), upload an
 * avatar image, paste a script, optionally add a news lower-third,
 * submit. The worker synthesizes voice → runs lipsync → overlays the
 * banner → uploads the final mp4.
 *
 * Disabled provider rows surface their install command in a code
 * block — no fake render button when the model isn't ready.
 */
export default function PresenterPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [providers, setProviders] = useState<PresenterProviderInfo[] | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [avatar, setAvatar] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [script, setScript] = useState("");
  const [voice, setVoice] = useState("");
  const [aspect, setAspect] = useState<"9:16" | "1:1" | "16:9">("9:16");
  const [headline, setHeadline] = useState("");
  const [ticker, setTicker] = useState("");
  const [job, setJob] = useState<PresenterJob | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = null;
  };
  useEffect(() => () => stopPolling(), []);

  useEffect(() => {
    if (!avatar) {
      if (avatarPreview) URL.revokeObjectURL(avatarPreview);
      setAvatarPreview(null);
      return;
    }
    const url = URL.createObjectURL(avatar);
    setAvatarPreview(url);
    return () => URL.revokeObjectURL(url);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [avatar]);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    (async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const res = await listPresenterProviders(token);
        setProviders(res.providers);
      } catch (e) {
        setError(e instanceof Error ? e.message : "load failed");
      }
    })();
  }, [isLoaded, isSignedIn, getToken]);

  const startPolling = useCallback((jobId: string) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const next = await getPresenterJob(jobId, token);
        setJob(next);
        if (next.status === "complete" || next.status === "failed") stopPolling();
      } catch (e) {
        setError(e instanceof Error ? e.message : "poll failed");
        stopPolling();
      }
    }, 3000);
  }, [getToken]);

  const onSubmit = async () => {
    if (!picked || !avatar || !script) return;
    setSubmitting(true);
    setError(null);
    setJob(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const upload = await uploadFileDirect(avatar, "image", token);
      const created = await renderPresenter(
        {
          provider_id: picked,
          script,
          avatar_image_url: upload.public_url,
          voice: voice.trim() || null,
          aspect_ratio: aspect,
          headline: headline.trim() || null,
          ticker: ticker.trim() || null,
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
        <p className="text-sm text-zinc-400">Sign in to use the AI Presenter.</p>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">AI Presenter</h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-400">
          Upload an avatar image + paste a script. The worker synthesizes
          a voice, runs lipsync, and (optionally) lays a news-style
          banner over the final clip. Disabled providers show the
          install command — we never run a "fake" presenter.
        </p>
      </div>

      {error ? (
        <div className="mb-4 rounded-md border border-red-900 bg-red-950/30 p-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>1. Pick a lipsync provider</CardTitle>
          <CardDescription>
            {providers
              ? `${providers.filter((p) => p.installed).length} of ${providers.length} installed`
              : "Loading…"}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          {(providers ?? []).map((p) => (
            <button
              key={p.id}
              type="button"
              disabled={!p.installed}
              onClick={() => p.installed && setPicked(p.id)}
              className={`text-left rounded-md border p-3 transition-colors ${
                picked === p.id
                  ? "border-emerald-700 bg-emerald-950/20"
                  : "border-zinc-900 bg-zinc-950/40 hover:border-zinc-700"
              } ${p.installed ? "" : "opacity-60 cursor-not-allowed"}`}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-zinc-100">{p.name}</span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wider ${
                    p.installed
                      ? "bg-emerald-950/50 text-emerald-300 border border-emerald-900"
                      : "bg-zinc-900 text-zinc-400 border border-zinc-800"
                  }`}
                >
                  {p.installed ? "ready" : "setup required"}
                </span>
              </div>
              {p.required_vram_gb > 0 ? (
                <p className="mt-1 text-xs text-zinc-500">
                  ~{p.required_vram_gb} GB VRAM
                </p>
              ) : null}
              {p.description ? (
                <p className="mt-1 text-xs text-zinc-400">{p.description}</p>
              ) : null}
              {!p.installed ? (
                <p className="mt-2 text-[11px] text-zinc-500">
                  install:{" "}
                  <code className="rounded bg-zinc-900 px-1 py-0.5">
                    {p.install_hint}
                  </code>
                </p>
              ) : null}
            </button>
          ))}
        </CardContent>
      </Card>

      {picked ? (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>2. Avatar + script</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="grid gap-1">
                <Label>Avatar image</Label>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => setAvatar(e.target.files?.[0] ?? null)}
                  className="block w-full text-sm text-zinc-300 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-800 file:px-3 file:py-1.5 file:text-zinc-100 hover:file:bg-zinc-700"
                />
                {avatarPreview ? (
                  <img
                    alt="avatar preview"
                    src={avatarPreview}
                    className="mt-2 max-h-48 rounded-md border border-zinc-900"
                  />
                ) : null}
              </div>
              <div className="grid gap-1">
                <Label>Script</Label>
                <Textarea
                  rows={6}
                  value={script}
                  onChange={(e) => setScript(e.target.value)}
                  placeholder="Hi, I'm reporting live from…"
                />
                <Input
                  className="mt-1"
                  placeholder="voice id (optional, edge-tts e.g. en-US-AriaNeural)"
                  value={voice}
                  onChange={(e) => setVoice(e.target.value)}
                />
              </div>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {picked ? (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>3. News template (optional)</CardTitle>
            <CardDescription>
              Leave blank to skip the lower-third banner.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1">
              <Label>Headline</Label>
              <Input
                value={headline}
                onChange={(e) => setHeadline(e.target.value)}
                placeholder="BREAKING: …"
              />
            </div>
            <div className="grid gap-1">
              <Label>Ticker</Label>
              <Input
                value={ticker}
                onChange={(e) => setTicker(e.target.value)}
                placeholder="Markets close lower… Eagles win in OT…"
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
            <div className="flex items-end">
              <Button
                onClick={onSubmit}
                disabled={submitting || !script || !avatar}
              >
                {submitting ? "Submitting…" : "Render presenter"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {job?.output_url ? (
        <Card>
          <CardHeader>
            <CardTitle>4. Output</CardTitle>
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
            Render failed: {job.error}
          </CardContent>
        </Card>
      ) : null}
    </AppShell>
  );
}
