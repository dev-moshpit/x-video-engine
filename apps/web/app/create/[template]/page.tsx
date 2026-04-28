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

const KNOWN_TEMPLATES = [
  "ai_story",
  "reddit_story",
  "voiceover",
  "auto_captions",
] as const;

type TemplateId = (typeof KNOWN_TEMPLATES)[number];

const TITLES: Record<TemplateId, { name: string; tagline: string }> = {
  ai_story: {
    name: "AI Story Video",
    tagline:
      "One prompt → cinematic 9:16 short with VO + captions + bg music. Preview the plan before paying GPU time.",
  },
  reddit_story: {
    name: "Reddit Story Video",
    tagline:
      "Drop a Reddit post (subreddit + title + body) — we narrate it dramatically over generated visuals.",
  },
  voiceover: {
    name: "Voiceover Video",
    tagline:
      "Bring your script. We add an AI voice, captions, and a solid-color background.",
  },
  auto_captions: {
    name: "Auto-Captions Video",
    tagline:
      "Script → AI voice → big bold burned captions over a flat background. Audio upload + transcription lands in Phase 2.",
  },
};

const CAPTION_STYLES = [
  "bold_word",
  "kinetic_word",
  "clean_subtitle",
  "impact_uppercase",
  "minimal_lower_third",
  "karaoke_3word",
] as const;

export default function CreateProjectPage({
  params,
}: {
  params: Promise<{ template: string }>;
}) {
  const { template } = use(params);
  const router = useRouter();
  const { getToken } = useAuth();

  if (!KNOWN_TEMPLATES.includes(template as TemplateId)) {
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

  const meta = TITLES[template as TemplateId];

  return (
    <AppShell>
      <h1 className="mb-1 text-2xl font-semibold tracking-tight">{meta.name}</h1>
      <p className="mb-8 max-w-2xl text-sm text-zinc-400">{meta.tagline}</p>

      {template === "ai_story" ? (
        <AIStoryForm router={router} getToken={getToken} />
      ) : template === "reddit_story" ? (
        <RedditStoryForm router={router} getToken={getToken} />
      ) : template === "voiceover" ? (
        <VoiceoverForm router={router} getToken={getToken} />
      ) : (
        <AutoCaptionsForm router={router} getToken={getToken} />
      )}
    </AppShell>
  );
}

// ─── Shared helpers ─────────────────────────────────────────────────────

type RouterT = ReturnType<typeof useRouter>;
type GetTokenT = ReturnType<typeof useAuth>["getToken"];

function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <Card className="border-red-900 bg-red-950/30">
      <CardContent className="py-3 text-sm text-red-200">{error}</CardContent>
    </Card>
  );
}

function AspectSelect({
  value,
  onChange,
}: {
  value: "9:16" | "16:9" | "1:1";
  onChange: (v: "9:16" | "16:9" | "1:1") => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as "9:16" | "16:9" | "1:1")}
      className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100"
    >
      <option value="9:16">9:16 — Shorts/Reels</option>
      <option value="16:9">16:9 — landscape</option>
      <option value="1:1">1:1 — square</option>
    </select>
  );
}

function CaptionStyleSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100"
    >
      {CAPTION_STYLES.map((s) => (
        <option key={s} value={s}>
          {s}
        </option>
      ))}
    </select>
  );
}

async function submitProject(
  router: RouterT,
  getToken: GetTokenT,
  payload: {
    template: TemplateId;
    name: string;
    template_input: Record<string, unknown>;
  },
  setError: (e: string | null) => void,
  setSubmitting: (b: boolean) => void,
) {
  setSubmitting(true);
  setError(null);
  try {
    const token = await getToken();
    if (!token) throw new Error("not signed in");
    const project = await createProject(payload, token);
    router.push(`/projects/${project.id}`);
  } catch (e) {
    setError(e instanceof Error ? e.message : "create failed");
    setSubmitting(false);
  }
}

// ─── AI Story ───────────────────────────────────────────────────────────

function AIStoryForm({ router, getToken }: { router: RouterT; getToken: GetTokenT }) {
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [duration, setDuration] = useState(20);
  const [aspect, setAspect] = useState<"9:16" | "16:9" | "1:1">("9:16");
  const [style, setStyle] = useState("");
  const [seed, setSeed] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submitProject(
          router,
          getToken,
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
          setError,
          setSubmitting,
        );
      }}
      className="grid max-w-2xl gap-5"
    >
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
        <p className="text-xs text-zinc-500">10–2000 characters.</p>
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
          <AspectSelect value={aspect} onChange={setAspect} />
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

      <ErrorBox error={error} />

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={submitting || prompt.length < 10}>
          {submitting ? "Creating…" : "Create project"}
        </Button>
        <span className="text-xs text-zinc-500">
          You&apos;ll preview the plan before rendering.
        </span>
      </div>
    </form>
  );
}

// ─── Reddit Story ───────────────────────────────────────────────────────

function RedditStoryForm({ router, getToken }: { router: RouterT; getToken: GetTokenT }) {
  const [name, setName] = useState("");
  const [subreddit, setSubreddit] = useState("AskReddit");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [duration, setDuration] = useState(30);
  const [voiceName, setVoiceName] = useState("");
  const [captionStyle, setCaptionStyle] = useState("kinetic_word");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submitProject(
          router,
          getToken,
          {
            template: "reddit_story",
            name: name || title.slice(0, 60),
            template_input: {
              subreddit,
              title,
              body,
              duration,
              caption_style: captionStyle,
              ...(voiceName ? { voice_name: voiceName } : {}),
            },
          },
          setError,
          setSubmitting,
        );
      }}
      className="grid max-w-2xl gap-5"
    >
      <div className="grid gap-2">
        <Label htmlFor="name">Project name (optional)</Label>
        <Input
          id="name"
          placeholder="auto: first 60 chars of title"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor="subreddit">Subreddit *</Label>
          <Input
            id="subreddit"
            required
            value={subreddit}
            onChange={(e) => setSubreddit(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="duration">Duration (sec)</Label>
          <Input
            id="duration"
            type="number"
            min={8}
            max={90}
            value={duration}
            onChange={(e) => setDuration(Number(e.target.value))}
          />
        </div>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="title">Post title *</Label>
        <Input
          id="title"
          required
          maxLength={300}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="body">Post body *</Label>
        <Textarea
          id="body"
          required
          minLength={10}
          maxLength={8000}
          rows={6}
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor="voice_name">Voice (optional)</Label>
          <Input
            id="voice_name"
            placeholder="e.g. en-US-GuyNeural"
            value={voiceName}
            onChange={(e) => setVoiceName(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="cap_style">Caption style</Label>
          <CaptionStyleSelect value={captionStyle} onChange={setCaptionStyle} />
        </div>
      </div>

      <ErrorBox error={error} />

      <div className="flex items-center gap-3">
        <Button
          type="submit"
          disabled={
            submitting ||
            title.length < 1 ||
            body.length < 10 ||
            subreddit.length < 1
          }
        >
          {submitting ? "Creating…" : "Create project"}
        </Button>
      </div>
    </form>
  );
}

// ─── Voiceover ──────────────────────────────────────────────────────────

function VoiceoverForm({ router, getToken }: { router: RouterT; getToken: GetTokenT }) {
  const [name, setName] = useState("");
  const [script, setScript] = useState("");
  const [aspect, setAspect] = useState<"9:16" | "16:9" | "1:1">("9:16");
  const [bgColor, setBgColor] = useState("#0b0b0f");
  const [voiceName, setVoiceName] = useState("");
  const [captionStyle, setCaptionStyle] = useState("bold_word");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submitProject(
          router,
          getToken,
          {
            template: "voiceover",
            name: name || script.slice(0, 60),
            template_input: {
              script,
              aspect,
              background_color: bgColor,
              caption_style: captionStyle,
              ...(voiceName ? { voice_name: voiceName } : {}),
            },
          },
          setError,
          setSubmitting,
        );
      }}
      className="grid max-w-2xl gap-5"
    >
      <div className="grid gap-2">
        <Label htmlFor="name">Project name (optional)</Label>
        <Input
          id="name"
          placeholder="auto: first 60 chars of script"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="script">Script *</Label>
        <Textarea
          id="script"
          required
          minLength={10}
          maxLength={8000}
          rows={8}
          placeholder="What the AI voice should say, top to bottom."
          value={script}
          onChange={(e) => setScript(e.target.value)}
        />
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <div className="grid gap-2">
          <Label htmlFor="aspect">Aspect</Label>
          <AspectSelect value={aspect} onChange={setAspect} />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="bg">Background color</Label>
          <Input
            id="bg"
            type="text"
            pattern="^#[0-9a-fA-F]{6}$"
            value={bgColor}
            onChange={(e) => setBgColor(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="cap_style">Caption style</Label>
          <CaptionStyleSelect value={captionStyle} onChange={setCaptionStyle} />
        </div>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="voice_name">Voice (optional)</Label>
        <Input
          id="voice_name"
          placeholder="e.g. en-US-AriaNeural"
          value={voiceName}
          onChange={(e) => setVoiceName(e.target.value)}
        />
      </div>

      <ErrorBox error={error} />

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={submitting || script.length < 10}>
          {submitting ? "Creating…" : "Create project"}
        </Button>
      </div>
    </form>
  );
}

// ─── Auto-Captions ──────────────────────────────────────────────────────

function AutoCaptionsForm({ router, getToken }: { router: RouterT; getToken: GetTokenT }) {
  const [name, setName] = useState("");
  const [script, setScript] = useState("");
  const [language, setLanguage] = useState("en");
  const [aspect, setAspect] = useState<"9:16" | "16:9" | "1:1">("9:16");
  const [bgColor, setBgColor] = useState("#0b0b0f");
  const [voiceName, setVoiceName] = useState("");
  const [captionStyle, setCaptionStyle] = useState("bold_word");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submitProject(
          router,
          getToken,
          {
            template: "auto_captions",
            name: name || script.slice(0, 60),
            template_input: {
              script,
              language,
              aspect,
              background_color: bgColor,
              caption_style: captionStyle,
              ...(voiceName ? { voice_name: voiceName } : {}),
            },
          },
          setError,
          setSubmitting,
        );
      }}
      className="grid max-w-2xl gap-5"
    >
      <div className="grid gap-2">
        <Label htmlFor="name">Project name (optional)</Label>
        <Input
          id="name"
          placeholder="auto: first 60 chars of script"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="script">Script *</Label>
        <Textarea
          id="script"
          required
          minLength={10}
          maxLength={8000}
          rows={8}
          placeholder="The text to caption. AI voice reads it; words appear word-by-word."
          value={script}
          onChange={(e) => setScript(e.target.value)}
        />
        <p className="text-xs text-zinc-500">
          Phase 1 is script-only. Audio/video upload + transcription is
          scheduled for Phase 2.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="grid gap-2">
          <Label htmlFor="lang">Language</Label>
          <Input
            id="lang"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="aspect">Aspect</Label>
          <AspectSelect value={aspect} onChange={setAspect} />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="bg">Bg color</Label>
          <Input
            id="bg"
            type="text"
            pattern="^#[0-9a-fA-F]{6}$"
            value={bgColor}
            onChange={(e) => setBgColor(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="cap_style">Caption style</Label>
          <CaptionStyleSelect value={captionStyle} onChange={setCaptionStyle} />
        </div>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="voice_name">Voice (optional)</Label>
        <Input
          id="voice_name"
          placeholder="e.g. en-US-AriaNeural"
          value={voiceName}
          onChange={(e) => setVoiceName(e.target.value)}
        />
      </div>

      <ErrorBox error={error} />

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={submitting || script.length < 10}>
          {submitting ? "Creating…" : "Create project"}
        </Button>
      </div>
    </form>
  );
}
