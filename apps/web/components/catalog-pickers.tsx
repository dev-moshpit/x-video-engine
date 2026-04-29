"use client";

import { useEffect, useState } from "react";

import {
  listCaptionLanguages,
  listPacingPresets,
  listStylePresets,
  listVoiceCategories,
  listVoices,
  type CaptionLanguage,
  type PacingMeta,
  type StylePresetMeta,
  type VoiceCategory,
  type VoiceInfo,
} from "@/lib/api";


/** Cached catalog fetches.
 *
 * The catalog endpoints are public and small; the same client renders
 * many forms in a session. We cache the response so the second
 * `<StylePresetPicker />` doesn't re-fetch.
 */
const _cache: {
  styles?: Promise<StylePresetMeta[]>;
  pacing?: Promise<PacingMeta[]>;
  voiceCategories?: Promise<VoiceCategory[]>;
  voices?: Promise<VoiceInfo[]>;
  languages?: Promise<CaptionLanguage[]>;
} = {};

function useCatalog<T>(
  key: keyof typeof _cache,
  fetcher: () => Promise<T>,
): { data: T | null; error: string | null } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    const promise = (_cache[key] as Promise<T> | undefined) ?? fetcher();
    (_cache as Record<string, unknown>)[key] = promise;
    promise.then(
      (v) => {
        if (!cancelled) setData(v);
      },
      (e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "load failed");
      },
    );
    return () => {
      cancelled = true;
    };
  }, [key, fetcher]);
  return { data, error };
}


// ─── Style preset picker ─────────────────────────────────────────────────

export function StylePresetPicker({
  value, onChange, label = "Visual style",
}: {
  value: string | undefined;
  onChange: (id: string | undefined) => void;
  label?: string;
}) {
  const { data, error } = useCatalog<StylePresetMeta[]>("styles", listStylePresets);

  if (error) {
    return (
      <FieldShell label={label}>
        <p className="text-xs text-zinc-500">
          Style catalog unavailable ({error}). The render will fall back to the
          template default.
        </p>
      </FieldShell>
    );
  }
  if (!data) {
    return <FieldShell label={label}><Skeleton /></FieldShell>;
  }

  const active = data.find((p) => p.id === value);

  return (
    <FieldShell label={label}>
      <div className="flex flex-wrap gap-2">
        <Chip active={value === undefined} onClick={() => onChange(undefined)}>
          Auto
        </Chip>
        {data.map((p) => (
          <Chip
            key={p.id}
            active={value === p.id}
            onClick={() => onChange(p.id)}
            swatch={p.palette.primary}
            tone={value === p.id ? "active" : "muted"}
          >
            {p.name}
          </Chip>
        ))}
      </div>
      {active ? (
        <p className="mt-2 text-xs text-zinc-400">{active.render_notes || active.description}</p>
      ) : (
        <p className="mt-2 text-xs text-zinc-500">
          Auto picks a sensible default for the template — pick a style to
          steer the look.
        </p>
      )}
    </FieldShell>
  );
}


// ─── Pacing picker ───────────────────────────────────────────────────────

const _PACING_HINT: Record<string, string> = {
  calm:      "long holds, gentle camera",
  medium:    "balanced reveals",
  fast:      "punchy cuts",
  chaotic:   "high-energy, frequent cuts",
  cinematic: "slow drifts, longer beats",
};

export function PacingPicker({
  value, onChange, label = "Pacing",
}: {
  value: string | undefined;
  onChange: (id: string | undefined) => void;
  label?: string;
}) {
  const { data, error } = useCatalog<PacingMeta[]>("pacing", listPacingPresets);

  if (error) {
    return (
      <FieldShell label={label}>
        <p className="text-xs text-zinc-500">
          Pacing catalog unavailable ({error}); template default applies.
        </p>
      </FieldShell>
    );
  }
  if (!data) {
    return <FieldShell label={label}><Skeleton /></FieldShell>;
  }

  return (
    <FieldShell label={label}>
      <div className="flex flex-wrap gap-2">
        <Chip active={value === undefined} onClick={() => onChange(undefined)}>
          Default
        </Chip>
        {data.map((p) => (
          <Chip
            key={p.id}
            active={value === p.id}
            onClick={() => onChange(p.id)}
          >
            {p.label}
          </Chip>
        ))}
      </div>
      {value ? (
        <p className="mt-2 text-xs text-zinc-400">
          {_PACING_HINT[value] ?? "—"}
        </p>
      ) : null}
    </FieldShell>
  );
}


// ─── Voice picker (category-grouped) ─────────────────────────────────────

export function VoicePicker({
  value, onChange, label = "Voice",
}: {
  value: string | undefined;
  onChange: (id: string | undefined) => void;
  label?: string;
}) {
  const cats = useCatalog<VoiceCategory[]>("voiceCategories", listVoiceCategories);
  const voices = useCatalog<VoiceInfo[]>("voices", listVoices);

  if (cats.error || voices.error) {
    return (
      <FieldShell label={label}>
        <p className="text-xs text-zinc-500">
          Voice catalog unavailable; the worker will use the default.
        </p>
      </FieldShell>
    );
  }
  if (!cats.data || !voices.data) {
    return <FieldShell label={label}><Skeleton /></FieldShell>;
  }

  return (
    <FieldShell label={label}>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || undefined)}
        className="w-full rounded-md border border-zinc-800 bg-zinc-950 p-2 text-sm text-zinc-100"
      >
        <option value="">Auto (template default)</option>
        {cats.data.map((cat) => {
          const inCat = voices.data!.filter((v) => cat.voice_ids.includes(v.id));
          if (inCat.length === 0) return null;
          return (
            <optgroup key={cat.id} label={cat.label}>
              {inCat.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name} · {v.language}
                  {v.tone && v.tone.length ? ` — ${v.tone.join(", ")}` : ""}
                </option>
              ))}
            </optgroup>
          );
        })}
      </select>
    </FieldShell>
  );
}


// ─── Caption language picker ─────────────────────────────────────────────

export function CaptionLanguagePicker({
  value, onChange, label = "Caption language",
}: {
  value: string | undefined;
  onChange: (code: string | undefined) => void;
  label?: string;
}) {
  const { data, error } = useCatalog<CaptionLanguage[]>("languages", listCaptionLanguages);

  if (error) {
    return (
      <FieldShell label={label}>
        <p className="text-xs text-zinc-500">
          Language list unavailable ({error}); captions render in English.
        </p>
      </FieldShell>
    );
  }
  if (!data) {
    return <FieldShell label={label}><Skeleton /></FieldShell>;
  }

  return (
    <FieldShell label={label}>
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || undefined)}
        className="w-full rounded-md border border-zinc-800 bg-zinc-950 p-2 text-sm text-zinc-100"
      >
        <option value="">Auto (English)</option>
        {data.map((l) => (
          <option key={l.code} value={l.code}>
            {l.name} ({l.native}){l.rtl ? " · RTL" : ""}
          </option>
        ))}
      </select>
    </FieldShell>
  );
}


// ─── Caption style picker (string list, deprecated when style preset picks one) ─

const _CAPTION_STYLE_LABELS: Record<string, string> = {
  bold_word:           "Bold word",
  kinetic_word:        "Kinetic word",
  clean_subtitle:      "Clean subtitle",
  impact_uppercase:    "Impact UPPERCASE",
  minimal_lower_third: "Minimal lower-third",
  karaoke_3word:       "Karaoke 3-word",
};

export function CaptionStylePicker({
  value,
  onChange,
  label = "Caption style",
  styles = [
    "bold_word",
    "kinetic_word",
    "clean_subtitle",
    "impact_uppercase",
    "minimal_lower_third",
    "karaoke_3word",
  ],
}: {
  value: string | undefined;
  onChange: (id: string | undefined) => void;
  label?: string;
  styles?: readonly string[];
}) {
  return (
    <FieldShell label={label}>
      <div className="flex flex-wrap gap-2">
        <Chip active={value === undefined} onClick={() => onChange(undefined)}>
          Auto
        </Chip>
        {styles.map((s) => (
          <Chip
            key={s}
            active={value === s}
            onClick={() => onChange(s)}
          >
            {_CAPTION_STYLE_LABELS[s] ?? s}
          </Chip>
        ))}
      </div>
    </FieldShell>
  );
}


// ─── Shared shell + chip primitives ─────────────────────────────────────

function FieldShell({
  label, children,
}: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
        {label}
      </div>
      {children}
    </div>
  );
}


function Chip({
  active, onClick, children, swatch, tone = "muted",
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  swatch?: string;
  tone?: "muted" | "active";
}) {
  void tone;
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition " +
        (active
          ? "border-blue-500 bg-blue-600/20 text-blue-100"
          : "border-zinc-800 bg-zinc-950/50 text-zinc-300 hover:border-blue-700 hover:bg-zinc-900")
      }
    >
      {swatch ? (
        <span
          className="h-2.5 w-2.5 rounded-full"
          style={{ backgroundColor: swatch }}
          aria-hidden
        />
      ) : null}
      {children}
    </button>
  );
}


function Skeleton() {
  return (
    <div className="h-9 w-full animate-pulse rounded-md border border-zinc-800 bg-zinc-900/40" />
  );
}
