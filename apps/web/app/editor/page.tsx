"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
import {
  editorProcess,
  getEditorJob,
  uploadFileDirect,
  type EditorAspect,
  type EditorJob,
} from "@/lib/api";


/**
 * Quick editor: trim, reframe, optionally burn auto-captions, export.
 * Single-pass ffmpeg on the worker. The page hides the technical
 * detail (presigned PUT, ffmpeg filters, faster-whisper language
 * codes) so a non-developer can ship a vertical clip in under a
 * minute.
 */
export default function EditorPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();

  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [duration, setDuration] = useState(0);
  const [trimStart, setTrimStart] = useState(0);
  const [trimEnd, setTrimEnd] = useState(0);
  const [aspect, setAspect] = useState<EditorAspect>("9:16");
  const [captions, setCaptions] = useState(true);
  const [language, setLanguage] = useState("auto");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [uploadedUrl, setUploadedUrl] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [job, setJob] = useState<EditorJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  useEffect(() => () => stopPolling(), []);

  useEffect(() => {
    if (!file) {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
      setUploadedUrl(null);
      setDuration(0);
      setTrimStart(0);
      setTrimEnd(0);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    setUploadedUrl(null);
    return () => {
      URL.revokeObjectURL(url);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file]);

  const onLoadedMetadata = () => {
    if (!videoRef.current) return;
    const d = videoRef.current.duration || 0;
    setDuration(d);
    setTrimStart(0);
    setTrimEnd(d);
  };

  const startPolling = useCallback((jobId: string) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const next = await getEditorJob(jobId, token);
        setJob(next);
        if (next.status === "complete" || next.status === "failed") {
          stopPolling();
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "poll failed");
        stopPolling();
      }
    }, 2000);
  }, [getToken]);

  const onSubmit = async () => {
    if (!file) return;
    setError(null);
    setSubmitting(true);
    setJob(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");

      let url = uploadedUrl;
      if (!url) {
        const isAudio = file.type.startsWith("audio/");
        const kind = isAudio ? "audio" : "video";
        const upload = await uploadFileDirect(file, kind, token);
        url = upload.public_url;
        setUploadedUrl(url);
      }

      const created = await editorProcess(
        {
          source_url: url,
          trim_start: trimStart > 0 ? trimStart : null,
          trim_end:
            trimEnd > 0 && trimEnd < duration ? trimEnd : null,
          aspect,
          captions,
          caption_language: language,
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
        <p className="text-sm text-zinc-400">Sign in to use the Editor.</p>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">
          Quick Editor
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-zinc-400">
          Upload a clip, trim it, choose an aspect, and we&apos;ll export
          a captioned vertical short.
        </p>
      </div>

      {error ? (
        <div className="mb-4 rounded-md border border-red-900 bg-red-950/30 p-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      {!file ? (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <label
              htmlFor="editor-source"
              className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed border-zinc-800 bg-zinc-950/40 px-6 py-12 text-center transition hover:border-zinc-700"
            >
              <span className="text-3xl">🎞</span>
              <span className="text-sm font-medium text-zinc-100">
                Click to choose a video
              </span>
              <span className="text-xs text-zinc-500">
                MP4, MOV, MKV — up to 1 GB
              </span>
              <input
                id="editor-source"
                type="file"
                accept="video/*,audio/*"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
          </CardContent>
        </Card>
      ) : null}

      {file ? (
        <Card className="mb-6">
          <CardContent className="grid gap-4 pt-6">
            {previewUrl ? (
              <video
                ref={videoRef}
                src={previewUrl}
                controls
                onLoadedMetadata={onLoadedMetadata}
                className="max-h-72 w-full rounded-md border border-zinc-900 bg-black"
              />
            ) : null}

            <div className="grid gap-2 sm:grid-cols-2">
              <div className="grid gap-1">
                <Label>
                  Start ({trimStart.toFixed(1)}s)
                </Label>
                <input
                  type="range"
                  min={0}
                  max={Math.max(0, duration - 0.1)}
                  step={0.1}
                  value={trimStart}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    setTrimStart(v);
                    if (v >= trimEnd) setTrimEnd(Math.min(duration, v + 0.5));
                    if (videoRef.current) videoRef.current.currentTime = v;
                  }}
                />
              </div>
              <div className="grid gap-1">
                <Label>End ({trimEnd.toFixed(1)}s)</Label>
                <input
                  type="range"
                  min={0.1}
                  max={duration}
                  step={0.1}
                  value={trimEnd}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    setTrimEnd(v);
                    if (v <= trimStart) setTrimStart(Math.max(0, v - 0.5));
                  }}
                />
              </div>
            </div>

            <div className="grid gap-2 sm:grid-cols-2">
              <div className="grid gap-1">
                <Label>Aspect</Label>
                <select
                  value={aspect}
                  onChange={(e) => setAspect(e.target.value as EditorAspect)}
                  className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-sm"
                >
                  <option value="9:16">9:16 Shorts</option>
                  <option value="1:1">1:1 Square</option>
                  <option value="16:9">16:9 Wide</option>
                  <option value="source">Keep source</option>
                </select>
              </div>
              <div className="grid gap-1">
                <Label>Captions</Label>
                <label className="flex h-9 items-center gap-2 text-sm text-zinc-300">
                  <input
                    type="checkbox"
                    checked={captions}
                    onChange={(e) => setCaptions(e.target.checked)}
                  />
                  Burn auto-captions
                </label>
              </div>
            </div>

            {showAdvanced ? (
              <div className="grid gap-2 sm:grid-cols-2">
                <div className="grid gap-1">
                  <Label>Caption language</Label>
                  <Input
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    placeholder="auto / en / es / …"
                    disabled={!captions}
                  />
                </div>
              </div>
            ) : null}

            <div className="flex items-center justify-between gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowAdvanced((v) => !v)}
                className="text-xs text-zinc-500 underline-offset-4 hover:text-zinc-300 hover:underline"
              >
                {showAdvanced ? "hide advanced" : "advanced"}
              </button>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setFile(null);
                    setJob(null);
                  }}
                  className="text-xs text-zinc-500 underline-offset-4 hover:text-zinc-300 hover:underline"
                >
                  reset
                </button>
                <Button onClick={onSubmit} disabled={submitting} size="lg">
                  {submitting ? "Submitting…" : "Export"}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {job && job.status !== "complete" && job.status !== "failed" ? (
        <Card className="mb-6">
          <CardContent className="py-6">
            <div className="flex items-center gap-3">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
              <span className="text-sm text-zinc-200">
                {job.status === "pending"
                  ? "Queued…"
                  : "Rendering…"}
              </span>
            </div>
            <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-zinc-900">
              <div
                className="h-full bg-emerald-500 transition-all"
                style={{ width: `${Math.round((job.progress ?? 0) * 100)}%` }}
              />
            </div>
          </CardContent>
        </Card>
      ) : null}

      {job?.output_url ? (
        <Card>
          <CardHeader>
            <CardTitle>Done</CardTitle>
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
            Export failed: {job.error}
          </CardContent>
        </Card>
      ) : null}
    </AppShell>
  );
}
