"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { use, useState } from "react";

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
import { Textarea } from "@/components/ui/textarea";
import { createProject } from "@/lib/api";

const KNOWN_TEMPLATES = ["ai_story", "reddit_story", "voiceover", "auto_captions"];

export default function CreateProjectPage({
  params,
}: {
  params: Promise<{ template: string }>;
}) {
  const { template } = use(params);
  const router = useRouter();
  const { getToken } = useAuth();

  if (!KNOWN_TEMPLATES.includes(template)) {
    return (
      <AppShell>
        <Card className="max-w-xl">
          <CardHeader>
            <CardTitle>Unknown template: {template}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-zinc-400">
            Pick one of the known Phase 1 templates from the gallery.
          </CardContent>
        </Card>
      </AppShell>
    );
  }

  if (template === "ai_story") {
    return <AIStoryForm router={router} getToken={getToken} />;
  }

  // Other templates land in PR 9.
  return (
    <AppShell>
      <Card className="max-w-xl">
        <CardHeader>
          <CardTitle>{template} form coming in PR 9</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-zinc-400">
          The AI Story form is wired up; the other three Phase 1 templates
          (reddit_story, voiceover, auto_captions) are scheduled for the
          next PR.
        </CardContent>
      </Card>
    </AppShell>
  );
}

function AIStoryForm({
  router,
  getToken,
}: {
  router: ReturnType<typeof useRouter>;
  getToken: ReturnType<typeof useAuth>["getToken"];
}) {
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [duration, setDuration] = useState(20);
  const [aspect, setAspect] = useState<"9:16" | "16:9" | "1:1">("9:16");
  const [style, setStyle] = useState("");
  const [seed, setSeed] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const project = await createProject(
        {
          template: "ai_story",
          name: name || prompt.slice(0, 60),
          template_input: {
            prompt,
            duration,
            aspect,
            ...(style ? { style } : {}),
            ...(seed ? { seed: Number(seed) } : {}),
          },
        },
        token,
      );
      router.push(`/projects/${project.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "create failed");
      setSubmitting(false);
    }
  }

  return (
    <AppShell>
      <h1 className="mb-1 text-2xl font-semibold tracking-tight">AI Story Video</h1>
      <p className="mb-8 max-w-2xl text-sm text-zinc-400">
        One prompt → a cinematic 9:16 short with VO + captions + bg music.
        You&apos;ll preview the plan before paying GPU time.
      </p>

      <form onSubmit={onSubmit} className="grid max-w-2xl gap-5">
        <div className="grid gap-2">
          <Label htmlFor="name">Project name (optional)</Label>
          <Input
            id="name"
            placeholder="auto: first 60 chars of prompt"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="prompt">Prompt *</Label>
          <Textarea
            id="prompt"
            required
            minLength={10}
            maxLength={2000}
            rows={5}
            placeholder="Make a motivational video about discipline. Cinematic, intense."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
          <p className="text-xs text-zinc-500">
            10–2000 characters. Style cues like &quot;cinematic&quot;,
            &quot;dreamy&quot;, &quot;neon&quot; steer the look.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <div className="grid gap-2">
            <Label htmlFor="duration">Duration (sec)</Label>
            <Input
              id="duration"
              type="number"
              min={8}
              max={60}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="aspect">Aspect</Label>
            <select
              id="aspect"
              value={aspect}
              onChange={(e) => setAspect(e.target.value as typeof aspect)}
              className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100"
            >
              <option value="9:16">9:16 — Shorts/Reels</option>
              <option value="16:9">16:9 — landscape</option>
              <option value="1:1">1:1 — square</option>
            </select>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="seed">Seed (optional)</Label>
            <Input
              id="seed"
              type="text"
              placeholder="leave blank = fresh each time"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
            />
          </div>
        </div>

        <div className="grid gap-2">
          <Label htmlFor="style">Style cue (optional)</Label>
          <Input
            id="style"
            placeholder="e.g. cinematic, dreamy, neon"
            value={style}
            onChange={(e) => setStyle(e.target.value)}
          />
        </div>

        {error ? (
          <Card className="border-red-900 bg-red-950/30">
            <CardContent className="py-3 text-sm text-red-200">{error}</CardContent>
          </Card>
        ) : null}

        <div className="flex items-center gap-3">
          <Button type="submit" disabled={submitting || prompt.length < 10}>
            {submitting ? "Creating…" : "Create project"}
          </Button>
          <span className="text-xs text-zinc-500">
            You&apos;ll preview the plan before rendering.
          </span>
        </div>
      </form>
    </AppShell>
  );
}
