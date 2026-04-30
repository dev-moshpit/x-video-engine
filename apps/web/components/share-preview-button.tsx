"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { Button } from "@/components/ui/button";
import {
  createRenderShare,
  deleteRenderShare,
  getRenderShare,
  type RenderShare,
} from "@/lib/api";


/** Phase 13 — share preview link button.
 *
 * Inline, owner-only. Loads the current share state on mount; on click
 * it creates the link if missing, copies the public URL to the clipboard,
 * and offers a disable toggle. The actual public page lives at
 * ``apps/web/app/share/[token]/page.tsx`` and is unauthenticated.
 */
export function SharePreviewButton({ jobId }: { jobId: string }) {
  const { getToken } = useAuth();
  const [share, setShare] = useState<RenderShare | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const token = await getToken();
        if (!token) return;
        const s = await getRenderShare(jobId, token);
        if (!cancelled) setShare(s);
      } catch {
        // 404 is the steady-state when no share exists yet — swallow.
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [jobId, getToken]);

  const publicUrl = (token: string) =>
    typeof window !== "undefined"
      ? `${window.location.origin}/share/${token}`
      : `/share/${token}`;

  const onCopy = async (token: string) => {
    try {
      await navigator.clipboard.writeText(publicUrl(token));
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* ignore */
    }
  };

  const onCreate = async () => {
    setBusy(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const s = await createRenderShare(jobId, {}, token);
      setShare(s);
      await onCopy(s.token);
    } catch (e) {
      setError(e instanceof Error ? e.message : "share failed");
    } finally {
      setBusy(false);
    }
  };

  const onDisable = async () => {
    setBusy(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      await deleteRenderShare(jobId, token);
      setShare((s) => (s ? { ...s, is_active: false } : s));
    } catch (e) {
      setError(e instanceof Error ? e.message : "disable failed");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <span className="text-[10px] text-zinc-500">loading…</span>;
  }

  if (!share || !share.is_active) {
    return (
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onCreate}
          disabled={busy}
          className="text-xs text-zinc-300 underline-offset-4 hover:underline disabled:opacity-50"
        >
          {busy ? "Sharing…" : "↗ Share preview"}
        </button>
        {error ? <span className="text-[10px] text-red-300">{error}</span> : null}
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <Button
        size="sm"
        variant="outline"
        onClick={() => onCopy(share.token)}
        disabled={busy}
      >
        {copied ? "✓ Copied" : "Copy share link"}
      </Button>
      <button
        type="button"
        onClick={onDisable}
        disabled={busy}
        className="text-zinc-500 hover:text-red-300"
      >
        disable
      </button>
      {error ? <span className="text-red-300">{error}</span> : null}
    </div>
  );
}
