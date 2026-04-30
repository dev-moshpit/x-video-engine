"use client";

import { useEffect, useState } from "react";
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
  getModelsHealth,
  getSystemHealth,
  type HealthProbe,
  type ModelProbe,
  type ModelsHealth,
  type SystemHealth,
} from "@/lib/api";


/**
 * System dashboard — Phase 1 of the platform expansion.
 *
 * Surfaces the api's `/api/system/health` and `/api/models/health`
 * snapshots so the operator can see at a glance what is installed,
 * what is missing, and exactly which command will fix it. No fake
 * "coming soon" — every row reflects a real probe.
 */
export default function SystemSettingsPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [system, setSystem] = useState<SystemHealth | null>(null);
  const [models, setModels] = useState<ModelsHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const [s, m] = await Promise.all([
        getSystemHealth(token),
        getModelsHealth(token),
      ]);
      setSystem(s);
      setModels(m);
    } catch (e) {
      setError(e instanceof Error ? e.message : "load failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoaded, isSignedIn]);

  return (
    <AppShell>
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">System</h1>
          <p className="mt-1 max-w-2xl text-sm text-zinc-400">
            Live health of the worker dependencies and AI model caches.
            Probes never download — they only inspect what's already
            present on disk.
          </p>
        </div>
        <Button variant="outline" onClick={refresh} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </Button>
      </div>

      {error ? (
        <div className="mb-6 rounded-md border border-red-900 bg-red-950/30 p-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span>Infrastructure</span>
            {system ? <Pill ok={system.ok} /> : null}
          </CardTitle>
          <CardDescription>
            ffmpeg, Redis broker, object storage, and GPU visibility.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          {system === null ? (
            <p className="text-sm text-zinc-500">Loading…</p>
          ) : (
            system.probes.map((p) => <ProbeRow key={p.name} probe={p} />)
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            AI models
            {models ? (
              <span className="ml-2 text-xs text-zinc-500">
                {models.installed} of {models.total} installed
              </span>
            ) : null}
          </CardTitle>
          <CardDescription>
            Per-model availability. Missing rows are disabled in the UI;
            generators do not silently fall back to a fake.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          {models === null ? (
            <p className="text-sm text-zinc-500">Loading…</p>
          ) : (
            models.models.map((m) => <ModelRow key={m.id} model={m} />)
          )}
        </CardContent>
      </Card>
    </AppShell>
  );
}


function Pill({ ok }: { ok: boolean }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${
        ok
          ? "bg-emerald-950/50 text-emerald-300 border border-emerald-900"
          : "bg-red-950/50 text-red-300 border border-red-900"
      }`}
    >
      {ok ? "ready" : "issues"}
    </span>
  );
}


function ProbeRow({ probe }: { probe: HealthProbe }) {
  return (
    <div className="rounded-md border border-zinc-900 bg-zinc-950/40 p-3">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium text-zinc-100">{probe.name}</div>
        <Pill ok={probe.ok} />
      </div>
      {probe.detail ? (
        <p className="mt-1 text-xs text-zinc-400">{probe.detail}</p>
      ) : null}
      {probe.error ? (
        <p className="mt-1 text-xs text-red-300">{probe.error}</p>
      ) : null}
      {probe.hint ? (
        <p className="mt-1 text-xs text-zinc-500">
          <span className="text-zinc-400">Fix:</span>{" "}
          <code className="rounded bg-zinc-900 px-1.5 py-0.5 text-[11px]">
            {probe.hint}
          </code>
        </p>
      ) : null}
    </div>
  );
}


function ModelRow({ model }: { model: ModelProbe }) {
  return (
    <div className="rounded-md border border-zinc-900 bg-zinc-950/40 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-zinc-100">
              {model.name}
            </span>
            <span className="rounded-full bg-zinc-900 px-2 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400">
              {model.mode}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-zinc-500">
            id: <code className="text-zinc-400">{model.id}</code>
            {model.required_vram_gb > 0
              ? ` · ${model.required_vram_gb} GB VRAM recommended`
              : null}
          </p>
        </div>
        <Pill ok={model.installed} />
      </div>
      <p className="mt-1 text-xs text-zinc-400">{model.status}</p>
      {model.cache_path ? (
        <p className="mt-1 text-[11px] text-zinc-500">
          cache: <code className="text-zinc-400">{model.cache_path}</code>
        </p>
      ) : null}
      {model.error ? (
        <p className="mt-1 text-xs text-red-300">{model.error}</p>
      ) : null}
      {model.hint ? (
        <p className="mt-1 text-xs text-zinc-500">
          <span className="text-zinc-400">Install:</span>{" "}
          <code className="rounded bg-zinc-900 px-1.5 py-0.5 text-[11px]">
            {model.hint}
          </code>
        </p>
      ) : null}
    </div>
  );
}
