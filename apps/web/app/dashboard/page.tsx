import { redirect } from "next/navigation";
import { auth, currentUser } from "@clerk/nextjs/server";
import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { listProjects, type Project } from "@/lib/api";

export default async function DashboardPage() {
  // Defense-in-depth auth gate. Middleware also protects this route
  // (see apps/web/middleware.ts), but Clerk's keyless dev mode
  // short-circuits the middleware callback to surface its claim-keys
  // banner. A server-side check here makes the gate work in both
  // keyless and claimed modes.
  const { userId, getToken } = await auth();
  if (!userId) redirect("/sign-in?redirect_url=/dashboard");

  const user = await currentUser();
  const display =
    user?.firstName ??
    user?.emailAddresses[0]?.emailAddress ??
    user?.id ??
    "anonymous";

  let projects: Project[] = [];
  let loadError: string | null = null;
  try {
    const token = await getToken();
    if (token) projects = await listProjects(token);
  } catch (e) {
    loadError = e instanceof Error ? e.message : "load failed";
  }

  return (
    <AppShell>
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Signed in as <span className="text-zinc-200">{display}</span>
          </p>
        </div>
        <Link href="/templates">
          <Button>New project →</Button>
        </Link>
      </div>

      {loadError ? (
        <Card className="border-red-900 bg-red-950/30">
          <CardContent className="pt-5 text-sm text-red-200">
            Could not load projects from the api. Make sure{" "}
            <code className="font-mono">pnpm dev:api</code> is running.
            <div className="mt-1 text-xs text-red-300/80">{loadError}</div>
          </CardContent>
        </Card>
      ) : projects.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>No projects yet</CardTitle>
            <CardDescription>
              Pick a template to start your first faceless short.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link href="/templates">
              <Button>Browse templates</Button>
            </Link>
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
    </AppShell>
  );
}
