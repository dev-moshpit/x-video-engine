"use client";

import { useAuth } from "@clerk/nextjs";
import { use, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { ProjectEditor } from "@/components/project-editor";
import { PublishPanel } from "@/components/publish-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  clearRenderFeedback,
  createRender,
  getProject,
  getRender,
  previewPlan,
  rejectRender,
  starRender,
  type GeneratedPlan,
  type ProjectDetail,
  type RenderSummary,
} from "@/lib/api";

const TERMINAL: Array<RenderSummary["stage"]> = ["complete", "failed"];

export default function ProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { getToken } = useAuth();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [plans, setPlans] = useState<GeneratedPlan[]>([]);
  const [recommendedIndex, setRecommendedIndex] = useState<number | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [render, setRender] = useState<RenderSummary | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [needsUpgrade, setNeedsUpgrade] = useState(false);

  // Initial project load
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        if (!token) throw new Error("not signed in");
        const p = await getProject(id, token);
        if (cancelled) return;
        setProject(p);
        // If there's already an in-flight render, hydrate it.
        const latest = p.renders[0];
        if (latest && !TERMINAL.includes(latest.stage)) setRender(latest);
        else if (latest) setRender(latest);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "load failed");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, getToken]);

  // Poll active render every 2s
  useEffect(() => {
    if (!render) return;
    if (TERMINAL.includes(render.stage)) return;
    const t = setInterval(async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const fresh = await getRender(render.id, token);
        setRender(fresh);
      } catch {
        // swallow; next tick will retry
      }
    }, 2000);
    return () => clearInterval(t);
  }, [render, getToken]);

  async function onPreview(variations: number = 1) {
    setPreviewing(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const res = await previewPlan(id, { variations }, token);
      setPlans(res.plans);
      setRecommendedIndex(
        typeof res.recommended_index === "number" ? res.recommended_index : null,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "preview failed");
    } finally {
      setPreviewing(false);
    }
  }

  async function onRender() {
    setSubmitting(true);
    setNeedsUpgrade(false);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const r = await createRender(id, token);
      setRender(r);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "render failed";
      // Phase 3: 402 Payment Required — show the upgrade prompt
      // instead of a generic error banner so the user knows what to
      // do next.
      if (msg.includes("402")) setNeedsUpgrade(true);
      else setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  if (error && !project) {
    return (
      <AppShell>
        <Card className="border-red-900 bg-red-950/30">
          <CardContent className="pt-5 text-sm text-red-200">{error}</CardContent>
        </Card>
      </AppShell>
    );
  }

  if (!project) {
    return (
      <AppShell>
        <p className="text-sm text-zinc-500">Loading project…</p>
      </AppShell>
    );
  }

  const supportsPlanPreview =
    project.template === "ai_story" || project.template === "reddit_story";

  return (
    <AppShell>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">{project.name}</h1>
        <div className="mt-2 flex items-center gap-3 text-xs text-zinc-500">
          <Badge>{project.template}</Badge>
          <span>created {new Date(project.created_at).toLocaleString()}</span>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="grid gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Inputs</CardTitle>
              <CardDescription>
                Pydantic-validated payload sent to the worker.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <pre className="overflow-auto rounded-md border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-300">
                {JSON.stringify(project.template_input, null, 2)}
              </pre>
              <ProjectEditor
                projectId={project.id}
                template={project.template}
                initialInput={project.template_input}
                onSaved={(next) =>
                  setProject((p) =>
                    p ? { ...p, template_input: next } : p,
                  )
                }
              />
            </CardContent>
            <CardFooter>
              {supportsPlanPreview ? (
                <>
                  <Button
                    variant="outline"
                    onClick={() => onPreview(1)}
                    disabled={previewing}
                  >
                    {previewing ? "Generating…" : "Preview plan"}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => onPreview(5)}
                    disabled={previewing}
                  >
                    Generate 5 variations
                  </Button>
                </>
              ) : null}
              <Button
                onClick={onRender}
                disabled={
                  submitting || (!!render && !TERMINAL.includes(render.stage))
                }
              >
                {submitting
                  ? "Submitting…"
                  : render && !TERMINAL.includes(render.stage)
                    ? "Render in progress…"
                    : "Render"}
              </Button>
            </CardFooter>
          </Card>

          {render ? <RenderStatusCard render={render} /> : null}

          {render && render.stage === "complete" && render.final_mp4_url ? (
            <PublishPanel
              projectId={project.id}
              finalMp4Url={render.final_mp4_url}
            />
          ) : null}
        </section>

        <section className="grid gap-4">
          {plans.length === 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>Plan preview</CardTitle>
                <CardDescription>
                  {supportsPlanPreview
                    ? "Click \"Preview plan\" to see the generated hook, scenes, and score before rendering."
                    : "This template renders directly without a plan stage."}
                </CardDescription>
              </CardHeader>
            </Card>
          ) : (
            plans.map((p, i) => (
              <PlanCard
                key={i}
                plan={p}
                index={i}
                isRecommended={recommendedIndex === i && plans.length > 1}
              />
            ))
          )}
        </section>
      </div>

      {needsUpgrade ? (
        <Card className="mt-6 border-amber-700/60 bg-amber-950/20">
          <CardContent className="flex items-center justify-between py-4">
            <div className="text-sm text-amber-100">
              <div className="font-medium">You&apos;re out of render credits.</div>
              <div className="text-xs text-amber-200/80">
                Upgrade your plan to keep rendering. Free tier refills monthly.
              </div>
            </div>
            <a href="/pricing">
              <Button>Upgrade →</Button>
            </a>
          </CardContent>
        </Card>
      ) : null}

      {error ? (
        <Card className="mt-6 border-red-900 bg-red-950/30">
          <CardContent className="py-3 text-sm text-red-200">{error}</CardContent>
        </Card>
      ) : null}
    </AppShell>
  );
}

function PlanCard({
  plan, index = 0, isRecommended = false,
}: {
  plan: GeneratedPlan;
  index?: number;
  isRecommended?: boolean;
}) {
  const { video_plan: vp, score, warnings } = plan;
  return (
    <Card
      className={
        isRecommended
          ? "border-emerald-700/60 ring-1 ring-emerald-700/40"
          : ""
      }
    >
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="mb-1 flex items-center gap-2">
              <CardTitle>{vp.title}</CardTitle>
              {isRecommended ? (
                <Badge tone="ok">recommended (highest score)</Badge>
              ) : (
                <Badge tone="muted">variation {index + 1}</Badge>
              )}
            </div>
            <CardDescription className="mt-1 italic">{vp.hook}</CardDescription>
          </div>
          <Badge tone={score.total >= 70 ? "ok" : "warn"}>
            score {score.total.toFixed(1)} / 100
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div>
          <Label>Concept</Label>
          <p className="mt-1 text-zinc-300">{vp.concept}</p>
        </div>
        <div>
          <Label>Scenes ({vp.scenes.length})</Label>
          <ul className="mt-1 space-y-1 text-xs text-zinc-400">
            {vp.scenes.map((s) => (
              <li key={s.scene_id}>
                <span className="font-mono text-zinc-500">{s.scene_id}</span>{" "}
                · {s.duration.toFixed(1)}s · {s.subject} ·{" "}
                <span className="italic">{s.camera_motion}</span>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <Label>Voiceover</Label>
          <ul className="mt-1 space-y-1 text-xs text-zinc-400">
            {vp.voiceover_lines.map((line, i) => (
              <li key={i}>· {line}</li>
            ))}
          </ul>
        </div>
        <div>
          <Label>CTA</Label>
          <p className="mt-1 text-zinc-300">{vp.cta}</p>
        </div>
        {warnings.length > 0 ? (
          <div>
            <Label>Audit warnings</Label>
            <ul className="mt-1 space-y-1 text-xs text-amber-300">
              {warnings.map((w, i) => (
                <li key={i}>⚠ {w}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function RenderStatusCard({ render }: { render: RenderSummary }) {
  const { getToken } = useAuth();
  const [current, setCurrent] = useState(render);
  // Sync external updates (the parent's poll) into local state.
  useEffect(() => {
    setCurrent(render);
  }, [render]);

  const isComplete = current.stage === "complete";
  const isFailed = current.stage === "failed";

  async function applyFeedback(
    next: "star" | "reject" | "clear",
  ) {
    try {
      const token = await getToken();
      if (!token) return;
      let updated: RenderSummary;
      if (next === "star") updated = await starRender(current.id, token);
      else if (next === "reject") updated = await rejectRender(current.id, token);
      else updated = await clearRenderFeedback(current.id, token);
      setCurrent(updated);
    } catch {
      // swallow — UI keeps the previous state
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Render</CardTitle>
          <Badge tone={isComplete ? "ok" : isFailed ? "error" : "warn"}>
            {current.stage}
          </Badge>
        </div>
        <CardDescription>
          job <span className="font-mono">{current.job_id}</span>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-900">
          <div
            className="h-full bg-emerald-500 transition-all"
            style={{ width: `${Math.round(current.progress * 100)}%` }}
          />
        </div>
        <div className="text-xs text-zinc-500">
          {Math.round(current.progress * 100)}%
          {current.completed_at
            ? ` · finished ${new Date(current.completed_at).toLocaleTimeString()}`
            : ` · started ${new Date(current.started_at).toLocaleTimeString()}`}
        </div>
        {isFailed && current.error ? (
          <p className="rounded-md border border-red-900 bg-red-950/40 p-2 text-xs text-red-200">
            {current.error}
          </p>
        ) : null}
        {isComplete && current.final_mp4_url ? (
          <div className="space-y-3">
            <video
              src={current.final_mp4_url}
              controls
              className="w-full rounded-md border border-zinc-800"
            />
            <div className="flex flex-wrap items-center gap-2">
              <a
                href={current.final_mp4_url}
                download
                className="text-sm text-zinc-300 hover:text-zinc-100 underline-offset-4 hover:underline"
              >
                Download MP4 ↓
              </a>
              <span className="ml-auto flex gap-2">
                <Button
                  size="sm"
                  variant={current.starred === true ? "default" : "outline"}
                  onClick={() => applyFeedback("star")}
                  title="Mark this render as a winner"
                >
                  ★ Star
                </Button>
                <Button
                  size="sm"
                  variant={current.starred === false ? "destructive" : "outline"}
                  onClick={() => applyFeedback("reject")}
                  title="Mark this render as a reject"
                >
                  ✕ Reject
                </Button>
                {current.starred !== null ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => applyFeedback("clear")}
                    title="Clear feedback"
                  >
                    ↺ Clear
                  </Button>
                ) : null}
              </span>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
