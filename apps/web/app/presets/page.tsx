"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

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
import { Input } from "@/components/ui/input";
import {
  createSavedPrompt,
  deleteSavedPrompt,
  listSavedPrompts,
  listTemplates,
  updateSavedPrompt,
  useSavedPrompt,
  type SavedPrompt,
  type TemplateMeta,
} from "@/lib/api";


export default function PresetsPage() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const router = useRouter();

  const [presets, setPresets] = useState<SavedPrompt[]>([]);
  const [templates, setTemplates] = useState<TemplateMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [filterTemplate, setFilterTemplate] = useState<string>("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoaded) return;
    if (!isSignedIn) {
      router.push("/sign-in?redirect_url=/presets");
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const token = await getToken();
        if (!token) throw new Error("not signed in");
        const [p, t] = await Promise.all([
          listSavedPrompts(token),
          listTemplates(),
        ]);
        if (cancelled) return;
        setPresets(p);
        setTemplates(t);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "load failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, getToken, router]);

  const templateName = useMemo(() => {
    const m = new Map<string, string>();
    templates.forEach((t) => m.set(t.template_id, t.name));
    return m;
  }, [templates]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return presets.filter((p) => {
      if (filterTemplate && p.template !== filterTemplate) return false;
      if (q) {
        const hay = `${p.label} ${p.template} ${
          templateName.get(p.template) ?? ""
        }`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [presets, search, filterTemplate, templateName]);

  const onUse = async (preset: SavedPrompt) => {
    setBusyId(preset.id);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const project = await useSavedPrompt(preset.id, {}, token);
      router.push(`/projects/${project.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "use preset failed");
      setBusyId(null);
    }
  };

  const onDuplicate = async (preset: SavedPrompt) => {
    setBusyId(preset.id);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const created = await createSavedPrompt(
        {
          template: preset.template,
          label: `${preset.label} (copy)`,
          template_input: preset.template_input,
        },
        token,
      );
      setPresets((p) => [created, ...p]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "duplicate failed");
    } finally {
      setBusyId(null);
    }
  };

  const onStartRename = (preset: SavedPrompt) => {
    setRenamingId(preset.id);
    setRenameValue(preset.label);
  };

  const onSaveRename = async (preset: SavedPrompt) => {
    const next = renameValue.trim();
    if (!next || next === preset.label) {
      setRenamingId(null);
      return;
    }
    setBusyId(preset.id);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const updated = await updateSavedPrompt(
        preset.id,
        { label: next },
        token,
      );
      setPresets((p) => p.map((x) => (x.id === preset.id ? updated : x)));
      setRenamingId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "rename failed");
    } finally {
      setBusyId(null);
    }
  };

  const onDelete = async (preset: SavedPrompt) => {
    if (!confirm(`Delete preset "${preset.label}"?`)) return;
    setBusyId(preset.id);
    try {
      const token = await getToken();
      if (!token) return;
      await deleteSavedPrompt(preset.id, token);
      setPresets((p) => p.filter((x) => x.id !== preset.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "delete failed");
    } finally {
      setBusyId(null);
    }
  };

  const usedTemplates = useMemo(() => {
    const set = new Set(presets.map((p) => p.template));
    return Array.from(set);
  }, [presets]);

  return (
    <AppShell>
      <div className="mb-8 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Presets</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Reusable prompt configurations. Save a project as a preset, then
            stamp out new videos in one click.
          </p>
        </div>
        <Link href="/templates">
          <Button>Create video →</Button>
        </Link>
      </div>

      {error ? (
        <div className="mb-6 rounded-md border border-red-900 bg-red-950/30 p-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <Input
          placeholder="Search presets…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-64"
        />
        <select
          value={filterTemplate}
          onChange={(e) => setFilterTemplate(e.target.value)}
          className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-3 text-sm"
        >
          <option value="">All templates</option>
          {usedTemplates.map((t) => (
            <option key={t} value={t}>
              {templateName.get(t) ?? t}
            </option>
          ))}
        </select>
        <span className="ml-auto text-xs text-zinc-500">
          {filtered.length} of {presets.length}
        </span>
      </div>

      {loading ? (
        <p className="text-sm text-zinc-500">Loading…</p>
      ) : presets.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>No presets yet</CardTitle>
            <CardDescription>
              Open any project, click <strong>Save as preset</strong> on the
              header, and it will show up here.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link href="/templates">
              <Button>Browse templates</Button>
            </Link>
          </CardContent>
        </Card>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-zinc-500">No presets match those filters.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((p) => (
            <Card key={p.id} className="flex flex-col">
              <CardHeader>
                <div className="flex items-start justify-between gap-2">
                  {renamingId === p.id ? (
                    <Input
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") onSaveRename(p);
                        if (e.key === "Escape") setRenamingId(null);
                      }}
                      autoFocus
                      className="h-8"
                    />
                  ) : (
                    <CardTitle className="text-base">{p.label}</CardTitle>
                  )}
                  <Badge tone="muted">
                    {templateName.get(p.template) ?? p.template}
                  </Badge>
                </div>
                <CardDescription className="text-xs">
                  used {p.use_count}× ·{" "}
                  {p.last_used_at
                    ? `last ${new Date(p.last_used_at).toLocaleDateString()}`
                    : "never used"}
                  {" · created "}
                  {new Date(p.created_at).toLocaleDateString()}
                </CardDescription>
              </CardHeader>
              <CardContent className="mt-auto flex flex-wrap items-center gap-2 pt-0">
                {renamingId === p.id ? (
                  <>
                    <Button
                      size="sm"
                      onClick={() => onSaveRename(p)}
                      disabled={busyId === p.id}
                    >
                      Save name
                    </Button>
                    <button
                      type="button"
                      onClick={() => setRenamingId(null)}
                      className="text-xs text-zinc-500 hover:text-zinc-300"
                    >
                      cancel
                    </button>
                  </>
                ) : (
                  <>
                    <Button
                      size="sm"
                      onClick={() => onUse(p)}
                      disabled={busyId === p.id}
                    >
                      Create video from preset →
                    </Button>
                    <button
                      type="button"
                      onClick={() => onDuplicate(p)}
                      disabled={busyId === p.id}
                      className="text-xs text-zinc-400 hover:text-zinc-100"
                    >
                      duplicate
                    </button>
                    <button
                      type="button"
                      onClick={() => onStartRename(p)}
                      className="text-xs text-zinc-400 hover:text-zinc-100"
                    >
                      rename
                    </button>
                    <button
                      type="button"
                      onClick={() => onDelete(p)}
                      disabled={busyId === p.id}
                      className="ml-auto text-xs text-zinc-500 hover:text-red-300"
                    >
                      delete
                    </button>
                  </>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </AppShell>
  );
}
