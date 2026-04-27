export default function Home() {
  return (
    <main className="min-h-dvh flex flex-col items-center justify-center px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">x-video-engine</h1>
      <p className="mt-3 max-w-md text-center text-sm text-zinc-400">
        SaaS skeleton — PR 1. Auth, dashboard, templates, and the four MVP
        generators arrive in PR 2 onward.
      </p>
      <a
        href="http://localhost:8000/docs"
        className="mt-6 text-xs text-zinc-500 underline-offset-4 hover:underline"
      >
        api docs (FastAPI) → :8000/docs
      </a>
    </main>
  );
}
