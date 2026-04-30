"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { Button } from "@/components/ui/button";
import {
  createExportVariant,
  listRenderArtifacts,
  type ExportAspect,
  type RenderArtifact,
} from "@/lib/api";


export function ExportVariants({ jobId }: { jobId: string }) {
  const { getToken } = useAuth();
  const [artifacts, setArtifacts] = useState<RenderArtifact[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [captions, setCaptions] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = async () => {
    try {
      const token = await getToken();
      if (!token) return;
      setArtifacts(await listRenderArtifacts(jobId, token));
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  useEffect(() => {
    const inFlight = artifacts.some(
      (a) => a.status === "pending" || a.status === "rendering",
    );
    if (!inFlight) return;
    const timer = setInterval(reload, 3000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifacts]);

  const onExport = async (aspect: ExportAspect) => {
    setBusy(aspect);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const created = await createExportVariant(
        jobId, { aspect, captions }, token,
      );
      setArtifacts((rows) => [created, ...rows]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "export failed");
    } finally {
      setBusy(null);
    }
  };

  const labelFor = (aspect: ExportAspect) => {
    if (aspect === "9:16") return "Export 9:16 Original";
    if (aspect === "1:1") return "Export Square";
    return "Export Horizontal";
  };

  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/40 p-3">
      <div className="mb-2 flex items-center justify-between">
        <div className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
          Export variants
        </div>
        <label className="flex items-center gap-1 text-[10px] text-zinc-500">
          <input
            type="checkbox"
            checked={captions}
            onChange={(e) => setCaptions(e.target.checked)}
          />
          captions
        </label>
      </div>

      {!captions ? (
        <div className="mb-2 rounded border border-amber-900 bg-amber-950/30 px-2 py-1 text-[10px] text-amber-200">
          Current renders already have captions burned into pixels. Clean
          no-captions exports need a future clean intermediate.
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {(["9:16", "1:1", "16:9"] as ExportAspect[]).map((aspect) => (
          <Button
            key={aspect}
            size="sm"
            variant="outline"
            onClick={() => onExport(aspect)}
            disabled={busy === aspect}
          >
            {busy === aspect ? "Queuing..." : labelFor(aspect)}
          </Button>
        ))}
      </div>

      {artifacts.length > 0 ? (
        <ul className="mt-3 space-y-1 text-xs">
          {artifacts.map((artifact) => (
            <li
              key={artifact.id}
              className="flex items-center gap-2 rounded border border-zinc-900 bg-zinc-950/60 px-2 py-1"
            >
              <span className="font-mono text-zinc-400">
                {artifact.aspect}
              </span>
              <span className="text-zinc-500">
                {artifact.captions ? "captions" : "no captions requested"}
              </span>
              <span
                className={
                  "ml-auto " +
                  (artifact.status === "complete"
                    ? "text-emerald-300"
                    : artifact.status === "failed"
                      ? "text-red-300"
                      : "text-amber-300")
                }
              >
                {artifact.status}
              </span>
              {artifact.url ? (
                <a
                  href={artifact.url}
                  download
                  className="text-zinc-300 underline-offset-4 hover:underline"
                >
                  Download
                </a>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      {error ? (
        <div className="mt-2 text-[10px] text-red-300">{error}</div>
      ) : null}
    </div>
  );
}
