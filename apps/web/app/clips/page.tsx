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
import {
  analyzeClip,
  exportClip,
  getClipJob,
  listClipArtifacts,
  uploadFileDirect,
  type ClipArtifact,
  type ClipJob,
  type ClipMoment,
  type ExportAspect,
} from "@/lib/api";


/**
 * Long video → clips. Three-step UX: upload, the worker auto-detects
 * the strongest moments, click one to export. Internal scoring
 * dimensions are hidden — we surface a single quality indicator
 * (Strong / Solid / Worth a look) so the page reads like a product
 * tool, not a dashboard.
 */
export default function ClipsPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();

  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [job, setJob] = useState<ClipJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<ClipArtifact[]>([]);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  useEffect(() => () => stopPolling(), []);

  const startPollingJob = useCallback((jobId: string) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const next = await getClipJob(jobId, token);
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

  const startPollingArtifacts = useCallback((jobId: string) => {
    const tick = async () => {
      try {
        const token = await getToken();
        if (!token) return;
        setArtifacts(await listClipArtifacts(jobId, token));
      } catch {
        /* keep last known */
      }
    };
    void tick();
    const id = setInterval(tick, 3000);
    return () => clearInterval(id);
  }, [getToken]);

  useEffect(() => {
    if (job?.status !== "complete") return;
    return startPollingArtifacts(job.job_id);
  }, [job?.status, job?.job_id, startPollingArtifacts]);

  const onAnalyze = async () => {
    if (!file || !isSignedIn) return;
    setError(null);
    setUploading(true);
    setJob(null);
    setArtifacts([]);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const isAudio = file.type.startsWith("audio/");
      const kind = isAudio ? "audio" : "video";
      const { public_url } = await uploadFileDirect(file, kind, token);
      setUploading(false);
      setAnalyzing(true);
      const created = await analyzeClip(
        { source_url: public_url, source_kind: kind },
        token,
      );
      setJob(created);
      startPollingJob(created.job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "analyze failed");
    } finally {
      setUploading(false);
      setAnalyzing(false);
    }
  };

  const onExport = async (
    moment: ClipMoment, aspect: ExportAspect, captions: boolean,
  ) => {
    if (!job) return;
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const a = await exportClip(
        job.job_id,
        { moment_id: moment.moment_id, aspect, captions },
        token,
      );
      setArtifacts((prev) => [a, ...prev]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "export failed");
    }
  };

  if (isLoaded && !isSignedIn) {
    return (
      <AppShell>
        <p className="text-sm text-zinc-400">Sign in to use the AI Clipper.</p>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">
          Long video → Clips
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-zinc-400">
          Drop in a podcast, stream, or any long video. We&apos;ll find the
          strongest 30-60 second moments and export them as captioned shorts.
        </p>
      </div>

      {error ? (
        <div className="mb-4 rounded-md border border-red-900 bg-red-950/30 p-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      {/* Upload step. Hidden once an analysis is in progress or done. */}
      {!job ? (
        <Card className="mb-6">
          <CardContent className="grid gap-4 pt-6">
            <label
              htmlFor="clip-source"
              className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed border-zinc-800 bg-zinc-950/40 px-6 py-12 text-center transition hover:border-zinc-700"
            >
              <span className="text-3xl">📥</span>
              <span className="text-sm font-medium text-zinc-100">
                {file ? file.name : "Click to choose a video or audio file"}
              </span>
              <span className="text-xs text-zinc-500">
                {file
                  ? `${(file.size / (1024 * 1024)).toFixed(1)} MB`
                  : "MP4, MOV, MP3, WAV — up to 1 GB"}
              </span>
              <input
                id="clip-source"
                type="file"
                accept="video/*,audio/*"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
            <div className="flex justify-end">
              <Button
                onClick={onAnalyze}
                disabled={!file || uploading || analyzing}
                size="lg"
              >
                {uploading
                  ? "Uploading…"
                  : analyzing
                    ? "Starting analysis…"
                    : "Find clips"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {/* Progress / failed states. */}
      {job?.status === "running" || job?.status === "pending" ? (
        <Card className="mb-6">
          <CardContent className="py-8">
            <div className="flex items-center gap-3">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
              <span className="text-sm text-zinc-200">
                {job.status === "pending"
                  ? "Queued…"
                  : "Transcribing and finding moments…"}
              </span>
            </div>
            <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-zinc-900">
              <div
                className="h-full bg-emerald-500 transition-all"
                style={{ width: `${Math.round((job.progress ?? 0) * 100)}%` }}
              />
            </div>
          </CardContent>
        </Card>
      ) : null}

      {job?.status === "failed" ? (
        <Card className="mb-6 border-red-900">
          <CardContent className="py-4 text-sm text-red-200">
            <p className="font-medium">Couldn&apos;t analyze this file.</p>
            <p className="mt-1 text-xs">{job.error}</p>
            <button
              type="button"
              onClick={() => {
                setJob(null);
                setFile(null);
              }}
              className="mt-3 text-xs text-red-300 underline-offset-4 hover:underline"
            >
              Try another file →
            </button>
          </CardContent>
        </Card>
      ) : null}

      {/* Moment list */}
      {job?.status === "complete" ? (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>
              {job.moments.length === 0
                ? "No moments long enough were found"
                : `${job.moments.length} clips ready`}
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            {job.moments.map((m) => (
              <MomentRow key={m.moment_id} moment={m} onExport={onExport} />
            ))}
            {job.moments.length === 0 ? (
              <button
                type="button"
                onClick={() => {
                  setJob(null);
                  setFile(null);
                }}
                className="text-sm text-zinc-300 underline-offset-4 hover:underline"
              >
                Try another file →
              </button>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {/* Exports */}
      {artifacts.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Exports</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-2">
            {artifacts.map((a) => (
              <ArtifactRow key={a.id} artifact={a} />
            ))}
          </CardContent>
        </Card>
      ) : null}
    </AppShell>
  );
}


function qualityLabel(score: number): { label: string; tone: string } {
  // Convert raw 0..1 score → human band. Hides the dimension breakdown.
  if (score >= 0.78) return { label: "🔥 Strong", tone: "text-emerald-300" };
  if (score >= 0.6) return { label: "✓ Solid", tone: "text-emerald-300/80" };
  return { label: "Worth a look", tone: "text-zinc-400" };
}


function MomentRow({
  moment, onExport,
}: {
  moment: ClipMoment;
  onExport: (m: ClipMoment, a: ExportAspect, c: boolean) => void;
}) {
  const [aspect, setAspect] = useState<ExportAspect>("9:16");
  const [captions, setCaptions] = useState(true);
  const [submitted, setSubmitted] = useState(false);
  const dur = Math.round(moment.duration);
  const q = qualityLabel(moment.score);

  const handleExport = () => {
    setSubmitted(true);
    onExport(moment, aspect, captions);
  };

  return (
    <div className="rounded-md border border-zinc-900 bg-zinc-950/40 p-4 transition-colors hover:border-zinc-800">
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3 text-xs text-zinc-500">
            <span>
              {fmt(moment.start)}–{fmt(moment.end)} · {dur}s
            </span>
            <span className={q.tone}>{q.label}</span>
          </div>
          <p className="mt-2 line-clamp-3 text-sm text-zinc-200">
            {moment.text}
          </p>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select
          value={aspect}
          onChange={(e) => setAspect(e.target.value as ExportAspect)}
          className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 text-xs"
        >
          <option value="9:16">9:16 Shorts</option>
          <option value="1:1">1:1 Square</option>
          <option value="16:9">16:9 Wide</option>
        </select>
        <label className="flex items-center gap-1.5 text-xs text-zinc-400">
          <input
            type="checkbox"
            checked={captions}
            onChange={(e) => setCaptions(e.target.checked)}
          />
          Burn captions
        </label>
        <Button
          size="sm"
          onClick={handleExport}
          disabled={submitted}
        >
          {submitted ? "Exporting…" : "Export"}
        </Button>
      </div>
    </div>
  );
}


function ArtifactRow({ artifact }: { artifact: ClipArtifact }) {
  return (
    <div className="flex items-center justify-between rounded-md border border-zinc-900 bg-zinc-950/40 p-3">
      <div className="text-sm">
        <span className="text-zinc-200">{artifact.aspect}</span>
        <span className="ml-2 text-xs text-zinc-500">
          {fmt(artifact.start_sec)}–{fmt(artifact.end_sec)}
        </span>
      </div>
      {artifact.url ? (
        <a
          href={artifact.url}
          className="text-xs text-emerald-400 underline"
          target="_blank"
          rel="noreferrer"
        >
          Download →
        </a>
      ) : artifact.error ? (
        <span className="text-xs text-red-300">{artifact.error}</span>
      ) : (
        <span className="text-xs text-zinc-500">{artifact.status}…</span>
      )}
    </div>
  );
}


function fmt(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds - m * 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}
