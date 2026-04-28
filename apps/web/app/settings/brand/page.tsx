"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  deleteBrandKit,
  getBrandKit,
  upsertBrandKit,
  type BrandKit,
} from "@/lib/api";


const EMPTY: BrandKit = {
  brand_color: null,
  accent_color: null,
  text_color: null,
  logo_url: null,
  brand_name: null,
};


export default function BrandSettingsPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [kit, setKit] = useState<BrandKit>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    (async () => {
      try {
        const token = await getToken();
        if (!token) return;
        setKit(await getBrandKit(token));
      } catch (e) {
        setError(e instanceof Error ? e.message : "load failed");
      }
    })();
  }, [isLoaded, isSignedIn, getToken]);

  const setField = <K extends keyof BrandKit>(k: K, v: BrandKit[K]) => {
    setSavedOk(false);
    setKit((prev) => ({ ...prev, [k]: v }));
  };

  const onSave = async () => {
    setSaving(true);
    setError(null);
    setSavedOk(false);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      // Trim empty hex strings to null so the api accepts them.
      const cleaned: BrandKit = {
        brand_color: emptyToNull(kit.brand_color),
        accent_color: emptyToNull(kit.accent_color),
        text_color: emptyToNull(kit.text_color),
        logo_url: emptyToNull(kit.logo_url),
        brand_name: emptyToNull(kit.brand_name),
      };
      const next = await upsertBrandKit(cleaned, token);
      setKit(next);
      setSavedOk(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "save failed");
    } finally {
      setSaving(false);
    }
  };

  const onClear = async () => {
    setSaving(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      try {
        await deleteBrandKit(token);
      } catch {
        // 404 = nothing to delete; treat as success.
      }
      setKit(EMPTY);
      setSavedOk(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "clear failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppShell>
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Brand Kit</h1>
        <p className="mt-1 max-w-2xl text-sm text-zinc-400">
          Apply your brand colors and logo to color-aware templates
          (Top 5, Twitter, more soon). Leave any field blank to keep the
          template default.
        </p>
      </div>

      {error ? (
        <div className="mb-6 rounded-md border border-red-900 bg-red-950/30 p-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}
      {savedOk ? (
        <div className="mb-6 rounded-md border border-emerald-900 bg-emerald-950/30 p-3 text-sm text-emerald-200">
          Brand kit saved.
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Tokens</CardTitle>
          <CardDescription>
            Hex colors only (e.g. <code>#1f6feb</code>).
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5">
          <div className="grid gap-2 sm:grid-cols-3">
            <div className="grid gap-2">
              <Label>Brand color</Label>
              <ColorInput
                value={kit.brand_color}
                onChange={(v) => setField("brand_color", v)}
              />
              <p className="text-[10px] text-zinc-500">
                Used for accent — rank numbers, verified check, footer.
              </p>
            </div>
            <div className="grid gap-2">
              <Label>Accent / page bg</Label>
              <ColorInput
                value={kit.accent_color}
                onChange={(v) => setField("accent_color", v)}
              />
              <p className="text-[10px] text-zinc-500">
                Used for the panel background on Top 5 + tweet card page.
              </p>
            </div>
            <div className="grid gap-2">
              <Label>Text color</Label>
              <ColorInput
                value={kit.text_color}
                onChange={(v) => setField("text_color", v)}
              />
              <p className="text-[10px] text-zinc-500">
                Reserved for future use (currently auto-derived).
              </p>
            </div>
          </div>

          <div className="grid gap-2 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label>Brand name</Label>
              <Input
                placeholder="Acme Studios"
                value={kit.brand_name ?? ""}
                onChange={(e) => setField("brand_name", e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label>Logo URL</Label>
              <Input
                placeholder="https://… .png / .svg"
                value={kit.logo_url ?? ""}
                onChange={(e) => setField("logo_url", e.target.value)}
              />
              <p className="text-[10px] text-zinc-500">
                Reserved for future overlay. Not yet rendered.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <Button onClick={onSave} disabled={saving}>
              {saving ? "Saving…" : "Save brand kit"}
            </Button>
            <button
              type="button"
              onClick={onClear}
              disabled={saving}
              className="text-xs text-red-300 hover:text-red-200"
            >
              clear all
            </button>
          </div>
        </CardContent>
      </Card>
    </AppShell>
  );
}


function ColorInput({
  value, onChange,
}: { value: string | null; onChange: (v: string | null) => void }) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="color"
        value={value ?? "#000000"}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-12 cursor-pointer rounded-md border border-zinc-800 bg-zinc-950"
      />
      <Input
        pattern="^#[0-9a-fA-F]{6}$"
        placeholder="#1f6feb"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
        className="flex-1"
      />
    </div>
  );
}


function emptyToNull(v: string | null): string | null {
  if (v === null) return null;
  const t = v.trim();
  return t.length === 0 ? null : t;
}
