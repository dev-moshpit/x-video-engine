import * as React from "react";
import { cn } from "@/lib/utils";

type Tone = "default" | "muted" | "warn" | "error" | "ok";

const TONES: Record<Tone, string> = {
  default: "border-zinc-700 bg-zinc-900 text-zinc-200",
  muted: "border-zinc-800 bg-zinc-950 text-zinc-400",
  warn: "border-amber-700 bg-amber-950 text-amber-200",
  error: "border-red-700 bg-red-950 text-red-200",
  ok: "border-emerald-700 bg-emerald-950 text-emerald-200",
};

export const Badge = ({
  className,
  tone = "default",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) => (
  <span
    className={cn(
      "inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide",
      TONES[tone],
      className,
    )}
    {...props}
  />
);
