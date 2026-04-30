"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  deleteSavedPrompt,
  getInsights,
  listProjects,
  listSavedPrompts,
  useSavedPrompt,
  type InsightsResponse,
  type Project,
  type SavedPrompt,
} from "@/lib/api";
import { useRouter } from "next/navigation";


export default function DashboardPage() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const router = useRouter();

  const [projects, setProjects] = useState<Project[]>([]);
  const [insights, setInsights] = useState<InsightsResponse | null>(null);
  const [presets, setPresets] = useState<SavedPrompt[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!isLoaded) return;
    if (!isSignedIn) {
      router.push("/sign-in?redirect_url=/dashboard");
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const token = await getToken();
        if (!token) throw new Error("not signed in");
        const [p, i, s] = await Promise.all([
          listProjects(token),
          getInsights(token),
          listSavedPrompts(token),
        ]);
        if (cancelled) return;
        setProjects(p);
        setInsights(i);
        setPresets(s);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "load failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, getToken, router]);

  const onUsePreset = async (id: string) => {
    try {
      const token = await getToken();
      if (!token) return;
      const project = await useSavedPrompt(id, {}, token);
      router.push(`/projects/${project.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "could not use preset");
    }
  };

  const onDeletePreset = async (id: string) => {
    try {
      const token = await getToken();
      if (!token) return;
      await deleteSavedPrompt(id, token);
      setPresets((p) => p.filter((x) => x.id !== id));
    } catch {
      /* swallow */
    }
  };

  return (
    <AppShell>
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          {insights && !insights.is_new_user ? (
            <p className="mt-1 text-sm text-zinc-400">
              {insights.completed_renders} videos shipped ·{" "}
              {insights.starred_renders} starred ·{" "}
              {insights.renders_last_7_days} this week
            </p>
          ) : (
            <p className="mt-1 text-sm text-zinc-400">
              Pick a starter below — or click + Create to choose a mode.
            </p>
          )}
        </div>
        <Link href="/create">
          <Button>+ Create video</Button>
        </Link>
      </div>

      {error ? (
        <Card className="mb-6 border-red-900 bg-red-950/30">
          <CardContent className="pt-5 text-sm text-red-200">
            <div className="font-medium">Could not load dashboard</div>
            <div className="mt-1 text-xs text-red-300/80">{error}</div>
          </CardContent>
        </Card>
      ) : null}

      {/* Insights row */}
      {insights ? <InsightsRow insights={insights} /> : null}

      {/* Saved prompts (when present) */}
      {presets.length > 0 ? (
        <section className="mb-8">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-400">
              Your presets
            </h2>
            <Link
              href="/presets"
              className="text-xs text-zinc-500 hover:text-zinc-300"
            >
              manage all →
            </Link>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {presets.slice(0, 6).map((p) => (
              <Card key={p.id} className="transition hover:border-blue-700/40">
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-base">{p.label}</CardTitle>
                    <Badge tone="muted">{p.template}</Badge>
                  </div>
                  <CardDescription className="text-xs">
                    used {p.use_count}× ·{" "}
                    {p.last_used_at
                      ? `last ${new Date(p.last_used_at).toLocaleDateString()}`
                      : "never used"}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex gap-2 pt-0">
                  <Button size="sm" onClick={() => onUsePreset(p.id)}>
                    Use →
                  </Button>
                  <button
                    type="button"
                    onClick={() => onDeletePreset(p.id)}
                    className="ml-auto text-xs text-zinc-500 hover:text-red-300"
                  >
                    delete
                  </button>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      ) : null}

      {/* Projects */}
      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-400">
          Recent projects
        </h2>
        {loading && projects.length === 0 ? (
          <p className="text-sm text-zinc-500">Loading…</p>
        ) : projects.length === 0 ? (
          <Card>
            <CardHeader>
              <CardTitle>No projects yet</CardTitle>
              <CardDescription>
                Three ways to start:
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-3">
              <Link href="/create/ai_story">
                <Button>Try AI Story</Button>
              </Link>
              <Link href="/create/reddit_story">
                <Button variant="outline">Try Reddit Story</Button>
              </Link>
              {presets.length > 0 ? (
                <Link href="/presets">
                  <Button variant="outline">Use saved preset</Button>
                </Link>
              ) : (
                <Link href="/templates">
                  <Button variant="outline">Browse all templates</Button>
                </Link>
              )}
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4">
            {projects.map((p) => (
              <Link key={p.id} href={`/projects/${p.id}`}>
                <Card className="transition-colors hover:bg-zinc-900/40">
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle>{p.name}</CardTitle>
                      <span className="text-xs text-zinc-500">{p.template}</span>
                    </div>
                    <CardDescription>
                      updated {new Date(p.updated_at).toLocaleString()}
                    </CardDescription>
                  </CardHeader>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </section>
    </AppShell>
  );
}


function InsightsRow({ insights }: { insights: InsightsResponse }) {
  const router = useRouter();
  const onTrySuggestion = (templateId: string) => {
    router.push(`/create/${templateId}`);
  };
  return (
    <section className="mb-8 grid gap-4 sm:grid-cols-2">
      {insights.best_template ? (
        <Card className="border-emerald-700/40 bg-emerald-950/10">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">
                Your top format: {insights.best_template.template_name}
              </CardTitle>
              <Badge tone="ok">
                {Math.round(insights.best_template.star_rate * 100)}% starred
              </Badge>
            </div>
            <CardDescription>
              {insights.best_template.starred} starred ·{" "}
              {insights.best_template.renders} rendered
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link href={`/create/${insights.best_template.template}`}>
              <Button>Make another →</Button>
            </Link>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Welcome 👋</CardTitle>
            <CardDescription>
              Render a few videos and star the best ones — we&apos;ll start
              recommending your top format here.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Try this today</CardTitle>
          <CardDescription>
            Hand-picked starters tuned for high engagement.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {insights.suggestions.slice(0, 3).map((s, i) => (
            <button
              key={`${s.template}-${i}`}
              type="button"
              onClick={() => onTrySuggestion(s.template)}
              className="block w-full rounded-md border border-zinc-800 bg-zinc-950/40 p-3 text-left transition hover:border-blue-700/60 hover:bg-zinc-900/40"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-zinc-100">
                  {s.label}
                </span>
                <Badge tone="muted">{s.template}</Badge>
              </div>
              <div className="mt-1 text-xs text-zinc-500">{s.reason}</div>
            </button>
          ))}
        </CardContent>
      </Card>
    </section>
  );
}
