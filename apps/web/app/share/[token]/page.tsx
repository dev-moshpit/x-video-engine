import Link from "next/link";

import { API_BASE_URL } from "@/lib/api";

interface PublicShare {
  final_mp4_url: string;
  template: string;
  project_name: string | null;
  created_at: string;
}

async function fetchShare(token: string): Promise<PublicShare | null> {
  const res = await fetch(
    `${API_BASE_URL}/api/public/renders/${encodeURIComponent(token)}`,
    { cache: "no-store" },
  );
  if (!res.ok) return null;
  return (await res.json()) as PublicShare;
}

export default async function PublicSharePage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const share = await fetchShare(token);

  if (!share) {
    return (
      <main className="flex min-h-dvh flex-col items-center justify-center px-6 py-16 text-center">
        <h1 className="text-xl font-semibold tracking-tight">Link unavailable</h1>
        <p className="mt-2 max-w-md text-sm text-zinc-400">
          This share link has been disabled, expired, or never existed.
        </p>
        <Link
          href="/"
          className="mt-8 text-xs text-zinc-500 underline-offset-4 hover:underline"
        >
          ← go home
        </Link>
      </main>
    );
  }

  return (
    <main className="min-h-dvh bg-zinc-950 px-4 py-10">
      <div className="mx-auto flex max-w-2xl flex-col gap-6">
        <header className="text-center">
          <h1 className="text-xl font-semibold tracking-tight text-zinc-100">
            {share.project_name ?? "Shared video"}
          </h1>
          <p className="mt-1 text-xs text-zinc-500">
            {share.template} · created{" "}
            {new Date(share.created_at).toLocaleDateString()}
          </p>
        </header>

        <div className="overflow-hidden rounded-xl border border-zinc-800 bg-black shadow-xl">
          <video
            src={share.final_mp4_url}
            controls
            playsInline
            className="block h-auto w-full bg-black"
          />
        </div>

        <footer className="text-center">
          <Link
            href="/"
            className="text-xs text-zinc-500 underline-offset-4 hover:underline"
          >
            powered by x-video-engine →
          </Link>
        </footer>
      </div>
    </main>
  );
}
