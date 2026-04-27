import { UserButton } from "@clerk/nextjs";
import { currentUser } from "@clerk/nextjs/server";

export default async function DashboardPage() {
  // The middleware (apps/web/middleware.ts) protects this route, so by
  // the time we render here the user is authenticated.
  const user = await currentUser();
  const display =
    user?.firstName ??
    user?.emailAddresses[0]?.emailAddress ??
    user?.id ??
    "anonymous";

  return (
    <main className="min-h-dvh px-6 py-10">
      <header className="mx-auto flex max-w-5xl items-center justify-between">
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <UserButton />
      </header>
      <section className="mx-auto mt-12 max-w-5xl">
        <p className="text-sm text-zinc-400">
          Signed in as <span className="text-zinc-100">{display}</span>
        </p>
        <p className="mt-6 text-sm text-zinc-500">
          Projects, template gallery, and the four MVP generators land in PR
          4–9.
        </p>
      </section>
    </main>
  );
}
