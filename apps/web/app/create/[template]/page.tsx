"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { use, useState } from "react";

import { AppShell } from "@/components/app-shell";
import {
  CaptionLanguagePicker,
  PacingPicker,
  StylePresetPicker,
} from "@/components/catalog-pickers";
import { MediaPickerButton } from "@/components/media-picker";
import { RecommendationHint } from "@/components/recommendation-hint";
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
  "fake_text",
  "would_you_rather",
  "split_video",
  "twitter",
  "top_five",
  "roblox_rant",
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
      "Script → AI voice → big bold burned captions. Drop in audio/video and we transcribe with Whisper.",
  },
  fake_text: {
    name: "Fake Text Conversation",
    tagline:
      "iOS / WhatsApp / Instagram / Tinder chat-screen video with typing animation and optional voice narration.",
  },
  would_you_rather: {
    name: "Would You Rather",
    tagline:
      "Two-option poll with timer countdown and percentage reveal — engagement-bait gold.",
  },
  split_video: {
    name: "Split Video",
    tagline:
      "Top/bottom or left/right split — your main clip with filler gameplay, voiceover, and burned captions.",
  },
  twitter: {
    name: "Twitter / X Tweet Video",
    tagline:
      "Render a tweet card (single or thread) with realistic metrics, voiceover, and captions.",
  },
  top_five: {
    name: "Top 5 / Countdown",
    tagline:
      "Numbered countdown video — 3 to 10 ranked items with bold overlays, voice, captions.",
  },
  roblox_rant: {
    name: "Roblox Rant",
    tagline:
      "Fast-paced rant with bold impact captions over a gameplay background. Energy at 11.",
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

const VOICES = [
  { id: "en-US-AriaNeural", label: "Aria - clear neutral" },
  { id: "en-US-JennyNeural", label: "Jenny - warm narrator" },
  { id: "en-US-GuyNeural", label: "Guy - dramatic / energetic" },
  { id: "en-US-AndrewNeural", label: "Andrew - cinematic" },
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
      ) : template === "auto_captions" ? (
        <AutoCaptionsForm router={router} getToken={getToken} />
      ) : template === "fake_text" ? (
        <FakeTextForm router={router} getToken={getToken} />
      ) : template === "would_you_rather" ? (
        <WouldYouRatherForm router={router} getToken={getToken} />
      ) : template === "split_video" ? (
        <SplitVideoForm router={router} getToken={getToken} />
      ) : template === "twitter" ? (
        <TwitterForm router={router} getToken={getToken} />
      ) : template === "top_five" ? (
        <TopFiveForm router={router} getToken={getToken} />
      ) : (
        <RobloxRantForm router={router} getToken={getToken} />
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

function VoiceSelect({
  value,
  onChange,
  allowNone = true,
}: {
  value: string;
  onChange: (v: string) => void;
  allowNone?: boolean;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100"
    >
      {allowNone ? <option value="">Template default</option> : null}
      {VOICES.map((voice) => (
        <option key={voice.id} value={voice.id}>
          {voice.label}
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
  const [stylePreset, setStylePreset] = useState<string | undefined>(undefined);
  const [pacing, setPacing] = useState<string | undefined>(undefined);
  const [captionLanguage, setCaptionLanguage] = useState<string | undefined>(undefined);
  const [seed, setSeed] = useState("");
  const [voiceName, setVoiceName] = useState("en-US-AndrewNeural");
  const [captionStyle, setCaptionStyle] = useState("kinetic_word");
  const [musicBed, setMusicBed] = useState("none");
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
              ...(stylePreset ? { style_preset: stylePreset } : {}),
              ...(pacing ? { pacing } : {}),
              ...(captionLanguage ? { caption_language: captionLanguage } : {}),
              ...(seed ? { seed: Number(seed) } : {}),
              ...(voiceName ? { voice_name: voiceName } : {}),
              ...(captionStyle ? { caption_style: captionStyle } : {}),
              ...(musicBed && musicBed !== "none" ? { music_bed: musicBed } : {}),
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

      <RecommendationHint
        template="ai_story"
        onApplyStyle={(v) => setStyle(v)}
      />

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

      <StylePresetPicker value={stylePreset} onChange={setStylePreset} />

      <PacingPicker value={pacing} onChange={setPacing} />

      <div className="grid gap-2">
        <Label htmlFor="style">Style cue (optional, free-form)</Label>
        <Input
          id="style"
          placeholder="overrides preset wording — e.g. cinematic, dreamy, neon"
          value={style}
          onChange={(e) => setStyle(e.target.value)}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="grid gap-2">
          <Label>Voice</Label>
          <VoiceSelect value={voiceName} onChange={setVoiceName} />
        </div>
        <div className="grid gap-2">
          <Label>Caption style</Label>
          <CaptionStyleSelect value={captionStyle} onChange={setCaptionStyle} />
        </div>
        <div className="grid gap-2">
          <Label>Music bed</Label>
          <select
            value={musicBed}
            onChange={(e) => setMusicBed(e.target.value)}
            className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100"
          >
            <option value="none">None</option>
            <option value="auto">Auto if available</option>
          </select>
        </div>
      </div>

      <CaptionLanguagePicker
        value={captionLanguage}
        onChange={setCaptionLanguage}
      />

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
  const [username, setUsername] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [upvotes, setUpvotes] = useState(1200);
  const [comments, setComments] = useState(180);
  const [duration, setDuration] = useState(30);
  const [voiceName, setVoiceName] = useState("en-US-GuyNeural");
  const [captionStyle, setCaptionStyle] = useState("kinetic_word");
  const [stylePreset, setStylePreset] = useState<string | undefined>(undefined);
  const [pacing, setPacing] = useState<string | undefined>(undefined);
  const [captionLanguage, setCaptionLanguage] = useState<string | undefined>(undefined);
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
              upvotes,
              comments,
              duration,
              caption_style: captionStyle,
              ...(username ? { username } : {}),
              ...(voiceName ? { voice_name: voiceName } : {}),
              ...(stylePreset ? { style_preset: stylePreset } : {}),
              ...(pacing ? { pacing } : {}),
              ...(captionLanguage ? { caption_language: captionLanguage } : {}),
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
      <RecommendationHint
        template="reddit_story"
        onApplyCaptionStyle={(v) => setCaptionStyle(v)}
        onApplyVoice={(v) => setVoiceName(v)}
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
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
          <Label>Username</Label>
          <Input
            placeholder="optional"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label>Upvotes</Label>
          <Input
            type="number"
            min={0}
            value={upvotes}
            onChange={(e) => setUpvotes(Number(e.target.value))}
          />
        </div>
        <div className="grid gap-2">
          <Label>Comments</Label>
          <Input
            type="number"
            min={0}
            value={comments}
            onChange={(e) => setComments(Number(e.target.value))}
          />
        </div>
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
          <Label htmlFor="voice_name">Voice</Label>
          <VoiceSelect value={voiceName} onChange={setVoiceName} />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="cap_style">Caption style</Label>
          <CaptionStyleSelect value={captionStyle} onChange={setCaptionStyle} />
        </div>
      </div>

      <StylePresetPicker value={stylePreset} onChange={setStylePreset} />
      <PacingPicker value={pacing} onChange={setPacing} />
      <CaptionLanguagePicker value={captionLanguage} onChange={setCaptionLanguage} />

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
  const [bgUrl, setBgUrl] = useState("");
  const [voiceName, setVoiceName] = useState("en-US-AriaNeural");
  const [captionStyle, setCaptionStyle] = useState("clean_subtitle");
  const [pacing, setPacing] = useState<string | undefined>(undefined);
  const [captionLanguage, setCaptionLanguage] = useState<string | undefined>(undefined);
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
              ...(bgUrl ? { background_url: bgUrl } : {}),
              ...(voiceName ? { voice_name: voiceName } : {}),
              ...(pacing ? { pacing } : {}),
              ...(captionLanguage ? { caption_language: captionLanguage } : {}),
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
      <RecommendationHint
        template="voiceover"
        onApplyCaptionStyle={(v) => setCaptionStyle(v)}
        onApplyVoice={(v) => setVoiceName(v)}
      />

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
        <Label htmlFor="background_url">Background video/image URL</Label>
        <div className="flex gap-2">
          <Input
            id="background_url"
            placeholder="https://... or select from library"
            value={bgUrl}
            onChange={(e) => setBgUrl(e.target.value)}
            className="flex-1"
          />
          <MediaPickerButton
            kind="video"
            label="Select from Library"
            onPick={(url) => setBgUrl(url)}
          />
          <MediaPickerButton
            kind="image"
            label="Image"
            onPick={(url) => setBgUrl(url)}
          />
        </div>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="voice_name">Voice</Label>
        <VoiceSelect value={voiceName} onChange={setVoiceName} />
      </div>

      <PacingPicker value={pacing} onChange={setPacing} />
      <CaptionLanguagePicker value={captionLanguage} onChange={setCaptionLanguage} />

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
  const [audioUrl, setAudioUrl] = useState("");
  const [videoUrl, setVideoUrl] = useState("");
  const [language, setLanguage] = useState("en");
  const [aspect, setAspect] = useState<"9:16" | "16:9" | "1:1">("9:16");
  const [bgColor, setBgColor] = useState("#0b0b0f");
  const [bgUrl, setBgUrl] = useState("");
  const [voiceName, setVoiceName] = useState("en-US-AriaNeural");
  const [captionStyle, setCaptionStyle] = useState("bold_word");
  const [pacing, setPacing] = useState<string | undefined>(undefined);
  const [captionLanguage, setCaptionLanguage] = useState<string | undefined>(undefined);
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
            name: name || script.slice(0, 60) || "Auto-caption upload",
            template_input: {
              script: script || "Transcribe this uploaded media.",
              language,
              aspect,
              background_color: bgColor,
              caption_style: captionStyle,
              ...(bgUrl ? { background_url: bgUrl } : {}),
              ...(audioUrl ? { audio_url: audioUrl } : {}),
              ...(videoUrl ? { video_url: videoUrl } : {}),
              ...(voiceName ? { voice_name: voiceName } : {}),
              ...(pacing ? { pacing } : {}),
              ...(captionLanguage ? { caption_language: captionLanguage } : {}),
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
      <RecommendationHint
        template="auto_captions"
        onApplyCaptionStyle={(v) => setCaptionStyle(v)}
        onApplyVoice={(v) => setVoiceName(v)}
      />

      <div className="grid gap-2">
        <Label htmlFor="script">Script</Label>
        <Textarea
          id="script"
          required={!audioUrl && !videoUrl}
          minLength={audioUrl || videoUrl ? undefined : 10}
          maxLength={8000}
          rows={8}
          placeholder="The text to caption. AI voice reads it; words appear word-by-word."
          value={script}
          onChange={(e) => setScript(e.target.value)}
        />
        <p className="text-xs text-zinc-500">
          Or paste an audio/video URL below to transcribe with Whisper —
          the script is then ignored.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label htmlFor="audio_url">Audio URL (optional)</Label>
          <div className="flex gap-2">
            <Input
              id="audio_url"
              placeholder="https://… .mp3 / .wav"
              value={audioUrl}
              onChange={(e) => setAudioUrl(e.target.value)}
              className="flex-1"
            />
            <MediaPickerButton
              kind="audio"
              label="Select from Library"
              onPick={(url) => setAudioUrl(url)}
            />
          </div>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="video_url">Video URL (optional)</Label>
          <div className="flex gap-2">
            <Input
              id="video_url"
              placeholder="https://… .mp4"
              value={videoUrl}
              onChange={(e) => setVideoUrl(e.target.value)}
              className="flex-1"
            />
            <MediaPickerButton
              kind="video"
              label="Select from Library"
              onPick={(url) => setVideoUrl(url)}
            />
          </div>
        </div>
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
        <Label htmlFor="background_url">Background URL for script-only renders</Label>
        <div className="flex gap-2">
          <Input
            id="background_url"
            value={bgUrl}
            onChange={(e) => setBgUrl(e.target.value)}
            className="flex-1"
          />
          <MediaPickerButton
            kind="video"
            label="Select from Library"
            onPick={(url) => setBgUrl(url)}
          />
          <MediaPickerButton
            kind="image"
            label="Image"
            onPick={(url) => setBgUrl(url)}
          />
        </div>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="voice_name">Voice</Label>
        <VoiceSelect value={voiceName} onChange={setVoiceName} />
      </div>

      <PacingPicker value={pacing} onChange={setPacing} />
      <CaptionLanguagePicker value={captionLanguage} onChange={setCaptionLanguage} />

      <ErrorBox error={error} />

      <div className="flex items-center gap-3">
        <Button
          type="submit"
          disabled={submitting || (!audioUrl && !videoUrl && script.length < 10)}
        >
          {submitting ? "Creating…" : "Create project"}
        </Button>
      </div>
    </form>
  );
}
// ─── Fake Text ──────────────────────────────────────────────────────────

type FakeTextMessageRow = {
  sender: "me" | "them";
  text: string;
  typing_ms: number;
  hold_ms: number;
};

function FakeTextForm({ router, getToken }: { router: RouterT; getToken: GetTokenT }) {
  const [name, setName] = useState("");
  const [style, setStyle] = useState<"ios" | "whatsapp" | "instagram" | "tinder">("ios");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [chatTitle, setChatTitle] = useState("Mom");
  const [aspect, setAspect] = useState<"9:16" | "16:9" | "1:1">("9:16");
  const [narrate, setNarrate] = useState(false);
  const [voiceName, setVoiceName] = useState("en-US-JennyNeural");
  const [captionStyle, setCaptionStyle] = useState("bold_word");
  const [bgColor, setBgColor] = useState("#111827");
  const [bgUrl, setBgUrl] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [showTimestamps, setShowTimestamps] = useState(false);
  const [pacing, setPacing] = useState<string | undefined>(undefined);
  const [captionLanguage, setCaptionLanguage] = useState<string | undefined>(undefined);
  const [messages, setMessages] = useState<FakeTextMessageRow[]>([
    { sender: "them", text: "Are you home?", typing_ms: 800, hold_ms: 1500 },
    { sender: "me", text: "Yeah, why?", typing_ms: 800, hold_ms: 1500 },
    { sender: "them", text: "We need to talk.", typing_ms: 1200, hold_ms: 2000 },
  ]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateMsg = (i: number, patch: Partial<FakeTextMessageRow>) =>
    setMessages((prev) => prev.map((m, idx) => (idx === i ? { ...m, ...patch } : m)));
  const addMsg = () =>
    setMessages((p) => [...p, { sender: "them", text: "", typing_ms: 800, hold_ms: 1500 }]);
  const removeMsg = (i: number) =>
    setMessages((p) => (p.length > 1 ? p.filter((_, idx) => idx !== i) : p));

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const cleaned = messages.filter((m) => m.text.trim().length > 0);
        if (cleaned.length === 0) {
          setError("Add at least one message with text.");
          return;
        }
        submitProject(
          router,
          getToken,
          {
            template: "fake_text",
            name: name || `${chatTitle} chat`,
            template_input: {
              style,
              theme,
              chat_title: chatTitle,
              aspect,
              narrate,
              caption_style: captionStyle,
              background_color: bgColor,
              show_timestamps: showTimestamps,
              ...(bgUrl ? { background_url: bgUrl } : {}),
              ...(avatarUrl ? { avatar_url: avatarUrl } : {}),
              ...(voiceName ? { voice_name: voiceName } : {}),
              ...(pacing ? { pacing } : {}),
              ...(captionLanguage ? { caption_language: captionLanguage } : {}),
              messages: cleaned,
            },
          },
          setError,
          setSubmitting,
        );
      }}
      className="grid max-w-2xl gap-5"
    >
      <div className="grid gap-2">
        <Label>Project name (optional)</Label>
        <Input
          placeholder="auto: chat title"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="grid gap-2">
          <Label>Style</Label>
          <select
            value={style}
            onChange={(e) => setStyle(e.target.value as typeof style)}
            className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100"
          >
            <option value="ios">iOS</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="instagram">Instagram</option>
            <option value="tinder">Tinder</option>
          </select>
        </div>
        <div className="grid gap-2">
          <Label>Theme</Label>
          <select
            value={theme}
            onChange={(e) => setTheme(e.target.value as typeof theme)}
            className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100"
          >
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
        </div>
        <div className="grid gap-2">
          <Label>Chat title</Label>
          <Input value={chatTitle} onChange={(e) => setChatTitle(e.target.value)} />
        </div>
        <div className="grid gap-2">
          <Label>Aspect</Label>
          <AspectSelect value={aspect} onChange={setAspect} />
        </div>
      </div>

      <div className="grid gap-3">
        <Label>Messages</Label>
        {messages.map((m, i) => (
          <div
            key={i}
            className="grid grid-cols-12 items-center gap-2 rounded-md border border-zinc-800 bg-zinc-950/50 p-2"
          >
            <select
              value={m.sender}
              onChange={(e) =>
                updateMsg(i, { sender: e.target.value as "me" | "them" })
              }
              className="col-span-2 h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm"
            >
              <option value="them">them</option>
              <option value="me">me</option>
            </select>
            <Input
              className="col-span-6"
              placeholder="message text"
              value={m.text}
              onChange={(e) => updateMsg(i, { text: e.target.value })}
            />
            <Input
              className="col-span-1"
              type="number"
              min={0}
              max={10000}
              value={m.typing_ms}
              onChange={(e) => updateMsg(i, { typing_ms: Number(e.target.value) })}
              title="typing ms"
            />
            <Input
              className="col-span-2"
              type="number"
              min={100}
              max={15000}
              value={m.hold_ms}
              onChange={(e) => updateMsg(i, { hold_ms: Number(e.target.value) })}
              title="hold ms"
            />
            <button
              type="button"
              className="col-span-1 text-xs text-red-300 hover:text-red-200"
              onClick={() => removeMsg(i)}
            >
              ✕
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={addMsg}
          className="self-start rounded-md border border-zinc-800 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-900"
        >
          + add message
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <label className="mt-6 inline-flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={narrate}
            onChange={(e) => setNarrate(e.target.checked)}
          />
          Narrate (TTS reads conversation aloud)
        </label>
        <div className="grid gap-2">
          <Label>Voice</Label>
          <VoiceSelect value={voiceName} onChange={setVoiceName} />
        </div>
        <div className="grid gap-2">
          <Label>Caption style</Label>
          <CaptionStyleSelect value={captionStyle} onChange={setCaptionStyle} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label>Background color</Label>
          <Input
            pattern="^#[0-9a-fA-F]{6}$"
            value={bgColor}
            onChange={(e) => setBgColor(e.target.value)}
          />
        </div>
        <label className="mt-6 inline-flex items-center gap-2 text-sm text-zinc-300">
          <input
            type="checkbox"
            checked={showTimestamps}
            onChange={(e) => setShowTimestamps(e.target.checked)}
          />
          Show timestamp
        </label>
      </div>

      <div className="grid gap-2">
        <Label>Background video/image URL</Label>
        <div className="flex gap-2">
          <Input
            placeholder="Optional saved library URL"
            value={bgUrl}
            onChange={(e) => setBgUrl(e.target.value)}
            className="flex-1"
          />
          <MediaPickerButton
            kind="video"
            label="Select from Library"
            onPick={(url) => setBgUrl(url)}
          />
          <MediaPickerButton
            kind="image"
            label="Image"
            onPick={(url) => setBgUrl(url)}
          />
        </div>
      </div>

      <div className="grid gap-2">
        <Label>Avatar URL</Label>
        <div className="flex gap-2">
          <Input
            placeholder="Optional saved image URL"
            value={avatarUrl}
            onChange={(e) => setAvatarUrl(e.target.value)}
            className="flex-1"
          />
          <MediaPickerButton
            kind="image"
            label="Select from Library"
            onPick={(url) => setAvatarUrl(url)}
          />
        </div>
      </div>

      <PacingPicker value={pacing} onChange={setPacing} />
      <CaptionLanguagePicker value={captionLanguage} onChange={setCaptionLanguage} />

      <ErrorBox error={error} />

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={submitting}>
          {submitting ? "Creating…" : "Create project"}
        </Button>
      </div>
    </form>
  );
}

// ─── Would You Rather ───────────────────────────────────────────────────

function WouldYouRatherForm({ router, getToken }: { router: RouterT; getToken: GetTokenT }) {
  const [name, setName] = useState("");
  const [question, setQuestion] = useState("Would you rather…");
  const [optionA, setOptionA] = useState("");
  const [optionB, setOptionB] = useState("");
  const [colorA, setColorA] = useState("#1f6feb");
  const [colorB, setColorB] = useState("#dc2626");
  const [bgUrl, setBgUrl] = useState("");
  const [timer, setTimer] = useState(5);
  const [pctA, setPctA] = useState(50);
  const [seed, setSeed] = useState("");
  const [aspect, setAspect] = useState<"9:16" | "16:9" | "1:1">("9:16");
  const [voiceName, setVoiceName] = useState("en-US-GuyNeural");
  const [captionStyle, setCaptionStyle] = useState("impact_uppercase");
  const [pacing, setPacing] = useState<string | undefined>(undefined);
  const [captionLanguage, setCaptionLanguage] = useState<string | undefined>(undefined);
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
            template: "would_you_rather",
            name: name || question.slice(0, 60),
            template_input: {
              question,
              option_a: optionA,
              option_b: optionB,
              color_a: colorA,
              color_b: colorB,
              ...(bgUrl ? { background_url: bgUrl } : {}),
              timer_seconds: timer,
              reveal_percent_a: pctA,
              ...(seed ? { seed: Number(seed) } : {}),
              aspect,
              caption_style: captionStyle,
              ...(voiceName ? { voice_name: voiceName } : {}),
              ...(pacing ? { pacing } : {}),
              ...(captionLanguage ? { caption_language: captionLanguage } : {}),
            },
          },
          setError,
          setSubmitting,
        );
      }}
      className="grid max-w-2xl gap-5"
    >
      <div className="grid gap-2">
        <Label>Project name (optional)</Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="grid gap-2">
        <Label>Question *</Label>
        <Textarea
          required
          minLength={10}
          maxLength={300}
          rows={2}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label>Option A *</Label>
          <Input required value={optionA} onChange={(e) => setOptionA(e.target.value)} />
          <Input
            type="text"
            pattern="^#[0-9a-fA-F]{6}$"
            value={colorA}
            onChange={(e) => setColorA(e.target.value)}
            className="text-xs"
          />
        </div>
        <div className="grid gap-2">
          <Label>Option B *</Label>
          <Input required value={optionB} onChange={(e) => setOptionB(e.target.value)} />
          <Input
            type="text"
            pattern="^#[0-9a-fA-F]{6}$"
            value={colorB}
            onChange={(e) => setColorB(e.target.value)}
            className="text-xs"
          />
        </div>
      </div>
      <div className="grid gap-2">
        <Label>Background video/image URL</Label>
        <div className="flex gap-2">
          <Input
            placeholder="Optional saved library URL"
            value={bgUrl}
            onChange={(e) => setBgUrl(e.target.value)}
            className="flex-1"
          />
          <MediaPickerButton
            kind="video"
            label="Select from Library"
            onPick={(url) => setBgUrl(url)}
          />
          <MediaPickerButton
            kind="image"
            label="Image"
            onPick={(url) => setBgUrl(url)}
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
        <div className="grid gap-2">
          <Label>Timer (s)</Label>
          <Input
            type="number"
            min={3}
            max={15}
            value={timer}
            onChange={(e) => setTimer(Number(e.target.value))}
          />
        </div>
        <div className="grid gap-2">
          <Label>% chose A</Label>
          <Input
            type="number"
            min={0}
            max={100}
            value={pctA}
            onChange={(e) => setPctA(Number(e.target.value))}
          />
        </div>
        <div className="grid gap-2">
          <Label>Aspect</Label>
          <AspectSelect value={aspect} onChange={setAspect} />
        </div>
        <div className="grid gap-2">
          <Label>Seed</Label>
          <Input value={seed} onChange={(e) => setSeed(e.target.value)} />
        </div>
        <div className="grid gap-2">
          <Label>Caption style</Label>
          <CaptionStyleSelect value={captionStyle} onChange={setCaptionStyle} />
        </div>
      </div>
      <div className="grid gap-2">
        <Label>Voice</Label>
        <VoiceSelect value={voiceName} onChange={setVoiceName} />
      </div>

      <PacingPicker value={pacing} onChange={setPacing} />
      <CaptionLanguagePicker value={captionLanguage} onChange={setCaptionLanguage} />

      <ErrorBox error={error} />
      <div>
        <Button type="submit" disabled={submitting || optionA.length < 1 || optionB.length < 1 || question.length < 10}>
          {submitting ? "Creating…" : "Create project"}
        </Button>
      </div>
    </form>
  );
}

// ─── Split Video ────────────────────────────────────────────────────────

function SplitVideoForm({ router, getToken }: { router: RouterT; getToken: GetTokenT }) {
  const [name, setName] = useState("");
  const [layout, setLayout] = useState<"vertical" | "horizontal">("vertical");
  const [mainPosition, setMainPosition] = useState<"first" | "second">("first");
  const [cropMode, setCropMode] = useState<"cover" | "contain">("cover");
  const [mainUrl, setMainUrl] = useState("");
  const [fillerUrl, setFillerUrl] = useState("");
  const [script, setScript] = useState("");
  const [duration, setDuration] = useState(30);
  const [aspect, setAspect] = useState<"9:16" | "16:9" | "1:1">("9:16");
  const [bgColor, setBgColor] = useState("#0b0b0f");
  const [voiceName, setVoiceName] = useState("en-US-AriaNeural");
  const [captionStyle, setCaptionStyle] = useState("bold_word");
  const [pacing, setPacing] = useState<string | undefined>(undefined);
  const [captionLanguage, setCaptionLanguage] = useState<string | undefined>(undefined);
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
            template: "split_video",
            name: name || script.slice(0, 60),
            template_input: {
              layout,
              main_position: mainPosition,
              crop_mode: cropMode,
              script,
              duration,
              aspect,
              background_color: bgColor,
              caption_style: captionStyle,
              ...(mainUrl ? { main_url: mainUrl } : {}),
              ...(fillerUrl ? { filler_url: fillerUrl } : {}),
              ...(voiceName ? { voice_name: voiceName } : {}),
              ...(pacing ? { pacing } : {}),
              ...(captionLanguage ? { caption_language: captionLanguage } : {}),
            },
          },
          setError,
          setSubmitting,
        );
      }}
      className="grid max-w-2xl gap-5"
    >
      <div className="grid gap-2">
        <Label>Project name (optional)</Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
        <div className="grid gap-2">
          <Label>Layout</Label>
          <select
            value={layout}
            onChange={(e) => setLayout(e.target.value as typeof layout)}
            className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm"
          >
            <option value="vertical">Top / Bottom</option>
            <option value="horizontal">Left / Right</option>
          </select>
        </div>
        <div className="grid gap-2">
          <Label>Main position</Label>
          <select
            value={mainPosition}
            onChange={(e) => setMainPosition(e.target.value as typeof mainPosition)}
            className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm"
          >
            <option value="first">Top / Left</option>
            <option value="second">Bottom / Right</option>
          </select>
        </div>
        <div className="grid gap-2">
          <Label>Fit</Label>
          <select
            value={cropMode}
            onChange={(e) => setCropMode(e.target.value as typeof cropMode)}
            className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm"
          >
            <option value="cover">Cover crop</option>
            <option value="contain">Contain</option>
          </select>
        </div>
        <div className="grid gap-2">
          <Label>Aspect</Label>
          <AspectSelect value={aspect} onChange={setAspect} />
        </div>
        <div className="grid gap-2">
          <Label>Duration (s)</Label>
          <Input
            type="number"
            min={8}
            max={120}
            value={duration}
            onChange={(e) => setDuration(Number(e.target.value))}
          />
        </div>
      </div>
      <div className="grid gap-2">
        <Label>Main clip URL</Label>
        <div className="flex gap-2">
          <Input
            placeholder="https://… or paste from your library"
            value={mainUrl}
            onChange={(e) => setMainUrl(e.target.value)}
            className="flex-1"
          />
          <MediaPickerButton
            kind="video"
            label="Select from Library"
            onPick={(url) => setMainUrl(url)}
          />
        </div>
      </div>
      <div className="grid gap-2">
        <Label>Filler clip URL (optional, gameplay/satisfying)</Label>
        <div className="flex gap-2">
          <Input
            value={fillerUrl}
            onChange={(e) => setFillerUrl(e.target.value)}
            className="flex-1"
          />
          <MediaPickerButton
            kind="video"
            label="Select from Library"
            onPick={(url) => setFillerUrl(url)}
          />
        </div>
      </div>
      <div className="grid gap-2">
        <Label>Script *</Label>
        <Textarea
          required
          minLength={10}
          maxLength={8000}
          rows={5}
          value={script}
          onChange={(e) => setScript(e.target.value)}
        />
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <div className="grid gap-2">
          <Label>Bg color (fallback)</Label>
          <Input
            type="text"
            pattern="^#[0-9a-fA-F]{6}$"
            value={bgColor}
            onChange={(e) => setBgColor(e.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <Label>Voice</Label>
          <VoiceSelect value={voiceName} onChange={setVoiceName} />
        </div>
        <div className="grid gap-2">
          <Label>Caption style</Label>
          <CaptionStyleSelect value={captionStyle} onChange={setCaptionStyle} />
        </div>
      </div>

      <PacingPicker value={pacing} onChange={setPacing} />
      <CaptionLanguagePicker value={captionLanguage} onChange={setCaptionLanguage} />

      <ErrorBox error={error} />
      <div>
        <Button type="submit" disabled={submitting || script.length < 10}>
          {submitting ? "Creating…" : "Create project"}
        </Button>
      </div>
    </form>
  );
}

// ─── Twitter / X ────────────────────────────────────────────────────────

function TwitterForm({ router, getToken }: { router: RouterT; getToken: GetTokenT }) {
  const [name, setName] = useState("");
  const [handle, setHandle] = useState("elonmusk");
  const [displayName, setDisplayName] = useState("Elon Musk");
  const [text, setText] = useState("");
  const [thread, setThread] = useState<string[]>([]);
  const [likes, setLikes] = useState(1200);
  const [retweets, setRetweets] = useState(80);
  const [replies, setReplies] = useState(150);
  const [views, setViews] = useState(45000);
  const [verified, setVerified] = useState(true);
  const [darkMode, setDarkMode] = useState(true);
  const [aspect, setAspect] = useState<"9:16" | "16:9" | "1:1">("9:16");
  const [voiceName, setVoiceName] = useState("en-US-AriaNeural");
  const [captionStyle, setCaptionStyle] = useState("bold_word");
  const [bgColor, setBgColor] = useState("#0b0b0f");
  const [bgUrl, setBgUrl] = useState("");
  const [pacing, setPacing] = useState<string | undefined>(undefined);
  const [captionLanguage, setCaptionLanguage] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateThread = (i: number, v: string) =>
    setThread((p) => p.map((t, idx) => (idx === i ? v : t)));

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submitProject(
          router,
          getToken,
          {
            template: "twitter",
            name: name || text.slice(0, 60),
            template_input: {
              handle,
              display_name: displayName,
              text,
              thread: thread.filter((t) => t.trim().length > 0),
              likes,
              retweets,
              replies,
              views,
              verified,
              dark_mode: darkMode,
              aspect,
              background_color: bgColor,
              ...(bgUrl ? { background_url: bgUrl } : {}),
              caption_style: captionStyle,
              ...(voiceName ? { voice_name: voiceName } : {}),
              ...(pacing ? { pacing } : {}),
              ...(captionLanguage ? { caption_language: captionLanguage } : {}),
            },
          },
          setError,
          setSubmitting,
        );
      }}
      className="grid max-w-2xl gap-5"
    >
      <div className="grid gap-2">
        <Label>Project name (optional)</Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label>Display name *</Label>
          <Input required value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </div>
        <div className="grid gap-2">
          <Label>Handle (without @) *</Label>
          <Input required value={handle} onChange={(e) => setHandle(e.target.value)} />
        </div>
      </div>
      <div className="grid gap-2">
        <Label>Tweet text *</Label>
        <Textarea
          required
          minLength={1}
          maxLength={1000}
          rows={4}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </div>
      <div className="grid gap-2">
        <Label>Thread (optional follow-up tweets)</Label>
        {thread.map((t, i) => (
          <div key={i} className="flex items-center gap-2">
            <Input
              value={t}
              onChange={(e) => updateThread(i, e.target.value)}
              placeholder={`Tweet ${i + 2}`}
            />
            <button
              type="button"
              className="text-xs text-red-300"
              onClick={() => setThread((p) => p.filter((_, idx) => idx !== i))}
            >
              ✕
            </button>
          </div>
        ))}
        {thread.length < 10 ? (
          <button
            type="button"
            className="self-start rounded-md border border-zinc-800 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-900"
            onClick={() => setThread((p) => [...p, ""])}
          >
            + add reply
          </button>
        ) : null}
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="grid gap-2">
          <Label>Likes</Label>
          <Input type="number" min={0} value={likes} onChange={(e) => setLikes(Number(e.target.value))} />
        </div>
        <div className="grid gap-2">
          <Label>Retweets</Label>
          <Input type="number" min={0} value={retweets} onChange={(e) => setRetweets(Number(e.target.value))} />
        </div>
        <div className="grid gap-2">
          <Label>Replies</Label>
          <Input type="number" min={0} value={replies} onChange={(e) => setReplies(Number(e.target.value))} />
        </div>
        <div className="grid gap-2">
          <Label>Views</Label>
          <Input type="number" min={0} value={views} onChange={(e) => setViews(Number(e.target.value))} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <label className="mt-6 inline-flex items-center gap-2 text-sm">
          <input type="checkbox" checked={verified} onChange={(e) => setVerified(e.target.checked)} />
          Verified
        </label>
        <label className="mt-6 inline-flex items-center gap-2 text-sm">
          <input type="checkbox" checked={darkMode} onChange={(e) => setDarkMode(e.target.checked)} />
          Dark mode
        </label>
        <div className="grid gap-2">
          <Label>Aspect</Label>
          <AspectSelect value={aspect} onChange={setAspect} />
        </div>
        <div className="grid gap-2">
          <Label>Caption style</Label>
          <CaptionStyleSelect value={captionStyle} onChange={setCaptionStyle} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label>Page bg color</Label>
          <Input pattern="^#[0-9a-fA-F]{6}$" value={bgColor} onChange={(e) => setBgColor(e.target.value)} />
        </div>
        <div className="grid gap-2">
          <Label>Voice</Label>
          <VoiceSelect value={voiceName} onChange={setVoiceName} />
        </div>
      </div>
      <div className="grid gap-2">
        <Label>Background video/image URL</Label>
        <div className="flex gap-2">
          <Input
            placeholder="Optional saved library URL"
            value={bgUrl}
            onChange={(e) => setBgUrl(e.target.value)}
            className="flex-1"
          />
          <MediaPickerButton
            kind="video"
            label="Select from Library"
            onPick={(url) => setBgUrl(url)}
          />
          <MediaPickerButton
            kind="image"
            label="Image"
            onPick={(url) => setBgUrl(url)}
          />
        </div>
      </div>

      <PacingPicker value={pacing} onChange={setPacing} />
      <CaptionLanguagePicker value={captionLanguage} onChange={setCaptionLanguage} />

      <ErrorBox error={error} />
      <div>
        <Button type="submit" disabled={submitting || text.length < 1}>
          {submitting ? "Creating…" : "Create project"}
        </Button>
      </div>
    </form>
  );
}

// ─── Top 5 / Countdown ──────────────────────────────────────────────────

type TopFiveItemRow = { title: string; description: string };

function TopFiveForm({ router, getToken }: { router: RouterT; getToken: GetTokenT }) {
  const [name, setName] = useState("");
  const [title, setTitle] = useState("Top 5 Cities to Visit Before You Die");
  const [items, setItems] = useState<TopFiveItemRow[]>([
    { title: "Tokyo", description: "Neon, sushi, vending machines on every corner." },
    { title: "Reykjavik", description: "Volcanoes and aurora borealis." },
    { title: "Cape Town", description: "Where the mountains meet the sea." },
    { title: "Cusco", description: "Gateway to Machu Picchu." },
    { title: "Marrakech", description: "Souks, spices, and rooftop sunsets." },
  ]);
  const [perItem, setPerItem] = useState(4);
  const [aspect, setAspect] = useState<"9:16" | "16:9" | "1:1">("9:16");
  const [bgColor, setBgColor] = useState("#0b0b0f");
  const [bgUrl, setBgUrl] = useState("");
  const [voiceName, setVoiceName] = useState("en-US-GuyNeural");
  const [captionStyle, setCaptionStyle] = useState("impact_uppercase");
  const [pacing, setPacing] = useState<string | undefined>("medium");
  const [captionLanguage, setCaptionLanguage] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateItem = (i: number, patch: Partial<TopFiveItemRow>) =>
    setItems((prev) => prev.map((m, idx) => (idx === i ? { ...m, ...patch } : m)));
  const addItem = () =>
    setItems((p) => (p.length < 10 ? [...p, { title: "", description: "" }] : p));
  const removeItem = (i: number) =>
    setItems((p) => (p.length > 3 ? p.filter((_, idx) => idx !== i) : p));

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const cleaned = items
          .map((it) => ({ title: it.title.trim(), description: it.description.trim() }))
          .filter((it) => it.title.length > 0);
        if (cleaned.length < 3) {
          setError("Need at least 3 items with titles.");
          return;
        }
        submitProject(
          router,
          getToken,
          {
            template: "top_five",
            name: name || title.slice(0, 60),
            template_input: {
              title,
              items: cleaned.map((it) =>
                it.description ? it : { title: it.title }
              ),
              per_item_seconds: perItem,
              aspect,
              background_color: bgColor,
              ...(bgUrl ? { background_url: bgUrl } : {}),
              caption_style: captionStyle,
              ...(voiceName ? { voice_name: voiceName } : {}),
              ...(pacing ? { pacing } : {}),
              ...(captionLanguage ? { caption_language: captionLanguage } : {}),
            },
          },
          setError,
          setSubmitting,
        );
      }}
      className="grid max-w-2xl gap-5"
    >
      <div className="grid gap-2">
        <Label>Project name (optional)</Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="grid gap-2">
        <Label>List title *</Label>
        <Input required value={title} onChange={(e) => setTitle(e.target.value)} />
      </div>
      <div className="grid gap-3">
        <Label>Items (3-10, count down N→1)</Label>
        {items.map((it, i) => (
          <div key={i} className="grid grid-cols-12 items-start gap-2 rounded-md border border-zinc-800 bg-zinc-950/50 p-2">
            <Input
              className="col-span-4"
              placeholder={`Item ${i + 1} title`}
              value={it.title}
              onChange={(e) => updateItem(i, { title: e.target.value })}
            />
            <Input
              className="col-span-7"
              placeholder="description (optional)"
              value={it.description}
              onChange={(e) => updateItem(i, { description: e.target.value })}
            />
            <button
              type="button"
              className="col-span-1 text-xs text-red-300"
              onClick={() => removeItem(i)}
            >
              ✕
            </button>
          </div>
        ))}
        {items.length < 10 ? (
          <button
            type="button"
            onClick={addItem}
            className="self-start rounded-md border border-zinc-800 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-900"
          >
            + add item
          </button>
        ) : null}
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="grid gap-2">
          <Label>Sec / item</Label>
          <Input
            type="number"
            min={2}
            max={15}
            value={perItem}
            onChange={(e) => setPerItem(Number(e.target.value))}
          />
        </div>
        <div className="grid gap-2">
          <Label>Aspect</Label>
          <AspectSelect value={aspect} onChange={setAspect} />
        </div>
        <div className="grid gap-2">
          <Label>Bg color</Label>
          <Input pattern="^#[0-9a-fA-F]{6}$" value={bgColor} onChange={(e) => setBgColor(e.target.value)} />
        </div>
        <div className="grid gap-2">
          <Label>Caption style</Label>
          <CaptionStyleSelect value={captionStyle} onChange={setCaptionStyle} />
        </div>
      </div>
      <div className="grid gap-2">
        <Label>Voice</Label>
        <VoiceSelect value={voiceName} onChange={setVoiceName} />
      </div>
      <div className="grid gap-2">
        <Label>Background video/image URL</Label>
        <div className="flex gap-2">
          <Input
            placeholder="Optional saved library URL"
            value={bgUrl}
            onChange={(e) => setBgUrl(e.target.value)}
            className="flex-1"
          />
          <MediaPickerButton
            kind="video"
            label="Select from Library"
            onPick={(url) => setBgUrl(url)}
          />
          <MediaPickerButton
            kind="image"
            label="Image"
            onPick={(url) => setBgUrl(url)}
          />
        </div>
      </div>

      <PacingPicker value={pacing} onChange={setPacing} />
      <CaptionLanguagePicker value={captionLanguage} onChange={setCaptionLanguage} />

      <ErrorBox error={error} />
      <div>
        <Button type="submit" disabled={submitting || title.length < 1}>
          {submitting ? "Creating…" : "Create project"}
        </Button>
      </div>
    </form>
  );
}

// ─── Roblox Rant ────────────────────────────────────────────────────────

function RobloxRantForm({ router, getToken }: { router: RouterT; getToken: GetTokenT }) {
  const [name, setName] = useState("");
  const [script, setScript] = useState("");
  const [bgUrl, setBgUrl] = useState("");
  const [bgColor, setBgColor] = useState("#0b0b0f");
  const [rate, setRate] = useState("+15%");
  const [aspect, setAspect] = useState<"9:16" | "16:9" | "1:1">("9:16");
  const [voiceName, setVoiceName] = useState("en-US-GuyNeural");
  const [captionStyle, setCaptionStyle] = useState("impact_uppercase");
  const [pacing, setPacing] = useState<string | undefined>(undefined);
  const [captionLanguage, setCaptionLanguage] = useState<string | undefined>(undefined);
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
            template: "roblox_rant",
            name: name || script.slice(0, 60),
            template_input: {
              script,
              speech_rate: rate,
              background_color: bgColor,
              aspect,
              caption_style: captionStyle,
              ...(bgUrl ? { background_url: bgUrl } : {}),
              ...(voiceName ? { voice_name: voiceName } : {}),
              ...(pacing ? { pacing } : {}),
              ...(captionLanguage ? { caption_language: captionLanguage } : {}),
            },
          },
          setError,
          setSubmitting,
        );
      }}
      className="grid max-w-2xl gap-5"
    >
      <div className="grid gap-2">
        <Label>Project name (optional)</Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="grid gap-2">
        <Label>Script *</Label>
        <Textarea
          required
          minLength={10}
          maxLength={8000}
          rows={6}
          value={script}
          onChange={(e) => setScript(e.target.value)}
        />
      </div>
      <div className="grid gap-2">
        <Label>Background URL (Roblox / gameplay clip, optional)</Label>
        <div className="flex gap-2">
          <Input
            placeholder="https://… or paste from your library"
            value={bgUrl}
            onChange={(e) => setBgUrl(e.target.value)}
            className="flex-1"
          />
          <MediaPickerButton
            kind="video"
            label="Select from Library"
            onPick={(url) => setBgUrl(url)}
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div className="grid gap-2">
          <Label>Speech rate</Label>
          <Input
            pattern="^[+\-]\d{1,3}%$"
            value={rate}
            onChange={(e) => setRate(e.target.value)}
            title="e.g. +15% (faster) or -5% (slower)"
          />
        </div>
        <div className="grid gap-2">
          <Label>Bg color</Label>
          <Input pattern="^#[0-9a-fA-F]{6}$" value={bgColor} onChange={(e) => setBgColor(e.target.value)} />
        </div>
        <div className="grid gap-2">
          <Label>Aspect</Label>
          <AspectSelect value={aspect} onChange={setAspect} />
        </div>
        <div className="grid gap-2">
          <Label>Caption style</Label>
          <CaptionStyleSelect value={captionStyle} onChange={setCaptionStyle} />
        </div>
      </div>
      <div className="grid gap-2">
        <Label>Voice</Label>
        <VoiceSelect value={voiceName} onChange={setVoiceName} />
      </div>

      <PacingPicker value={pacing} onChange={setPacing} />
      <CaptionLanguagePicker value={captionLanguage} onChange={setCaptionLanguage} />

      <ErrorBox error={error} />
      <div>
        <Button type="submit" disabled={submitting || script.length < 10}>
          {submitting ? "Creating…" : "Create project"}
        </Button>
      </div>
    </form>
  );
}
