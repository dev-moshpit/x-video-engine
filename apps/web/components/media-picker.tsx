"use client";

import { useEffect, useState, useTransition } from "react";
import { useAuth } from "@clerk/nextjs";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  listMediaAssets,
  saveMediaAsset,
  searchMedia,
  type MediaAsset,
  type MediaSearchHit,
} from "@/lib/api";


type Kind = "video" | "image";

/** Modal media picker — shown when the user clicks a "Pick" button on a
 * URL field. Two tabs:
 *
 *   - **Saved** (default): the user's library, filtered by ``kind``.
 *   - **Search**: query Pexels/Pixabay live; clicking a hit saves it
 *     to the library AND selects it.
 *
 * Picking an asset calls ``onPick(url)`` and closes the modal so the
 * caller's form field gets the URL pasted in. The picker doesn't manage
 * its own form state — the caller controls when it opens via ``open``.
 */
export function MediaPicker({
  open,
  onClose,
  onPick,
  kind = "video",
  defaultQuery = "",
}: {
  open: boolean;
  onClose: () => void;
  onPick: (url: string) => void;
  kind?: Kind;
  defaultQuery?: string;
}) {
  const { getToken } = useAuth();

  const [tab, setTab] = useState<"saved" | "search">("saved");
  const [saved, setSaved] = useState<MediaAsset[]>([]);
  const [loadingSaved, setLoadingSaved] = useState(false);
  const [savedError, setSavedError] = useState<string | null>(null);

  const [query, setQuery] = useState(defaultQuery);
  const [hits, setHits] = useState<MediaSearchHit[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searching, startSearch] = useTransition();

  // Hydrate the Saved tab when the picker opens.
  useEffect(() => {
    if (!open) return;
    (async () => {
      setLoadingSaved(true);
      setSavedError(null);
      try {
        const token = await getToken();
        if (!token) throw new Error("not signed in");
        setSaved(await listMediaAssets(token, { kind }));
      } catch (e) {
        setSavedError(e instanceof Error ? e.message : "load failed");
      } finally {
        setLoadingSaved(false);
      }
    })();
  }, [open, kind, getToken]);

  if (!open) return null;

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    startSearch(async () => {
      setSearchError(null);
      try {
        const token = await getToken();
        if (!token) throw new Error("not signed in");
        const res = await searchMedia({ query: query.trim(), kind }, token);
        setHits(res.hits);
        setWarnings(res.warnings);
      } catch (e) {
        setSearchError(e instanceof Error ? e.message : "search failed");
      }
    });
  };

  const onSaveAndPick = async (hit: MediaSearchHit) => {
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      await saveMediaAsset(
        {
          provider: hit.provider,
          provider_asset_id: hit.provider_asset_id,
          kind: hit.kind,
          url: hit.url,
          thumbnail_url: hit.thumbnail_url,
          width: hit.width,
          height: hit.height,
          duration_sec: hit.duration_sec,
          orientation: hit.orientation,
          tags: hit.tags,
          attribution: hit.attribution,
        },
        token,
      );
      onPick(hit.url);
      onClose();
    } catch (e) {
      setSearchError(e instanceof Error ? e.message : "save failed");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div className="flex w-full max-w-3xl max-h-[85vh] flex-col rounded-lg border border-zinc-800 bg-zinc-950 shadow-xl">
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-3">
          <h2 className="text-sm font-semibold">Pick a {kind}</h2>
          <button
            onClick={onClose}
            className="text-xs text-zinc-400 hover:text-zinc-100"
          >
            close ✕
          </button>
        </div>

        <div className="flex border-b border-zinc-800 px-2">
          <TabButton
            active={tab === "saved"}
            onClick={() => setTab("saved")}
            label={`Saved (${saved.length})`}
          />
          <TabButton
            active={tab === "search"}
            onClick={() => setTab("search")}
            label="Search"
          />
        </div>

        <div className="overflow-y-auto p-4">
          {tab === "saved" ? (
            <SavedTab
              loading={loadingSaved}
              error={savedError}
              assets={saved}
              onPick={(url) => {
                onPick(url);
                onClose();
              }}
            />
          ) : (
            <SearchTab
              query={query}
              setQuery={setQuery}
              kind={kind}
              hits={hits}
              warnings={warnings}
              searching={searching}
              error={searchError}
              onSearch={onSearch}
              onSaveAndPick={onSaveAndPick}
            />
          )}
        </div>
      </div>
    </div>
  );
}


function TabButton({
  active, onClick, label,
}: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className={
        "px-4 py-2 text-xs " +
        (active
          ? "border-b-2 border-blue-500 text-zinc-100"
          : "text-zinc-400 hover:text-zinc-200")
      }
    >
      {label}
    </button>
  );
}


function SavedTab({
  loading, error, assets, onPick,
}: {
  loading: boolean;
  error: string | null;
  assets: MediaAsset[];
  onPick: (url: string) => void;
}) {
  if (loading) return <p className="text-sm text-zinc-500">Loading…</p>;
  if (error) {
    return (
      <p className="rounded-md border border-red-900 bg-red-950/30 p-3 text-xs text-red-200">
        {error}
      </p>
    );
  }
  if (assets.length === 0) {
    return (
      <p className="text-sm text-zinc-500">
        Nothing saved yet. Switch to the <strong>Search</strong> tab to find
        something on Pexels or Pixabay.
      </p>
    );
  }
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {assets.map((a) => (
        <PickerCard
          key={a.id}
          thumb={a.thumbnail_url}
          title={a.attribution || a.provider}
          dims={
            a.width && a.height
              ? `${a.width}×${a.height}`
              : null
          }
          dur={a.duration_sec}
          onClick={() => onPick(a.url)}
        />
      ))}
    </div>
  );
}


function SearchTab({
  query, setQuery, kind, hits, warnings, searching, error,
  onSearch, onSaveAndPick,
}: {
  query: string;
  setQuery: (v: string) => void;
  kind: Kind;
  hits: MediaSearchHit[];
  warnings: string[];
  searching: boolean;
  error: string | null;
  onSearch: (e: React.FormEvent) => void;
  onSaveAndPick: (hit: MediaSearchHit) => void;
}) {
  return (
    <div className="space-y-4">
      <form onSubmit={onSearch} className="flex gap-2">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={`Search Pexels & Pixabay for ${kind}s…`}
          className="flex-1"
        />
        <Button type="submit" disabled={searching || !query.trim()}>
          {searching ? "Searching…" : "Search"}
        </Button>
      </form>

      {warnings.length > 0 ? (
        <div className="rounded-md border border-amber-900 bg-amber-950/30 p-3 text-xs text-amber-200">
          {warnings.map((w) => <div key={w}>{w}</div>)}
        </div>
      ) : null}
      {error ? (
        <div className="rounded-md border border-red-900 bg-red-950/30 p-3 text-xs text-red-200">
          {error}
        </div>
      ) : null}

      {hits.length === 0 && !searching ? (
        <p className="text-sm text-zinc-500">
          Try “skateboard”, “ocean”, “neon”, or anything else to start.
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-3">
          {hits.map((h) => (
            <PickerCard
              key={`${h.provider}-${h.provider_asset_id}`}
              thumb={h.thumbnail_url}
              title={h.attribution}
              dims={`${h.width}×${h.height}`}
              dur={h.duration_sec}
              onClick={() => onSaveAndPick(h)}
              ctaLabel="Save &amp; use"
            />
          ))}
        </div>
      )}
    </div>
  );
}


function PickerCard({
  thumb, title, dims, dur, onClick, ctaLabel = "Use",
}: {
  thumb: string | null;
  title: string;
  dims: string | null;
  dur: number | null;
  onClick: () => void;
  ctaLabel?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex flex-col overflow-hidden rounded-md border border-zinc-800 bg-zinc-950/50 text-left transition hover:border-blue-700 hover:bg-zinc-900"
    >
      <div className="aspect-video w-full overflow-hidden bg-zinc-900">
        {thumb ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={thumb}
            alt={title}
            className="h-full w-full object-cover transition group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-zinc-600">
            no preview
          </div>
        )}
      </div>
      <div className="p-2 text-xs text-zinc-400">
        <div className="truncate">{title}</div>
        <div className="mt-0.5 text-[10px] text-zinc-500">
          {dims}
          {dur ? ` · ${dur.toFixed(1)}s` : ""}
        </div>
        <div className="mt-1 text-[11px] text-blue-400 opacity-0 transition group-hover:opacity-100">
          {ctaLabel}
        </div>
      </div>
    </button>
  );
}


/** Convenience trigger: a button + label + the picker modal. Use it
 * inside a template form so the URL field gets a "Pick from library"
 * shortcut without each form re-implementing the modal state. */
export function MediaPickerButton({
  onPick, kind, label = "Pick",
}: {
  onPick: (url: string) => void;
  kind: Kind;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-md border border-zinc-800 px-3 py-1 text-xs text-zinc-300 hover:border-blue-700 hover:bg-zinc-900"
      >
        {label}
      </button>
      <MediaPicker
        open={open}
        onClose={() => setOpen(false)}
        onPick={onPick}
        kind={kind}
      />
    </>
  );
}
