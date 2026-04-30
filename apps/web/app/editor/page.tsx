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
import {
  editorProcess,
  getEditorJob,
  uploadFileDirect,
  type EditorAspect,
  type EditorJob,
} from "@/lib/api";


/**
 * Editor page — Platform Phase 1.
 *
 * Upload → preview source → trim → choose aspect + caption settings
 * → submit → poll until output_url arrives → download.
 *
 * The trim handles use the native HTML5 ``<video>`` element to seek
 * — we don't parse frames in the browser. Once the user submits, the
 * api enqueues a job and the worker does a single ffmpeg pass.
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

  // Wire the local file → object URL for preview.
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

      // Upload once per source — cache the public_url so the user can
      // tweak settings and re-submit without re-uploading.
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
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Editor</h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-400">
          Upload a clip, set trim handles, pick the aspect ratio, and
          export. Auto-captions are on by default — they run via
          faster-whisper on the worker.
        </p>
      </div>

      {error ? (
        <div className="mb-4 rounded-md border border-red-900 bg-red-950/30 p-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>1. Upload a clip</CardTitle>
          <CardDescription>
            mp4 / mov / mkv / mp3 — pasted into a presigned PUT URL.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <input
            type="file"
            accept="video/*,audio/*"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-zinc-300 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-800 file:px-3 file:py-1.5 file:text-zinc-100 hover:file:bg-zinc-700"
          />
          {previewUrl ? (
            <video
              ref={videoRef}
              src={previewUrl}
              controls
              onLoadedMetadata={onLoadedMetadata}
              className="max-h-72 w-full rounded-md border border-zinc-900 bg-black"
            />
          ) : null}
        </CardContent>
      </Card>

      {file ? (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>2. Trim + reframe</CardTitle>
            <CardDescription>
              Source duration: {duration.toFixed(1)}s
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="grid gap-1">
                <Label>Trim start ({trimStart.toFixed(1)}s)</Label>
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
                <Label>Trim end ({trimEnd.toFixed(1)}s)</Label>
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

            <div className="grid gap-2 sm:grid-cols-3">
              <div className="grid gap-1">
                <Label>Aspect</Label>
                <select
                  value={aspect}
                  onChange={(e) => setAspect(e.target.value as EditorAspect)}
                  className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-sm"
                >
                  <option value="9:16">9:16 (Reels / Shorts / TikTok)</option>
                  <option value="1:1">1:1 (Instagram feed)</option>
                  <option value="16:9">16:9 (YouTube)</option>
                  <option value="source">keep source</option>
                </select>
              </div>
              <div className="grid gap-1">
                <Label>Captions</Label>
                <label className="flex items-center gap-2 text-sm text-zinc-300">
                  <input
                    type="checkbox"
                    checked={captions}
                    onChange={(e) => setCaptions(e.target.checked)}
                  />
                  burn auto-captions
                </label>
              </div>
              <div className="grid gap-1">
                <Label>Language</Label>
                <Input
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  placeholder="auto / en / es / …"
                  disabled={!captions}
                />
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Button onClick={onSubmit} disabled={submitting}>
                {submitting ? "Submitting…" : "Export clip"}
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
            Export failed: {job.error}
          </CardContent>
        </Card>
      ) : null}
    </AppShell>
  );
}
