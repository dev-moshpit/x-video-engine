import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/app-shell";
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
import { listTemplates, type TemplateMeta } from "@/lib/api";

type GroupMeta = {
  title: string;
  blurb: string;
  ids: string[];
};

const GROUPS: GroupMeta[] = [
  {
    title: "Story",
    blurb: "Long-form prompts → cinematic 9:16 narrations with synthesised visuals.",
    ids: ["ai_story", "reddit_story"],
  },
  {
    title: "Social Screenshots",
    blurb: "Render realistic social-media UI as 9:16 video with voiceover.",
    ids: ["fake_text", "twitter"],
  },
  {
    title: "Games / Brainrot",
    blurb: "Fast-paced gameplay-style overlays + reaction loops.",
    ids: ["roblox_rant", "split_video", "would_you_rather"],
  },
  {
    title: "Countdown / List",
    blurb: "Numbered listicle videos with bold panel typography.",
    ids: ["top_five"],
  },
  {
    title: "Utility",
    blurb: "Bring-your-own script → voiceover + burned captions.",
    ids: ["voiceover", "auto_captions"],
  },
];

// Per-template editorial polish: a one-liner "best for" so the gallery
// reads like a product page instead of a schema dump, plus 1-2 sample
// prompt seeds an operator can click into the create form for a head
// start. Defined here (not in the template registry) so editorial
// changes don't churn the api schema.
const TEMPLATE_POLISH: Record<string, { bestFor: string; samples: string[] }> = {
  ai_story: {
    bestFor: "TikTok / Reels motivational shorts",
    samples: [
      "Make a motivational video about discipline beating motivation.",
      "AI is replacing boring office work — show why, cinematic.",
    ],
  },
  reddit_story: {
    bestFor: "AmITheAsshole / scary / nostalgia narrations",
    samples: [
      "AITA for not letting my coworker microwave fish in the office",
      "TIFU by sending the wrong text to my landlord",
    ],
  },
  fake_text: {
    bestFor: "Drama posts, group-chat comedy",
    samples: [
      "Mum chat about my cat sending the wrong calendar invite",
      "Tinder convo gone hilariously wrong",
    ],
  },
  twitter: {
    bestFor: "Hot-take tweets and quote-tweet reactions",
    samples: [
      "found a bug. fixed it. now tweeting about it.",
      "crypto isn't dead — it's just resting (a thread)",
    ],
  },
  roblox_rant: {
    bestFor: "Fast rant + gameplay-style overlay",
    samples: [
      "why every game keeps adding battle passes nobody wanted",
      "the worst design decision in modern web apps",
    ],
  },
  split_video: {
    bestFor: "Reaction / commentary stacked over filler clips",
    samples: [
      "explain a concept on top, gameplay underneath",
      "before-and-after split with narration",
    ],
  },
  would_you_rather: {
    bestFor: "Engagement bait, two-option polls",
    samples: [
      "Always know when someone is lying — or always get away with it?",
      "Be invisible — or fly forever?",
    ],
  },
  top_five: {
    bestFor: "Listicles, countdowns, reveal moments",
    samples: [
      "Top 5 cities to visit before you die",
      "5 productivity hacks that actually work",
    ],
  },
  voiceover: {
    bestFor: "Bring-your-own script, premium narration",
    samples: [
      "30-second product launch script",
      "founder's story over a calm background",
    ],
  },
  auto_captions: {
    bestFor: "Ship a video you already have with bold burned captions",
    samples: [
      "Drop in an audio file and we'll caption + visualise it",
      "Use your own voice; we burn the captions on top",
    ],
  },
};

export default async function TemplatesPage() {
  const { userId } = await auth();
  if (!userId) redirect("/sign-in?redirect_url=/templates");

  let templates: TemplateMeta[] = [];
  let error: string | null = null;
  try {
    templates = await listTemplates();
  } catch (e) {
    error = e instanceof Error ? e.message : "failed to load templates";
  }

  const byId = new Map(templates.map((template) => [template.template_id, template]));

  return (
    <AppShell>
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Templates</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Faceless-video formats grouped by how creators actually use them.
          </p>
        </div>
      </div>

      {error ? (
        <Card className="border-red-900 bg-red-950/30">
          <CardContent className="pt-5 text-sm text-red-200">
            Could not reach the api at{" "}
            <code className="font-mono">
              {process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}
            </code>
            .
            <div className="mt-2 text-xs text-red-300/80">{error}</div>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-8">
          {GROUPS.map((group) => {
            const groupTemplates = group.ids
              .map((id) => byId.get(id))
              .filter((item): item is TemplateMeta => Boolean(item));
            if (groupTemplates.length === 0) return null;
            return (
              <section key={group.title}>
                <div className="mb-3">
                  <h2 className="text-sm font-semibold uppercase tracking-wider text-zinc-300">
                    {group.title}
                  </h2>
                  <p className="mt-1 text-xs text-zinc-500">{group.blurb}</p>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  {groupTemplates.map((template) => (
                    <TemplateCard
                      key={template.template_id}
                      template={template}
                    />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}

function TemplateCard({ template }: { template: TemplateMeta }) {
  const polish = TEMPLATE_POLISH[template.template_id];
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle>{template.name}</CardTitle>
          {template.has_plan_preview ? (
            <Badge tone="ok">plan preview</Badge>
          ) : (
            <Badge tone="muted">direct render</Badge>
          )}
        </div>
        <CardDescription>{template.description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {polish?.bestFor ? (
          <div className="text-[11px] uppercase tracking-wider text-blue-300/80">
            Best for · <span className="text-blue-200">{polish.bestFor}</span>
          </div>
        ) : null}
        <div className="flex flex-wrap gap-1">
          {template.tags.map((tag) => (
            <Badge key={tag} tone="muted">
              {tag}
            </Badge>
          ))}
        </div>
        {polish && polish.samples.length > 0 ? (
          <ul className="space-y-1 text-xs text-zinc-400">
            {polish.samples.slice(0, 2).map((sample) => (
              <li key={sample} className="leading-snug">
                <span className="mr-1 text-zinc-600">→</span>
                <span className="italic">&ldquo;{sample}&rdquo;</span>
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
      <CardFooter>
        <Link href={`/create/${template.template_id}`} className="ml-auto">
          <Button>Use this template</Button>
        </Link>
      </CardFooter>
    </Card>
  );
}
