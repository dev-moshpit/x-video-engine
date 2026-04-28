"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { getRecommendations, type Recommendations } from "@/lib/api";


/* Phase 4 + 6 — surfaces the user's per-template winner caption_style /
 * voice / style cue at the top of the create form so the operator
 * doesn't re-pick the same combo on every render.
 *
 * Renders nothing when the user has no signal yet (new account /
 * no starred renders for this template). When there *is* a signal,
 * shows one chip per recommended field; clicking the chip pushes the
 * value into the form's state via the caller-supplied setter. */
export function RecommendationHint({
  template,
  onApplyCaptionStyle,
  onApplyVoice,
  onApplyStyle,
}: {
  template: string;
  onApplyCaptionStyle?: (v: string) => void;
  onApplyVoice?: (v: string) => void;
  onApplyStyle?: (v: string) => void;
}) {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [recs, setRecs] = useState<Recommendations | null>(null);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    let cancelled = false;
    (async () => {
      try {
        const token = await getToken();
        if (!token) return;
        const r = await getRecommendations(template, token);
        if (!cancelled) setRecs(r);
      } catch {
        // Recommendations are optional UX — never block the form.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [template, isLoaded, isSignedIn, getToken]);

  if (!recs) return null;
  const hasAny = recs.caption_style || recs.voice_name || recs.style;
  if (!hasAny) return null;

  return (
    <div className="rounded-md border border-emerald-700/40 bg-emerald-950/20 p-3 text-xs text-emerald-100">
      <div className="mb-1 font-medium">Picks from your starred renders:</div>
      <div className="flex flex-wrap gap-2">
        {recs.caption_style && onApplyCaptionStyle ? (
          <button
            type="button"
            onClick={() => onApplyCaptionStyle(recs.caption_style!)}
            className="rounded-full border border-emerald-700/50 bg-emerald-950/40 px-3 py-1 hover:border-emerald-500 hover:bg-emerald-950/60"
            title={recs.reasons.caption_style}
          >
            captions: <strong>{recs.caption_style}</strong>
          </button>
        ) : null}
        {recs.voice_name && onApplyVoice ? (
          <button
            type="button"
            onClick={() => onApplyVoice(recs.voice_name!)}
            className="rounded-full border border-emerald-700/50 bg-emerald-950/40 px-3 py-1 hover:border-emerald-500 hover:bg-emerald-950/60"
            title={recs.reasons.voice_name}
          >
            voice: <strong>{recs.voice_name}</strong>
          </button>
        ) : null}
        {recs.style && onApplyStyle ? (
          <button
            type="button"
            onClick={() => onApplyStyle(recs.style!)}
            className="rounded-full border border-emerald-700/50 bg-emerald-950/40 px-3 py-1 hover:border-emerald-500 hover:bg-emerald-950/60"
            title={recs.reasons.style}
          >
            style: <strong>{recs.style}</strong>
          </button>
        ) : null}
      </div>
      <div className="mt-1 text-[10px] text-emerald-200/70">
        Click a chip to apply to this form.
      </div>
    </div>
  );
}
