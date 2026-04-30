import Link from "next/link";

import { AppShell } from "@/components/app-shell";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";


/** Settings hub. Links to the per-section pages and the Clerk-managed
 * account UI (the avatar in the app-shell opens it). */
export default function SettingsIndex() {
  const sections = [
    {
      href: "/settings/brand",
      title: "Brand kit",
      blurb:
        "Colors, logo, and brand name applied to color-aware templates.",
    },
    {
      href: "/settings/billing",
      title: "Billing",
      blurb: "Plan, credit balance, and Stripe customer portal.",
    },
    {
      href: "/presets",
      title: "Presets",
      blurb: "Manage your saved prompt configurations.",
    },
    {
      href: "/library",
      title: "Media library",
      blurb: "Search Pexels/Pixabay and save assets for reuse.",
    },
    {
      href: "/settings/system",
      title: "System health",
      blurb: "Live status of ffmpeg, Redis, storage, GPU, and AI model caches.",
    },
  ];

  return (
    <AppShell>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-zinc-400">
          Account, billing, brand kit, and reusable inputs.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {sections.map((s) => (
          <Link key={s.href} href={s.href}>
            <Card className="transition-colors hover:border-zinc-700">
              <CardHeader>
                <CardTitle className="text-base">{s.title}</CardTitle>
                <CardDescription>{s.blurb}</CardDescription>
              </CardHeader>
              <CardContent className="text-xs text-zinc-500">
                Open →
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </AppShell>
  );
}
