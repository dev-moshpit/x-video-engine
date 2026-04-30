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
 * AI Clipper page — Platform Phase 1.
 *
 * Drag a long video / audio file in → upload via presigned PUT →
 * POST /api/clips/analyze → poll /api/clips/{id} until status=complete →
 * surface the scored moments → user picks one and an aspect →
 * POST /api/clips/{id}/export → poll the artifact until url is ready →
 * link to the finished MP4.
 *
 * Every action backed by a real worker step. No fake "preview".
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
        // ignore — keep last known list
      }
    };
    void tick();
    const id = setInterval(tick, 3000);
    return () => clearInterval(id);
  }, [getToken]);

  // Whenever a job becomes complete, start polling its artifacts list.
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
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">AI Clipper</h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-400">
          Upload a long video or audio file. The clipper transcribes,
          finds the strongest moments, scores them across seven
          dimensions, and exports captioned shorts in your chosen
          aspect ratio.
        </p>
      </div>

      {error ? (
        <div className="mb-4 rounded-md border border-red-900 bg-red-950/30 p-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>1. Upload source media</CardTitle>
          <CardDescription>
            mp4 / mov / mp3 / wav up to 1 GB. We send it directly to
            object storage with a presigned PUT — the browser is the
            uploader.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <input
            type="file"
            accept="video/*,audio/*"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-sm text-zinc-300 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-800 file:px-3 file:py-1.5 file:text-zinc-100 hover:file:bg-zinc-700"
          />
          {file ? (
            <p className="text-xs text-zinc-500">
              {file.name} · {(file.size / (1024 * 1024)).toFixed(1)} MB ·
              {" "}{file.type || "unknown type"}
            </p>
          ) : null}
          <div className="flex items-center gap-3">
            <Button
              onClick={onAnalyze}
              disabled={!file || uploading || analyzing}
            >
              {uploading
                ? "Uploading…"
                : analyzing
                  ? "Starting analysis…"
                  : "Analyze for viral moments"}
            </Button>
            {job ? (
              <span className="text-xs text-zinc-500">
                job {job.job_id.slice(0, 12)}… · {job.status} ·{" "}
                {Math.round((job.progress ?? 0) * 100)}%
              </span>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {job?.status === "running" || job?.status === "pending" ? (
        <Card className="mb-6">
          <CardContent className="py-6 text-sm text-zinc-300">
            <p>
              {job.status === "pending" ? "Queued…" : "Transcribing + scoring."}
            </p>
            <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-zinc-900">
              <div
                className="h-full bg-emerald-500 transition-all"
                style={{ width: `${Math.round(job.progress * 100)}%` }}
              />
            </div>
          </CardContent>
        </Card>
      ) : null}

      {job?.status === "failed" ? (
        <Card className="mb-6 border-red-900">
          <CardContent className="py-4 text-sm text-red-200">
            <p className="font-medium">Analysis failed.</p>
            <p className="mt-1 text-xs">{job.error}</p>
          </CardContent>
        </Card>
      ) : null}

      {job?.status === "complete" ? (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>
              2. {job.moments.length} viral moments detected
            </CardTitle>
            <CardDescription>
              Sorted by score. Pick aspect + captions toggle to export.
              {job.duration_sec
                ? ` (source: ${Math.round(job.duration_sec)}s)`
                : null}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            {job.moments.length === 0 ? (
              <p className="text-sm text-zinc-400">
                No moments long enough were found in this source.
              </p>
            ) : (
              job.moments.map((m) => (
                <MomentRow key={m.moment_id} moment={m} onExport={onExport} />
              ))
            )}
          </CardContent>
        </Card>
      ) : null}

      {artifacts.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>3. Exports</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            {artifacts.map((a) => (
              <ArtifactRow key={a.id} artifact={a} />
            ))}
          </CardContent>
        </Card>
      ) : null}
    </AppShell>
  );
}


function MomentRow({
  moment, onExport,
}: {
  moment: ClipMoment;
  onExport: (m: ClipMoment, a: ExportAspect, c: boolean) => void;
}) {
  const [aspect, setAspect] = useState<ExportAspect>("9:16");
  const [captions, setCaptions] = useState(true);
  const dims = moment.score_breakdown;
  const dur = Math.round(moment.duration);
  return (
    <div className="rounded-md border border-zinc-900 bg-zinc-950/40 p-3">
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <span>
              {fmt(moment.start)}–{fmt(moment.end)} · {dur}s
            </span>
            <span className="rounded-full bg-zinc-900 px-2 py-0.5 text-[10px]">
              score {(moment.score * 100).toFixed(0)}
            </span>
          </div>
          <p className="mt-1 line-clamp-3 text-sm text-zinc-200">
            {moment.text}
          </p>
        </div>
      </div>
      <div className="mt-2 grid grid-cols-7 gap-1 text-[10px]">
        <Bar label="hook" v={dims.hook_strength} />
        <Bar label="emo" v={dims.emotional_spike} />
        <Bar label="ctrv" v={dims.controversy} />
        <Bar label="clr" v={dims.clarity} />
        <Bar label="len" v={dims.length_fit} />
        <Bar label="erg" v={dims.speaker_energy} />
        <Bar label="cap" v={dims.caption_potential} />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select
          value={aspect}
          onChange={(e) => setAspect(e.target.value as ExportAspect)}
          className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 text-xs"
        >
          <option value="9:16">9:16</option>
          <option value="1:1">1:1</option>
          <option value="16:9">16:9</option>
        </select>
        <label className="flex items-center gap-1 text-xs text-zinc-400">
          <input
            type="checkbox"
            checked={captions}
            onChange={(e) => setCaptions(e.target.checked)}
          />
          captions
        </label>
        <Button
          size="sm"
          onClick={() => onExport(moment, aspect, captions)}
        >
          Export clip
        </Button>
      </div>
    </div>
  );
}


function Bar({ label, v }: { label: string; v: number }) {
  const pct = Math.max(0, Math.min(1, v));
  return (
    <div>
      <div className="flex items-center justify-between text-[9px] text-zinc-500">
        <span>{label}</span>
        <span>{Math.round(pct * 100)}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-900">
        <div
          className="h-full bg-emerald-500"
          style={{ width: `${pct * 100}%` }}
        />
      </div>
    </div>
  );
}


function ArtifactRow({ artifact }: { artifact: ClipArtifact }) {
  return (
    <div className="rounded-md border border-zinc-900 bg-zinc-950/40 p-3">
      <div className="flex items-center justify-between">
        <div className="text-sm">
          <span className="text-zinc-200">{artifact.aspect}</span>
          <span className="ml-2 text-xs text-zinc-500">
            {fmt(artifact.start_sec)}–{fmt(artifact.end_sec)}
          </span>
        </div>
        <span className="rounded-full bg-zinc-900 px-2 py-0.5 text-[10px] uppercase tracking-wider text-zinc-400">
          {artifact.status}
        </span>
      </div>
      {artifact.url ? (
        <a
          href={artifact.url}
          className="mt-2 inline-block text-xs text-emerald-400 underline"
          target="_blank"
          rel="noreferrer"
        >
          Download MP4 →
        </a>
      ) : null}
      {artifact.error ? (
        <p className="mt-1 text-xs text-red-300">{artifact.error}</p>
      ) : null}
    </div>
  );
}


function fmt(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds - m * 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}
