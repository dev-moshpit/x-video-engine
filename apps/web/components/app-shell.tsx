import { UserButton } from "@clerk/nextjs";
import Link from "next/link";

import { CreditBalance } from "@/components/credit-balance";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-dvh">
      <header className="border-b border-zinc-900 px-6 py-4">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <Link
            href="/dashboard"
            className="text-sm font-semibold tracking-tight"
          >
            x-video-engine
          </Link>
          <nav className="flex items-center gap-4 text-sm">
            <Link
              href="/dashboard"
              className="text-zinc-400 hover:text-zinc-100"
            >
              Dashboard
            </Link>
            <Link
              href="/create"
              className="rounded-md bg-emerald-700/20 px-3 py-1 font-medium text-emerald-200 hover:bg-emerald-700/30"
            >
              + Create
            </Link>
            <Link
              href="/library"
              className="text-zinc-400 hover:text-zinc-100"
            >
              Library
            </Link>
            <Link
              href="/pricing"
              className="text-zinc-400 hover:text-zinc-100"
            >
              Pricing
            </Link>
            <Link
              href="/settings"
              className="text-zinc-400 hover:text-zinc-100"
            >
              Settings
            </Link>
            <CreditBalance />
            <UserButton />
          </nav>
        </div>
      </header>
      <div className="mx-auto max-w-6xl px-6 py-10">{children}</div>
    </div>
  );
}
