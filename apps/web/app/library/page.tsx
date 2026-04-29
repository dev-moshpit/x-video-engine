"use client";

import { useEffect, useState, useTransition } from "react";
import { useAuth } from "@clerk/nextjs";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  deleteMediaAsset,
  listMediaAssets,
  saveMediaAsset,
  searchMedia,
  type MediaAsset,
  type MediaSearchHit,
} from "@/lib/api";

type Kind = "video" | "image";
type Orientation = "any" | "vertical" | "horizontal" | "square";
type SavedKindFilter = "all" | "video" | "image";

export default function LibraryPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();

  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [loadingAssets, setLoadingAssets] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [savedKindFilter, setSavedKindFilter] = useState<SavedKindFilter>("all");
  const [savedOrientation, setSavedOrientation] = useState<Orientation>("any");

  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<Kind>("video");
  const [orientation, setOrientation] = useState<Orientation>("vertical");
  const [searchHits, setSearchHits] = useState<MediaSearchHit[]>([]);
  const [searchWarnings, setSearchWarnings] = useState<string[]>([]);
  const [searching, startSearch] = useTransition();
  const [searchError, setSearchError] = useState<string | null>(null);
  const [preview, setPreview] = useState<MediaAsset | null>(null);

  const reloadAssets = async () => {
    setLoadingAssets(true);
    setLoadError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const filters: {
        kind?: "video" | "image";
        orientation?: "vertical" | "horizontal" | "square";
      } = {};
      if (savedKindFilter !== "all") filters.kind = savedKindFilter;
      if (savedOrientation !== "any") filters.orientation = savedOrientation;
      setAssets(await listMediaAssets(token, filters));
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "load failed");
    } finally {
      setLoadingAssets(false);
    }
  };

  useEffect(() => {
    if (isLoaded && isSignedIn) reloadAssets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoaded, isSignedIn, savedKindFilter, savedOrientation]);

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    startSearch(async () => {
      setSearchError(null);
      try {
        const token = await getToken();
        if (!token) throw new Error("not signed in");
        const res = await searchMedia(
          { query: query.trim(), kind, orientation },
          token,
        );
        setSearchHits(res.hits);
        setSearchWarnings(res.warnings);
      } catch (e) {
        setSearchError(e instanceof Error ? e.message : "search failed");
      }
    });
  };

  const onSave = async (hit: MediaSearchHit) => {
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
      await reloadAssets();
    } catch (e) {
      setSearchError(e instanceof Error ? e.message : "save failed");
    }
  };

  const onDelete = async (id: string) => {
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      await deleteMediaAsset(id, token);
      setAssets((prev) => prev.filter((a) => a.id !== id));
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "delete failed");
    }
  };

  const copyUrl = (url: string) => {
    navigator.clipboard.writeText(url).catch(() => {});
  };

  return (
    <AppShell>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Media Library</h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-400">
          Search Pexels and Pixabay, save clips and images to your library, and
          paste the URL into any template that asks for a background or main
          clip.
        </p>
      </div>

      {/* ─── Search ──────────────────────────────────────────────────────── */}
      <Card className="mb-8">
        <CardHeader>
          <CardTitle>Search providers</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSearch} className="grid gap-4 sm:grid-cols-12">
            <div className="grid gap-2 sm:col-span-5">
              <Label>Query</Label>
              <Input
                placeholder="skateboard, neon city, ocean…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <div className="grid gap-2 sm:col-span-2">
              <Label>Kind</Label>
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value as Kind)}
                className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100"
              >
                <option value="video">Video</option>
                <option value="image">Image</option>
              </select>
            </div>
            <div className="grid gap-2 sm:col-span-3">
              <Label>Orientation</Label>
              <select
                value={orientation}
                onChange={(e) => setOrientation(e.target.value as Orientation)}
                className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm text-zinc-100"
              >
                <option value="any">Any</option>
                <option value="vertical">Vertical (9:16)</option>
                <option value="horizontal">Horizontal (16:9)</option>
                <option value="square">Square (1:1)</option>
              </select>
            </div>
            <div className="flex items-end sm:col-span-2">
              <Button type="submit" disabled={searching || !query.trim()}>
                {searching ? "Searching…" : "Search"}
              </Button>
            </div>
          </form>

          {searchWarnings.length > 0 ? (
            <div className="mt-4 rounded-md border border-amber-900 bg-amber-950/30 p-3 text-xs text-amber-200">
              {searchWarnings.map((w) => (
                <div key={w}>{w}</div>
              ))}
              <div className="mt-1 text-amber-300/80">
                Set <code>PEXELS_API_KEY</code> and{" "}
                <code>PIXABAY_API_KEY</code> on the api process to enable
                search.
              </div>
            </div>
          ) : null}

          {searchError ? (
            <div className="mt-4 rounded-md border border-red-900 bg-red-950/30 p-3 text-xs text-red-200">
              {searchError}
            </div>
          ) : null}

          {searchHits.length > 0 ? (
            <div className="mt-6 grid gap-4 sm:grid-cols-2 md:grid-cols-3">
              {searchHits.map((hit) => (
                <SearchHitCard
                  key={`${hit.provider}-${hit.provider_asset_id}`}
                  hit={hit}
                  onSave={onSave}
                />
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* ─── Saved assets ───────────────────────────────────────────────── */}
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-lg font-semibold">Saved ({assets.length})</h2>
        <div className="flex flex-wrap items-center gap-3 text-[11px]">
          <FilterChips
            label="Kind"
            value={savedKindFilter}
            onChange={(v) => setSavedKindFilter(v as SavedKindFilter)}
            options={[
              { id: "all", label: "All" },
              { id: "video", label: "Video" },
              { id: "image", label: "Image" },
            ]}
          />
          <FilterChips
            label="Orient."
            value={savedOrientation}
            onChange={(v) => setSavedOrientation(v as Orientation)}
            options={[
              { id: "any", label: "Any" },
              { id: "vertical", label: "9:16" },
              { id: "horizontal", label: "16:9" },
              { id: "square", label: "1:1" },
            ]}
          />
          {loadingAssets ? (
            <span className="text-xs text-zinc-500">Loading…</span>
          ) : null}
        </div>
      </div>
      {loadError ? (
        <div className="mb-4 rounded-md border border-red-900 bg-red-950/30 p-3 text-xs text-red-200">
          {loadError}
        </div>
      ) : null}
      {assets.length === 0 && !loadingAssets ? (
        <SavedEmptyState
          filtered={
            savedKindFilter !== "all" || savedOrientation !== "any"
          }
          onClear={() => {
            setSavedKindFilter("all");
            setSavedOrientation("any");
          }}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3">
          {assets.map((a) => (
            <AssetCard
              key={a.id}
              asset={a}
              onCopy={() => copyUrl(a.url)}
              onDelete={() => onDelete(a.id)}
              onPreview={() => setPreview(a)}
            />
          ))}
        </div>
      )}

      {preview ? (
        <PreviewModal asset={preview} onClose={() => setPreview(null)} />
      ) : null}
    </AppShell>
  );
}

function SearchHitCard({
  hit,
  onSave,
}: {
  hit: MediaSearchHit;
  onSave: (hit: MediaSearchHit) => void;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="aspect-video overflow-hidden rounded-md bg-zinc-900">
          {hit.thumbnail_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={hit.thumbnail_url}
              alt={hit.attribution}
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-zinc-600">
              no preview
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent className="text-xs text-zinc-400">
        <div className="truncate">{hit.attribution}</div>
        <div className="mt-1 text-[10px] text-zinc-500">
          {hit.width}×{hit.height}
          {hit.duration_sec ? ` · ${hit.duration_sec.toFixed(1)}s` : ""} ·{" "}
          {hit.orientation}
        </div>
      </CardContent>
      <CardFooter>
        <Button onClick={() => onSave(hit)} className="ml-auto" size="sm">
          + Save to library
        </Button>
      </CardFooter>
    </Card>
  );
}

function AssetCard({
  asset,
  onCopy,
  onDelete,
  onPreview,
}: {
  asset: MediaAsset;
  onCopy: () => void;
  onDelete: () => void;
  onPreview: () => void;
}) {
  const isAudio = (asset.kind as string) === "audio";
  const isVideo = asset.kind === "video";
  const kindLabel = isAudio ? "♪ AUDIO" : isVideo ? "▶ VIDEO" : "◧ IMAGE";

  return (
    <Card>
      <CardHeader className="pb-2">
        <button
          type="button"
          onClick={onPreview}
          className="relative aspect-video w-full overflow-hidden rounded-md bg-zinc-900 transition hover:opacity-90"
          title="Preview"
        >
          {asset.thumbnail_url && !isAudio ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={asset.thumbnail_url}
              alt={asset.attribution || asset.provider}
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-1 text-xs text-zinc-500">
              <span className="text-2xl">
                {isAudio ? "♪" : isVideo ? "▶" : "◧"}
              </span>
              <span>{isAudio ? "audio file" : "click to preview"}</span>
            </div>
          )}
          <span className="absolute left-1.5 top-1.5 rounded bg-black/70 px-1.5 py-0.5 text-[9px] font-semibold tracking-wider text-zinc-100">
            {kindLabel}
          </span>
          {isVideo && asset.duration_sec ? (
            <span className="absolute right-1.5 bottom-1.5 rounded bg-black/70 px-1.5 py-0.5 text-[9px] text-zinc-100">
              {asset.duration_sec.toFixed(1)}s
            </span>
          ) : null}
        </button>
      </CardHeader>
      <CardContent className="text-xs text-zinc-400">
        <div className="truncate">{asset.attribution || asset.provider}</div>
        <div className="mt-1 text-[10px] text-zinc-500">
          {asset.width && asset.height ? `${asset.width}×${asset.height}` : ""}
          {asset.duration_sec ? ` · ${asset.duration_sec.toFixed(1)}s` : ""}
          {asset.orientation ? ` · ${asset.orientation}` : ""}
        </div>
      </CardContent>
      <CardFooter className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={onCopy}
          className="text-xs text-zinc-300 underline-offset-2 hover:text-zinc-100 hover:underline"
        >
          Copy URL
        </button>
        <button
          type="button"
          onClick={onDelete}
          className="text-xs text-red-300 hover:text-red-200"
        >
          delete
        </button>
      </CardFooter>
    </Card>
  );
}


function FilterChips<T extends string>({
  label, value, onChange, options,
}: {
  label: string;
  value: T;
  onChange: (v: T) => void;
  options: ReadonlyArray<{ id: T; label: string }>;
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-zinc-500">{label}:</span>
      <span className="inline-flex gap-1">
        {options.map((o) => (
          <button
            type="button"
            key={o.id}
            onClick={() => onChange(o.id)}
            className={
              "rounded-full px-2 py-0.5 " +
              (value === o.id
                ? "bg-blue-600 text-white"
                : "bg-zinc-900 text-zinc-400 hover:bg-zinc-800")
            }
          >
            {o.label}
          </button>
        ))}
      </span>
    </span>
  );
}


function SavedEmptyState({
  filtered, onClear,
}: { filtered: boolean; onClear: () => void }) {
  if (filtered) {
    return (
      <div className="rounded-md border border-zinc-900 bg-zinc-950/50 p-6 text-center text-sm text-zinc-400">
        No saved assets match the active filters.
        <button
          type="button"
          onClick={onClear}
          className="ml-2 text-blue-400 underline-offset-4 hover:underline"
        >
          Clear filters
        </button>
      </div>
    );
  }
  return (
    <div className="rounded-md border border-zinc-900 bg-zinc-950/50 p-6 text-center text-sm text-zinc-400">
      <div className="text-zinc-300">Your library is empty.</div>
      <div className="mt-1 text-xs text-zinc-500">
        Search Pexels / Pixabay above and click <strong>Save</strong> to keep an
        asset around — or pick one straight from a template form.
      </div>
    </div>
  );
}


function PreviewModal({
  asset, onClose,
}: {
  asset: MediaAsset;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
      onClick={onClose}
    >
      <div
        className="flex w-full max-w-3xl flex-col gap-3 rounded-lg border border-zinc-800 bg-zinc-950 p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <div className="text-sm text-zinc-200">
            {asset.attribution || asset.provider}
          </div>
          <button
            onClick={onClose}
            className="text-xs text-zinc-400 hover:text-zinc-100"
          >
            close ✕
          </button>
        </div>
        <div className="aspect-video w-full overflow-hidden rounded-md bg-black">
          {asset.kind === "video" ? (
            // eslint-disable-next-line jsx-a11y/media-has-caption
            <video
              src={asset.url}
              controls
              autoPlay
              loop
              muted
              className="h-full w-full"
            />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={asset.url}
              alt={asset.attribution || ""}
              className="h-full w-full object-contain"
            />
          )}
        </div>
        <div className="flex items-center justify-between text-xs text-zinc-400">
          <div>
            {asset.width && asset.height ? `${asset.width}×${asset.height}` : ""}
            {asset.duration_sec ? ` · ${asset.duration_sec.toFixed(1)}s` : ""}
            {asset.orientation ? ` · ${asset.orientation}` : ""}
          </div>
          <button
            onClick={() => {
              navigator.clipboard.writeText(asset.url).catch(() => {});
            }}
            className="rounded-md border border-zinc-800 px-3 py-1 text-zinc-300 hover:bg-zinc-900"
          >
            Copy URL
          </button>
        </div>
      </div>
    </div>
  );
}
