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

  return (
    <AppShell>
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Templates</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Pick a template to start a new project. Phase 1 ships four —
            more land in PR&nbsp;14+.
          </p>
        </div>
      </div>

      {error ? (
        <Card className="border-red-900 bg-red-950/30">
          <CardContent className="pt-5 text-sm text-red-200">
            Could not reach the api at{" "}
            <code className="font-mono">{process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}</code>
            . Make sure <code className="font-mono">pnpm dev:api</code> is running.
            <div className="mt-2 text-xs text-red-300/80">{error}</div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-5 sm:grid-cols-2">
          {templates.map((t) => (
            <Card key={t.template_id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>{t.name}</CardTitle>
                  {t.has_plan_preview ? (
                    <Badge tone="ok">plan preview</Badge>
                  ) : (
                    <Badge tone="muted">direct render</Badge>
                  )}
                </div>
                <CardDescription>{t.description}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-1">
                  {t.tags.map((tag) => (
                    <Badge key={tag} tone="muted">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </CardContent>
              <CardFooter>
                <Link
                  href={`/create/${t.template_id}`}
                  className="ml-auto"
                >
                  <Button>Use this template →</Button>
                </Link>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}
    </AppShell>
  );
}
