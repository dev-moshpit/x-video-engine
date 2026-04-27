import { redirect } from "next/navigation";
import { UserButton } from "@clerk/nextjs";
import { auth, currentUser } from "@clerk/nextjs/server";

export default async function DashboardPage() {
  // Defense-in-depth auth gate. Middleware also protects this route
  // (see apps/web/middleware.ts), but Clerk's keyless dev mode
  // short-circuits the middleware callback to surface its claim-keys
  // banner. A server-side check here makes the gate work in both
  // keyless and claimed modes.
  const { userId } = await auth();
  if (!userId) {
    redirect("/sign-in?redirect_url=/dashboard");
  }

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
