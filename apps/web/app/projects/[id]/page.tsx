"use client";

import { useAuth } from "@clerk/nextjs";
import { use, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { ExportVariants } from "@/components/export-variants";
import { ProjectEditor } from "@/components/project-editor";
import { PublishPanel } from "@/components/publish-panel";
import { SavePresetButton } from "@/components/save-preset-button";
import { SharePreviewButton } from "@/components/share-preview-button";
import { UpgradeModal } from "@/components/upgrade-modal";
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
  createRenderBatch,
  getBillingStatus,
  getProject,
  getRender,
  previewPlan,
  rejectRender,
  smartGenerate,
  starRender,
  type BillingStatus,
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
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [plans, setPlans] = useState<GeneratedPlan[]>([]);
  const [recommendedIndex, setRecommendedIndex] = useState<number | null>(null);
  const [smartReasoning, setSmartReasoning] = useState<string[]>([]);
  const [previewing, setPreviewing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [needsUpgrade, setNeedsUpgrade] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Pull billing status for the credit-cost / balance pill below "Generate".
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const s = await getBillingStatus(token);
        if (!cancelled) setBilling(s);
      } catch {
        /* leave null — pill simply doesn't show */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [getToken]);

  // Initial project load.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        if (!token) throw new Error("not signed in");
        const p = await getProject(id, token);
        if (cancelled) return;
        setProject(p);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "load failed");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, getToken]);

  // Poll any active render every 2s; refresh the project when one completes
  // so the variation comparison view picks up new MP4 URLs.
  useEffect(() => {
    if (!project) return;
    const active = project.renders.filter((r) => !TERMINAL.includes(r.stage));
    if (active.length === 0) return;
    const t = setInterval(async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const refreshed = await Promise.all(
          active.map((r) => getRender(r.id, token).catch(() => r)),
        );
        setProject((prev) => {
          if (!prev) return prev;
          const byId = new Map(refreshed.map((r) => [r.id, r]));
          return {
            ...prev,
            renders: prev.renders.map((r) => byId.get(r.id) ?? r),
          };
        });
      } catch {
        /* swallow */
      }
    }, 2000);
    return () => clearInterval(t);
  }, [project, getToken]);

  async function refreshProject() {
    try {
      const token = await getToken();
      if (!token) return;
      const p = await getProject(id, token);
      setProject(p);
    } catch {
      /* swallow */
    }
  }

  async function onSmartGenerate() {
    setSubmitting(true);
    setNeedsUpgrade(false);
    setError(null);
    setSmartReasoning([]);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const res = await smartGenerate(
        id,
        { candidates: 3, render_top: 1 },
        token,
      );
      setPlans(res.plans);
      setRecommendedIndex(res.best_index);
      setSmartReasoning(res.reasoning);
      // Surface freshly enqueued renders.
      await refreshProject();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "smart generate failed";
      if (msg.includes("402")) setNeedsUpgrade(true);
      else setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  async function onPreview(variations: number) {
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
      setSmartReasoning([]);
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
      await createRender(id, token);
      await refreshProject();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "render failed";
      if (msg.includes("402")) setNeedsUpgrade(true);
      else setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  async function onRenderBatch(count: number) {
    setSubmitting(true);
    setNeedsUpgrade(false);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      await createRenderBatch(id, count, token);
      await refreshProject();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "batch render failed";
      if (msg.includes("402")) setNeedsUpgrade(true);
      else setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  async function onRegenerateSimilar() {
    // Same project_input, fresh seeds → 2 more candidates.
    await onRenderBatch(2);
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
      <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{project.name}</h1>
          <div className="mt-2 flex items-center gap-3 text-xs text-zinc-500">
            <Badge>{project.template}</Badge>
            <span>created {new Date(project.created_at).toLocaleString()}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <SavePresetButton
            template={project.template}
            templateInput={project.template_input}
            defaultLabel={project.name}
          />
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
            <CardFooter className="flex flex-wrap items-center gap-3">
              <Button
                size="lg"
                onClick={onSmartGenerate}
                disabled={submitting}
                className="font-semibold"
              >
                {submitting ? "Generating…" : "Generate Video →"}
              </Button>
              <CreditCostPill billing={billing} cost={1} />
              <span className="text-xs text-zinc-500">
                Plans 3 → scores → renders the best one.
              </span>
              <button
                type="button"
                onClick={() => setShowAdvanced((v) => !v)}
                className="ml-auto text-xs text-zinc-500 hover:text-zinc-300"
              >
                {showAdvanced ? "Hide advanced" : "Advanced ↓"}
              </button>
            </CardFooter>
            {showAdvanced ? (
              <div className="border-t border-zinc-900 px-6 py-4">
                <div className="flex flex-wrap gap-2">
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
                        Preview 5 variations
                      </Button>
                    </>
                  ) : null}
                  <Button
                    variant="outline"
                    onClick={onRender}
                    disabled={submitting}
                  >
                    Render once
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => onRenderBatch(3)}
                    disabled={submitting}
                  >
                    Render 3×
                  </Button>
                  <Button
                    variant="outline"
                    onClick={onRegenerateSimilar}
                    disabled={submitting}
                    title="Render two more variations of the current configuration"
                  >
                    Regenerate Similar
                  </Button>
                </div>
              </div>
            ) : null}
          </Card>

          {smartReasoning.length > 0 ? (
            <Card className="border-emerald-700/40 bg-emerald-950/10">
              <CardHeader>
                <CardTitle className="text-base">
                  Why this plan was picked
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1 text-xs text-emerald-200">
                  {smartReasoning.map((r, i) => (
                    <li key={i}>· {r}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}

          <RenderVariationsView
            projectId={project.id}
            renders={project.renders}
            onChange={refreshProject}
          />

          {(() => {
            const completed = project.renders.filter(
              (r) => r.stage === "complete" && r.final_mp4_url,
            );
            const best =
              completed.find((r) => r.starred === true) ?? completed[0];
            if (!best || !best.final_mp4_url) return null;
            return (
              <PublishPanel
                projectId={project.id}
                finalMp4Url={best.final_mp4_url}
              />
            );
          })()}
        </section>

        <section className="grid gap-4">
          {!supportsPlanPreview || plans.length === 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>Plan preview</CardTitle>
                <CardDescription>
                  {supportsPlanPreview
                    ? "Click \"Generate Video\" to plan, score, and render in one shot — or open Advanced for manual control."
                    : "This template renders directly. Click \"Generate Video\"."}
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

      <UpgradeModal
        open={needsUpgrade}
        onClose={() => setNeedsUpgrade(false)}
        context="render"
      />

      {error ? (
        <Card className="mt-6 border-red-900 bg-red-950/30">
          <CardContent className="py-3 text-sm text-red-200">{error}</CardContent>
        </Card>
      ) : null}
    </AppShell>
  );
}

function PlanCard({
  plan,
  index = 0,
  isRecommended = false,
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
            score {Number(score.total).toFixed(1)} / 100
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

function RenderVariationsView({
  projectId,
  renders,
  onChange,
}: {
  projectId: string;
  renders: RenderSummary[];
  onChange: () => void;
}) {
  const { getToken } = useAuth();
  const sorted = useMemo(
    () =>
      [...renders].sort(
        (a, b) =>
          new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
      ),
    [renders],
  );
  const completed = sorted.filter(
    (r) => r.stage === "complete" && r.final_mp4_url,
  );
  const inProgress = sorted.filter((r) => !TERMINAL.includes(r.stage));
  const failed = sorted.filter((r) => r.stage === "failed");

  if (sorted.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Renders</CardTitle>
          <CardDescription>
            No renders yet — click <strong>Generate Video</strong> to start.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  // Best = highest-starred render; if none starred, the most recent complete.
  const bestId =
    completed.find((r) => r.starred === true)?.id ?? completed[0]?.id;

  const toggleStar = async (renderId: string, current: boolean | null) => {
    try {
      const token = await getToken();
      if (!token) return;
      if (current === true) await clearRenderFeedback(renderId, token);
      else await starRender(renderId, token);
      onChange();
    } catch {
      /* swallow */
    }
  };

  const toggleReject = async (renderId: string, current: boolean | null) => {
    try {
      const token = await getToken();
      if (!token) return;
      if (current === false) await clearRenderFeedback(renderId, token);
      else await rejectRender(renderId, token);
      onChange();
    } catch {
      /* swallow */
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Renders ({sorted.length})</CardTitle>
          <span className="text-xs text-zinc-500">
            {completed.length} complete · {inProgress.length} in progress
            {failed.length ? ` · ${failed.length} failed` : ""}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {inProgress.map((r) => (
          <div
            key={r.id}
            className="rounded-md border border-zinc-800 bg-zinc-950/40 p-3"
          >
            <div className="mb-2 flex items-center justify-between text-xs">
              <span className="font-mono text-zinc-500">{r.job_id}</span>
              <Badge tone="warn">{r.stage}</Badge>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-900">
              <div
                className="h-full bg-emerald-500 transition-all"
                style={{ width: `${Math.round(r.progress * 100)}%` }}
              />
            </div>
            <div className="mt-1 text-[10px] text-zinc-600">
              {Math.round(r.progress * 100)}% · started{" "}
              {new Date(r.started_at).toLocaleTimeString()}
            </div>
          </div>
        ))}

        {completed.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {completed.map((r) => (
              <div
                key={r.id}
                className={
                  "flex flex-col rounded-md border bg-zinc-950/40 p-2 " +
                  (bestId === r.id
                    ? "border-emerald-700/60 ring-1 ring-emerald-700/40"
                    : "border-zinc-800")
                }
              >
                <div className="mb-2 flex items-center justify-between text-[11px]">
                  <span className="font-mono text-zinc-500">{r.job_id}</span>
                  {bestId === r.id ? (
                    <Badge tone="ok">best</Badge>
                  ) : null}
                </div>
                <video
                  src={r.final_mp4_url ?? undefined}
                  controls
                  className="w-full rounded-md border border-zinc-900"
                />
                <div className="mt-2 flex items-center gap-2 text-xs">
                  <button
                    type="button"
                    onClick={() => toggleStar(r.id, r.starred)}
                    className={
                      "rounded px-2 py-1 " +
                      (r.starred === true
                        ? "bg-emerald-600/30 text-emerald-200"
                        : "text-zinc-400 hover:text-zinc-100")
                    }
                  >
                    ★ {r.starred === true ? "Starred" : "Star"}
                  </button>
                  <button
                    type="button"
                    onClick={() => toggleReject(r.id, r.starred)}
                    className={
                      "rounded px-2 py-1 " +
                      (r.starred === false
                        ? "bg-red-700/30 text-red-200"
                        : "text-zinc-400 hover:text-zinc-100")
                    }
                  >
                    ✕ Reject
                  </button>
                  {r.final_mp4_url ? (
                    <a
                      href={r.final_mp4_url}
                      download
                      className="ml-auto rounded border border-zinc-700 px-2 py-1 text-zinc-200 hover:border-blue-600 hover:bg-zinc-900"
                    >
                      ↓ Download
                    </a>
                  ) : null}
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-zinc-900/80 pt-2">
                  <SharePreviewButton jobId={r.job_id} />
                  <ExportVariants jobId={r.job_id} />
                </div>
              </div>
            ))}
          </div>
        ) : null}

        {failed.map((r) => (
          <FailedRender
            key={r.id}
            render={r}
            projectId={projectId}
            onRetry={onChange}
          />
        ))}

      </CardContent>
    </Card>
  );
}


function CreditCostPill({
  billing,
  cost,
}: {
  billing: BillingStatus | null;
  cost: number;
}) {
  const insufficient = billing !== null && billing.balance < cost;
  return (
    <span
      className={
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium " +
        (insufficient
          ? "border-amber-700 bg-amber-950/30 text-amber-200"
          : "border-zinc-700 bg-zinc-900/60 text-zinc-200")
      }
      title={
        billing
          ? `${billing.tier} tier · ${billing.balance} credits left`
          : "Each render costs 1 credit"
      }
    >
      <span aria-hidden>◆</span>
      <span>
        {cost} credit{cost === 1 ? "" : "s"}
      </span>
      {billing ? (
        <span className="text-zinc-500">
          · {billing.balance} left
        </span>
      ) : null}
    </span>
  );
}


function humanizeRenderError(raw: string | null): string {
  if (!raw) return "Render failed before producing an MP4. Try again, or tweak the inputs and retry.";
  const lower = raw.toLowerCase();
  if (lower.includes("timeout") || lower.includes("timed out")) {
    return "The render took too long and was cancelled. The worker may be under load — please retry.";
  }
  if (lower.includes("out of memory") || lower.includes("oom") || lower.includes("cuda")) {
    return "The GPU ran out of memory on this render. Lower the duration or try again later.";
  }
  if (lower.includes("download") || lower.includes("resolve") || lower.includes("404")) {
    return "A media URL in your inputs couldn't be downloaded. Re-pick the asset from your library and retry.";
  }
  if (lower.includes("budget") || lower.includes("402")) {
    return "Out of credits — top up to keep rendering.";
  }
  return "Render failed. Retry, or expand details below to inspect the error.";
}


function FailedRender({
  render,
  projectId,
  onRetry,
}: {
  render: RenderSummary;
  projectId: string;
  onRetry: () => void;
}) {
  const { getToken } = useAuth();
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDetails, setShowDetails] = useState(false);

  const onClick = async () => {
    setRetrying(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      await createRender(projectId, token);
      onRetry();
    } catch (e) {
      setError(e instanceof Error ? e.message : "retry failed");
    } finally {
      setRetrying(false);
    }
  };

  const friendly = humanizeRenderError(render.error);

  return (
    <div className="rounded-md border border-red-900 bg-red-950/20 p-3 text-xs text-red-200">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-red-300/80">{render.job_id}</span>
        <Badge tone="error">failed</Badge>
      </div>
      <p className="mb-3 leading-relaxed text-red-100">{friendly}</p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onClick}
          disabled={retrying}
          className="rounded border border-red-700 bg-red-900/40 px-3 py-1 font-medium text-red-50 hover:bg-red-800/60 disabled:opacity-50"
        >
          {retrying ? "Retrying…" : "↻ Retry render"}
        </button>
        {render.error ? (
          <button
            type="button"
            onClick={() => setShowDetails((v) => !v)}
            className="text-[11px] text-red-300 hover:text-red-100"
          >
            {showDetails ? "Hide details" : "Show details"}
          </button>
        ) : null}
        {error ? (
          <span className="ml-2 text-[10px] text-red-300">{error}</span>
        ) : null}
      </div>
      {showDetails && render.error ? (
        <pre className="mt-2 overflow-auto rounded border border-red-900/60 bg-black/40 p-2 text-[10px] text-red-200/80">
          {render.error}
        </pre>
      ) : null}
    </div>
  );
}
