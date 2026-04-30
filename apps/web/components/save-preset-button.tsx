"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createSavedPrompt } from "@/lib/api";


/** Phase 9 / 12 — saves the current project's template + template_input
 * as a reusable preset. Shown on the project page header so the operator
 * can stamp out variations later without re-typing the form.
 *
 * The button toggles into an inline label input + confirm; we intentionally
 * don't open a modal to keep the action lightweight (this is a power-user
 * shortcut, not a primary flow).
 */
export function SavePresetButton({
  template,
  templateInput,
  defaultLabel,
}: {
  template: string;
  templateInput: Record<string, unknown>;
  defaultLabel: string;
}) {
  const { getToken } = useAuth();
  const [open, setOpen] = useState(false);
  const [label, setLabel] = useState(defaultLabel || "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSave = async () => {
    if (!label.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      await createSavedPrompt(
        {
          template,
          label: label.trim(),
          template_input: templateInput,
        },
        token,
      );
      setSaved(true);
      setOpen(false);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "save failed");
    } finally {
      setSaving(false);
    }
  };

  if (open) {
    return (
      <div className="flex items-center gap-2">
        <Input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Preset label"
          className="h-9 w-56"
          autoFocus
        />
        <Button
          size="sm"
          onClick={onSave}
          disabled={saving || !label.trim()}
        >
          {saving ? "Saving…" : "Save"}
        </Button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-xs text-zinc-500 hover:text-zinc-300"
        >
          cancel
        </button>
        {error ? (
          <span className="text-xs text-red-300">{error}</span>
        ) : null}
      </div>
    );
  }

  return (
    <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
      {saved ? "✓ Saved" : "★ Save as preset"}
    </Button>
  );
}
