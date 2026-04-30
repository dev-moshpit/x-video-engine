"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";

import { getBillingStatus, type BillingStatus } from "@/lib/api";


/** Phase 10.5 — global credit-balance pill for the app shell.
 *
 * Refetches when the route changes (mount-on-nav) so the value tracks
 * usage across the session without explicit client-side cache wiring.
 * Hidden when the user isn't signed in or the api can't be reached.
 */
export function CreditBalance() {
  const { isSignedIn, isLoaded, getToken } = useAuth();
  const [status, setStatus] = useState<BillingStatus | null>(null);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const s = await getBillingStatus(token);
        if (!cancelled) setStatus(s);
      } catch {
        /* swallow — pill just stays hidden */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, getToken]);

  if (!status) return null;

  const low = status.balance < 5;
  return (
    <Link
      href={status.tier === "free" ? "/pricing" : "/settings/billing"}
      title={`${status.tier} tier · ${status.balance} credits`}
      className={
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition " +
        (low
          ? "border-amber-700 bg-amber-950/30 text-amber-200 hover:border-amber-500"
          : "border-zinc-800 text-zinc-300 hover:border-zinc-600")
      }
    >
      <span aria-hidden>◆</span>
      <span>{status.balance}</span>
    </Link>
  );
}
