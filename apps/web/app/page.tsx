import Link from "next/link";
import { auth } from "@clerk/nextjs/server";

export default async function Home() {
  const { userId } = await auth();

  return (
    <main className="min-h-dvh flex flex-col items-center justify-center px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">x-video-engine</h1>
      <p className="mt-3 max-w-md text-center text-sm text-zinc-400">
        Faceless short-video factory. Prompt or template in, upload-ready
        vertical MP4 out.
      </p>

      <div className="mt-8 flex gap-3">
        {userId ? (
          <Link
            href="/dashboard"
            className="rounded-md bg-zinc-100 text-zinc-900 px-4 py-2 text-sm hover:bg-white"
          >
            Open dashboard
          </Link>
        ) : (
          <>
            <Link
              href="/sign-in"
              className="rounded-md border border-zinc-700 px-4 py-2 text-sm hover:bg-zinc-900"
            >
              Sign in
            </Link>
            <Link
              href="/sign-up"
              className="rounded-md bg-zinc-100 text-zinc-900 px-4 py-2 text-sm hover:bg-white"
            >
              Sign up
            </Link>
          </>
        )}
      </div>

      <a
        href="http://localhost:8000/docs"
        className="mt-12 text-xs text-zinc-500 underline-offset-4 hover:underline"
      >
        api docs (FastAPI) → :8000/docs
      </a>
    </main>
  );
}
