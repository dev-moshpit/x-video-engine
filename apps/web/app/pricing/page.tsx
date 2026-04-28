"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  createCheckout,
  getBillingStatus,
  listTiers,
  type BillingStatus,
  type TierInfo,
} from "@/lib/api";


/* Public pricing page. Tiers + features come straight from
 * /api/billing/tiers so the catalog is the source of truth — no
 * duplicated copy here. Upgrade buttons hit /api/billing/checkout
 * and redirect to Stripe Checkout when configured; fall back to a
 * "Stripe not set up yet" notice on 503. */
export default function PricingPage() {
  const { getToken, isSignedIn, isLoaded } = useAuth();
  const router = useRouter();

  const [tiers, setTiers] = useState<TierInfo[]>([]);
  const [status, setStatus] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [upgrading, setUpgrading] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const t = await listTiers();
        if (!cancelled) setTiers(t);
        if (isLoaded && isSignedIn) {
          const token = await getToken();
          if (token && !cancelled) setStatus(await getBillingStatus(token));
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "load failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, getToken]);

  const handleUpgrade = async (tier: "pro" | "business") => {
    setUpgrading(tier);
    setError(null);
    try {
      if (!isSignedIn) {
        router.push(`/sign-in?redirect_url=/pricing`);
        return;
      }
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const origin = window.location.origin;
      const { url } = await createCheckout(
        {
          tier,
          success_url: `${origin}/settings/billing?checkout=success`,
          cancel_url: `${origin}/pricing?checkout=cancel`,
        },
        token,
      );
      window.location.href = url;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "checkout failed";
      // Surface Stripe-not-configured as a friendly notice rather than
      // a red banner — common in dev.
      if (msg.includes("503")) {
        setError(
          "Checkout isn't wired up in this environment yet. Set STRIPE_SECRET_KEY + STRIPE_PRICE_PRO/BUSINESS on the api process.",
        );
      } else {
        setError(msg);
      }
      setUpgrading(null);
    }
  };

  return (
    <AppShell>
      <div className="mb-10 text-center">
        <h1 className="text-3xl font-semibold tracking-tight">Pricing</h1>
        <p className="mx-auto mt-2 max-w-xl text-sm text-zinc-400">
          Pay-as-you-render with a generous free tier. One render = one credit
          regardless of template. Upgrade anytime; the change takes effect
          immediately.
        </p>
      </div>

      {error ? (
        <div className="mx-auto mb-6 max-w-2xl rounded-md border border-amber-900 bg-amber-950/30 p-3 text-sm text-amber-200">
          {error}
        </div>
      ) : null}

      {loading && tiers.length === 0 ? (
        <p className="text-center text-sm text-zinc-500">Loading…</p>
      ) : (
        <div className="grid gap-6 sm:grid-cols-3">
          {tiers.map((t) => {
            const isCurrent = status?.tier === t.name;
            const isFree = t.name === "free";
            const action: "current" | "downgrade" | "upgrade" | "signin" = !isLoaded || !isSignedIn
              ? isFree
                ? "current"
                : "signin"
              : isCurrent
                ? "current"
                : isFree
                  ? "downgrade"
                  : "upgrade";

            return (
              <Card
                key={t.name}
                className={
                  t.name === "pro"
                    ? "border-blue-700/60 ring-1 ring-blue-700/40"
                    : ""
                }
              >
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle>{t.display_name}</CardTitle>
                    {isCurrent ? (
                      <Badge tone="ok">current</Badge>
                    ) : t.name === "pro" ? (
                      <Badge tone="muted">popular</Badge>
                    ) : null}
                  </div>
                  <CardDescription>
                    {t.monthly_credits} renders / month
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-2 text-sm text-zinc-300">
                  <div>• Up to {t.concurrent_renders} concurrent renders</div>
                  <div>
                    {t.watermark ? (
                      <span className="text-zinc-400">
                        • Watermarked output
                      </span>
                    ) : (
                      <span className="text-emerald-300">
                        • No watermark
                      </span>
                    )}
                  </div>
                  <div>• All 10 templates</div>
                  <div>• Pexels &amp; Pixabay search</div>
                </CardContent>
                <CardFooter>
                  {action === "current" ? (
                    <Button disabled className="w-full">
                      Current plan
                    </Button>
                  ) : action === "signin" ? (
                    <Button
                      onClick={() =>
                        router.push(`/sign-up?redirect_url=/pricing`)
                      }
                      className="w-full"
                    >
                      Sign up
                    </Button>
                  ) : action === "downgrade" ? (
                    <Button
                      disabled
                      className="w-full"
                      title="Downgrade via the billing portal"
                    >
                      Downgrade
                    </Button>
                  ) : (
                    <Button
                      disabled={!t.purchaseable || upgrading === t.name}
                      onClick={() => handleUpgrade(t.name as "pro" | "business")}
                      className="w-full"
                    >
                      {upgrading === t.name
                        ? "Redirecting…"
                        : t.purchaseable
                          ? `Upgrade to ${t.display_name}`
                          : "Coming soon"}
                    </Button>
                  )}
                </CardFooter>
              </Card>
            );
          })}
        </div>
      )}

      {status ? (
        <p className="mt-8 text-center text-xs text-zinc-500">
          You're on{" "}
          <span className="font-mono text-zinc-300">{status.tier}</span> —
          balance:{" "}
          <span className="font-mono text-zinc-300">{status.balance}</span>{" "}
          credits.{" "}
          <a
            className="underline hover:text-zinc-300"
            href="/settings/billing"
          >
            Manage billing →
          </a>
        </p>
      ) : null}
    </AppShell>
  );
}
