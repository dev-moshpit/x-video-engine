"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { Button } from "@/components/ui/button";
import { getBillingStatus, type BillingStatus } from "@/lib/api";


/** Phase 10 — modal shown when an action returns 402 Payment Required.
 * Pulls the current billing status so we can show the user how many
 * credits they actually have left (almost always 0 here, but we read
 * live so an admin-granted top-up doesn't lie). */
export function UpgradeModal({
  open,
  onClose,
  context = "render",
}: {
  open: boolean;
  onClose: () => void;
  context?: string;
}) {
  const { getToken, isSignedIn } = useAuth();
  const [status, setStatus] = useState<BillingStatus | null>(null);

  useEffect(() => {
    if (!open || !isSignedIn) return;
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const s = await getBillingStatus(token);
        if (!cancelled) setStatus(s);
      } catch {
        /* swallow */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, isSignedIn, getToken]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-lg border border-zinc-800 bg-zinc-950 p-6 shadow-xl"
      >
        <div className="mb-4">
          <h2 className="text-lg font-semibold tracking-tight">
            Out of credits
          </h2>
          <p className="mt-1 text-sm text-zinc-400">
            This {context} needs more credits than you have. Upgrade your plan
            and the {context} will land in your project right away.
          </p>
        </div>

        {status ? (
          <div className="mb-4 grid grid-cols-2 gap-3 rounded-md border border-zinc-800 bg-zinc-900/50 p-3 text-xs">
            <div>
              <div className="text-zinc-500">Current plan</div>
              <div className="mt-0.5 font-medium capitalize text-zinc-100">
                {status.tier}
              </div>
            </div>
            <div>
              <div className="text-zinc-500">Credits left</div>
              <div className="mt-0.5 font-medium text-zinc-100">
                {status.balance}
              </div>
            </div>
            <div className="col-span-2">
              <div className="text-zinc-500">Plan refill</div>
              <div className="mt-0.5 text-zinc-300">
                {status.monthly_credits} credits / month
                {status.current_period_end
                  ? ` · renews ${new Date(status.current_period_end).toLocaleDateString()}`
                  : ""}
              </div>
            </div>
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <Link href="/pricing" className="flex-1">
            <Button className="w-full">Upgrade →</Button>
          </Link>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </div>

        <p className="mt-3 text-[11px] text-zinc-500">
          Pro: 600 credits / month, no watermark · Business: 3,000
          credits / month, 8 concurrent renders.
        </p>
      </div>
    </div>
  );
}
