"use client";

import { useEffect, useMemo, useState } from "react";
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
  listPresenterProviders,
  listPublishingProviders,
  type HealthProbe,
  type ModelProbe,
  type ModelsHealth,
  type PresenterProviderInfo,
  type PublishingProviderInfo,
  type SystemHealth,
} from "@/lib/api";


/**
 * Setup Status page. Replaces the developer-flavored "System health"
 * with a friendlier matrix: each capability is either Ready, Needs
 * setup, or Missing. The setup hint is one click away — copyable
 * code blocks instead of a wall of dev jargon.
 *
 * One screen, four sections: core infra, AI models, talking-head
 * providers, publishing targets. Each one shows what works right now
 * and exactly what to do to unlock the rest.
 */

type StatusKind = "ready" | "setup" | "missing";

interface StatusRow {
  id: string;
  title: string;
  status: StatusKind;
  detail: string;
  hint: string | null;
  cachePath?: string | null;
  category: string;
  badge?: string;
}


export default function SetupStatusPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [system, setSystem] = useState<SystemHealth | null>(null);
  const [models, setModels] = useState<ModelsHealth | null>(null);
  const [presenter, setPresenter] = useState<PresenterProviderInfo[] | null>(null);
  const [publishing, setPublishing] = useState<PublishingProviderInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const [s, m, pr, pub] = await Promise.all([
        getSystemHealth(token),
        getModelsHealth(token),
        listPresenterProviders(token).catch(() => null),
        listPublishingProviders(token).catch(() => null),
      ]);
      setSystem(s);
      setModels(m);
      setPresenter(pr?.providers ?? null);
      setPublishing(pub?.providers ?? null);
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

  const rows: StatusRow[] = useMemo(() => {
    const out: StatusRow[] = [];
    if (system) {
      const required = new Set(["ffmpeg", "redis", "storage"]);
      for (const p of system.probes) {
        out.push({
          id: `infra:${p.name}`,
          title: humanProbeName(p.name),
          status: p.ok
            ? "ready"
            : required.has(p.name)
              ? "missing"
              : "setup",
          detail: p.detail || (p.ok ? "All good." : p.error || "Not detected."),
          hint: p.hint || null,
          category: "core",
        });
      }
    }
    if (models) {
      for (const m of models.models) {
        out.push({
          id: `model:${m.id}`,
          title: m.name,
          status: m.installed ? "ready" : "setup",
          detail: m.status,
          hint: m.hint || null,
          cachePath: m.cache_path,
          category: "models",
          badge: m.required_vram_gb > 0 ? `~${m.required_vram_gb} GB VRAM` : undefined,
        });
      }
    }
    if (presenter) {
      for (const p of presenter) {
        out.push({
          id: `presenter:${p.id}`,
          title: p.name,
          status: p.installed ? "ready" : "setup",
          detail: p.installed
            ? "Lipsync provider ready."
            : p.error || "Not configured.",
          hint: p.install_hint || null,
          cachePath: p.cache_path,
          category: "presenter",
          badge: p.required_vram_gb > 0 ? `~${p.required_vram_gb} GB VRAM` : undefined,
        });
      }
    }
    if (publishing) {
      for (const p of publishing) {
        out.push({
          id: `pub:${p.id}`,
          title: p.name,
          status: p.configured ? "ready" : "setup",
          detail: p.configured
            ? "Connected — uploads will succeed."
            : p.error || "OAuth credentials not set.",
          hint: p.setup_hint || null,
          category: "publishing",
        });
      }
    }
    return out;
  }, [system, models, presenter, publishing]);

  const counts = useMemo(() => {
    const ready = rows.filter((r) => r.status === "ready").length;
    const setup = rows.filter((r) => r.status === "setup").length;
    const missing = rows.filter((r) => r.status === "missing").length;
    return { ready, setup, missing, total: rows.length };
  }, [rows]);

  const sections: Array<{ id: string; title: string; subtitle: string }> = [
    {
      id: "core",
      title: "Core",
      subtitle: "ffmpeg, queue, storage — the platform won't run without these.",
    },
    {
      id: "models",
      title: "AI Models",
      subtitle: "Prompt → video providers. Install at least one to unlock prompt generation.",
    },
    {
      id: "presenter",
      title: "Talking Head",
      subtitle: "Lipsync providers for the AI Presenter. Optional unless you use that mode.",
    },
    {
      id: "publishing",
      title: "Publishing",
      subtitle: "Direct upload to social platforms. Optional.",
    },
  ];

  return (
    <AppShell>
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Setup Status</h1>
          <p className="mt-1 max-w-2xl text-sm text-zinc-400">
            What works right now, what needs setup, and exactly which
            command will fix it. Probes only inspect what&apos;s on disk —
            nothing here triggers a download.
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

      {/* Big at-a-glance summary */}
      <div className="mb-8 grid gap-3 sm:grid-cols-3">
        <SummaryTile
          label="Ready"
          count={counts.ready}
          tone="emerald"
        />
        <SummaryTile
          label="Needs setup"
          count={counts.setup}
          tone="amber"
        />
        <SummaryTile
          label="Missing"
          count={counts.missing}
          tone="red"
        />
      </div>

      {sections.map((sec) => {
        const sectionRows = rows.filter((r) => r.category === sec.id);
        if (sectionRows.length === 0) return null;
        return (
          <Card key={sec.id} className="mb-6">
            <CardHeader>
              <CardTitle className="text-base">{sec.title}</CardTitle>
              <CardDescription>{sec.subtitle}</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-2">
              {sectionRows.map((r) => (
                <StatusRowView key={r.id} row={r} />
              ))}
            </CardContent>
          </Card>
        );
      })}
    </AppShell>
  );
}


function SummaryTile({
  label, count, tone,
}: {
  label: string;
  count: number;
  tone: "emerald" | "amber" | "red";
}) {
  const toneClass =
    tone === "emerald"
      ? "border-emerald-700/40 bg-emerald-950/10 text-emerald-200"
      : tone === "amber"
        ? "border-amber-700/40 bg-amber-950/10 text-amber-200"
        : "border-red-900 bg-red-950/10 text-red-200";
  return (
    <div className={`rounded-lg border p-4 ${toneClass}`}>
      <div className="text-3xl font-semibold">{count}</div>
      <div className="text-xs uppercase tracking-wider opacity-80">{label}</div>
    </div>
  );
}


function StatusRowView({ row }: { row: StatusRow }) {
  return (
    <div className="rounded-md border border-zinc-900 bg-zinc-950/40 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-zinc-100">{row.title}</span>
            {row.badge ? (
              <span className="rounded-full bg-zinc-900 px-2 py-0.5 text-[10px] uppercase tracking-wider text-zinc-400">
                {row.badge}
              </span>
            ) : null}
          </div>
          <p className="mt-1 text-xs text-zinc-400">{row.detail}</p>
        </div>
        <StatusPill kind={row.status} />
      </div>
      {row.status !== "ready" && row.hint ? (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs text-zinc-500 hover:text-zinc-300">
            How to fix
          </summary>
          <pre className="mt-2 overflow-x-auto rounded bg-zinc-900 px-3 py-2 text-[11px] text-zinc-300">
            <code>{row.hint}</code>
          </pre>
          {row.cachePath ? (
            <p className="mt-1 text-[10px] text-zinc-500">
              checked at: <code>{row.cachePath}</code>
            </p>
          ) : null}
        </details>
      ) : null}
    </div>
  );
}


function StatusPill({ kind }: { kind: StatusKind }) {
  const map = {
    ready: {
      cls: "bg-emerald-950/50 text-emerald-300 border-emerald-900",
      label: "✓ Ready",
    },
    setup: {
      cls: "bg-amber-950/50 text-amber-200 border-amber-900",
      label: "⚠ Needs setup",
    },
    missing: {
      cls: "bg-red-950/50 text-red-300 border-red-900",
      label: "✗ Missing",
    },
  } as const;
  const m = map[kind];
  return (
    <span
      className={`whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${m.cls}`}
    >
      {m.label}
    </span>
  );
}


function humanProbeName(name: string): string {
  switch (name) {
    case "ffmpeg":
      return "ffmpeg";
    case "redis":
      return "Redis (job queue)";
    case "storage":
      return "Object storage";
    case "gpu":
      return "GPU";
    case "faster-whisper":
      return "faster-whisper (clipper / captions)";
    default:
      return name;
  }
}
