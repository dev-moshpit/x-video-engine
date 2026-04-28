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

export default function LibraryPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();

  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [loadingAssets, setLoadingAssets] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<Kind>("video");
  const [orientation, setOrientation] = useState<Orientation>("vertical");
  const [searchHits, setSearchHits] = useState<MediaSearchHit[]>([]);
  const [searchWarnings, setSearchWarnings] = useState<string[]>([]);
  const [searching, startSearch] = useTransition();
  const [searchError, setSearchError] = useState<string | null>(null);

  const reloadAssets = async () => {
    setLoadingAssets(true);
    setLoadError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      setAssets(await listMediaAssets(token));
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : "load failed");
    } finally {
      setLoadingAssets(false);
    }
  };

  useEffect(() => {
    if (isLoaded && isSignedIn) reloadAssets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoaded, isSignedIn]);

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
      <div className="mb-4 flex items-end justify-between">
        <h2 className="text-lg font-semibold">Saved ({assets.length})</h2>
        {loadingAssets ? (
          <span className="text-xs text-zinc-500">Loading…</span>
        ) : null}
      </div>
      {loadError ? (
        <div className="mb-4 rounded-md border border-red-900 bg-red-950/30 p-3 text-xs text-red-200">
          {loadError}
        </div>
      ) : null}
      {assets.length === 0 && !loadingAssets ? (
        <p className="text-sm text-zinc-500">
          Nothing saved yet — search above and click{" "}
          <span className="font-mono text-zinc-300">Save</span>.
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-3">
          {assets.map((a) => (
            <AssetCard
              key={a.id}
              asset={a}
              onCopy={() => copyUrl(a.url)}
              onDelete={() => onDelete(a.id)}
            />
          ))}
        </div>
      )}
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
        <Button onClick={() => onSave(hit)} className="ml-auto">
          Save
        </Button>
      </CardFooter>
    </Card>
  );
}

function AssetCard({
  asset,
  onCopy,
  onDelete,
}: {
  asset: MediaAsset;
  onCopy: () => void;
  onDelete: () => void;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="aspect-video overflow-hidden rounded-md bg-zinc-900">
          {asset.thumbnail_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={asset.thumbnail_url}
              alt={asset.attribution || asset.provider}
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
        <div className="truncate">{asset.attribution || asset.provider}</div>
        <div className="mt-1 text-[10px] text-zinc-500">
          {asset.width && asset.height ? `${asset.width}×${asset.height}` : ""}
          {asset.duration_sec ? ` · ${asset.duration_sec.toFixed(1)}s` : ""}
          {asset.orientation ? ` · ${asset.orientation}` : ""}
        </div>
      </CardContent>
      <CardFooter className="flex items-center justify-between gap-2">
        <Button onClick={onCopy} className="text-xs">
          Copy URL
        </Button>
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
