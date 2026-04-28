"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";

import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  createPortal,
  getBillingStatus,
  type BillingStatus,
} from "@/lib/api";


export default function BillingSettingsPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openingPortal, setOpeningPortal] = useState(false);

  const reload = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      setStatus(await getBillingStatus(token));
    } catch (e) {
      setError(e instanceof Error ? e.message : "load failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isLoaded && isSignedIn) reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoaded, isSignedIn]);

  const handleOpenPortal = async () => {
    setOpeningPortal(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const origin = window.location.origin;
      const { url } = await createPortal(
        { return_url: `${origin}/settings/billing` },
        token,
      );
      window.location.href = url;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "portal open failed";
      if (msg.includes("503")) {
        setError(
          "Billing portal isn't wired up in this environment yet.",
        );
      } else if (msg.includes("400")) {
        setError(
          "No active subscription — upgrade on /pricing first.",
        );
      } else {
        setError(msg);
      }
      setOpeningPortal(false);
    }
  };

  return (
    <AppShell>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Billing</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Your current plan, credit balance, and Stripe billing portal.
        </p>
      </div>

      {error ? (
        <div className="mb-6 rounded-md border border-amber-900 bg-amber-950/30 p-3 text-sm text-amber-200">
          {error}
        </div>
      ) : null}

      {loading || !status ? (
        <p className="text-sm text-zinc-500">Loading…</p>
      ) : (
        <div className="grid gap-6 sm:grid-cols-2">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="capitalize">{status.tier} plan</CardTitle>
                {status.has_active_subscription ? (
                  <Badge tone="ok">active</Badge>
                ) : (
                  <Badge tone="muted">free tier</Badge>
                )}
              </div>
              <CardDescription>
                {status.monthly_credits} credits / month ·{" "}
                {status.watermark ? "watermarked output" : "no watermark"}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              {status.current_period_end ? (
                <div className="text-zinc-400">
                  Renews{" "}
                  <span className="text-zinc-200">
                    {new Date(status.current_period_end).toLocaleDateString()}
                  </span>
                </div>
              ) : null}
              <div className="flex flex-wrap gap-3 pt-2">
                {status.has_active_subscription ? (
                  <Button
                    onClick={handleOpenPortal}
                    disabled={openingPortal}
                  >
                    {openingPortal ? "Opening…" : "Manage billing"}
                  </Button>
                ) : (
                  <Link href="/pricing">
                    <Button>Upgrade</Button>
                  </Link>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Credit balance</CardTitle>
              <CardDescription>One render = one credit.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-semibold tracking-tight">
                {status.balance}
              </div>
              <p className="mt-2 text-xs text-zinc-500">
                Refilled to {status.monthly_credits} on each successful invoice.
              </p>
              {status.balance < 5 ? (
                <div className="mt-4 rounded-md border border-amber-900 bg-amber-950/30 p-3 text-xs text-amber-200">
                  Running low. Renders will return{" "}
                  <code>402 Payment Required</code> when you hit zero.
                  {status.tier === "free" ? (
                    <>
                      {" "}
                      <Link
                        href="/pricing"
                        className="underline hover:text-amber-100"
                      >
                        Upgrade →
                      </Link>
                    </>
                  ) : null}
                </div>
              ) : null}
            </CardContent>
          </Card>
        </div>
      )}
    </AppShell>
  );
}
