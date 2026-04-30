"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { MediaPickerButton } from "@/components/media-picker";
import { updateProject } from "@/lib/api";


/* Lightweight editor — NOT a timeline.
 *
 * Exposes the high-value, most-iterated fields for each template:
 *
 *   - script / prompt (the wording itself)
 *   - caption_style + voice_name (style/voice swap)
 *   - background_url (replace the bg)
 *
 * Other fields (duration, aspect, advanced flags) are deliberately
 * left untouched — those usually don't change between iterations and
 * are still editable by recreating the project from /create. The
 * editor PATCHes /api/projects/:id; the existing PATCH route already
 * validates against the template schema so we don't re-implement
 * Pydantic on the frontend.
 */

const CAPTION_STYLES = [
  "bold_word",
  "kinetic_word",
  "clean_subtitle",
  "impact_uppercase",
  "minimal_lower_third",
  "karaoke_3word",
] as const;


type Template = string;

type TemplateInput = Record<string, unknown>;

const SCRIPT_FIELD: Record<Template, string | null> = {
  ai_story: "prompt",
  reddit_story: "body",
  voiceover: "script",
  auto_captions: "script",
  fake_text: null,            // structured messages — use /create instead
  would_you_rather: "question",
  split_video: "script",
  twitter: "text",
  top_five: null,             // list of items — use /create instead
  roblox_rant: "script",
};

const BG_URL_FIELD: Record<Template, string | null> = {
  ai_story: null,
  reddit_story: null,
  voiceover: "background_url",
  auto_captions: "video_url",
  fake_text: "background_url",
  would_you_rather: "background_url",
  split_video: "main_url",
  twitter: "background_url",
  top_five: "background_url",
  roblox_rant: "background_url",
};


export function ProjectEditor({
  projectId,
  template,
  initialInput,
  onSaved,
}: {
  projectId: string;
  template: Template;
  initialInput: TemplateInput;
  onSaved: (next: TemplateInput) => void;
}) {
  const { getToken } = useAuth();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState<TemplateInput>(initialInput);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scriptField = SCRIPT_FIELD[template] ?? null;
  const bgUrlField = BG_URL_FIELD[template] ?? null;

  const setField = (key: string, value: unknown) => {
    setInput((prev) => {
      const next = { ...prev };
      if (value === "" || value === null) {
        delete next[key];
      } else {
        next[key] = value;
      }
      return next;
    });
  };

  const onSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const updated = await updateProject(
        projectId, { template_input: input }, token,
      );
      onSaved(updated.template_input as TemplateInput);
      setOpen(false);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "save failed";
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <Button variant="outline" onClick={() => setOpen(true)}>
        Edit inputs
      </Button>
    );
  }

  return (
    <div className="space-y-4 rounded-md border border-zinc-800 bg-zinc-950/40 p-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium text-zinc-200">Edit inputs</div>
        <button
          type="button"
          onClick={() => {
            setInput(initialInput);
            setOpen(false);
            setError(null);
          }}
          className="text-xs text-zinc-400 hover:text-zinc-100"
        >
          cancel
        </button>
      </div>

      {scriptField ? (
        <div className="grid gap-2">
          <Label>{scriptField}</Label>
          <Textarea
            rows={6}
            value={(input[scriptField] as string) ?? ""}
            onChange={(e) => setField(scriptField, e.target.value)}
          />
        </div>
      ) : (
        <p className="rounded-md border border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-400">
          This template has structured inputs (a list of messages or items).
          Use the JSON editor below to adjust them, or recreate the project
          from <code>/create/{template}</code>.
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="grid gap-2">
          <Label>Caption style</Label>
          <select
            value={(input.caption_style as string) ?? ""}
            onChange={(e) => setField("caption_style", e.target.value || null)}
            className="h-9 rounded-md border border-zinc-800 bg-zinc-950 px-2 text-sm"
          >
            <option value="">(template default)</option>
            {CAPTION_STYLES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div className="grid gap-2">
          <Label>Voice</Label>
          <Input
            placeholder="en-US-AriaNeural"
            value={(input.voice_name as string) ?? ""}
            onChange={(e) => setField("voice_name", e.target.value)}
          />
        </div>
      </div>

      {bgUrlField ? (
        <div className="grid gap-2">
          <Label>{bgUrlField}</Label>
          <div className="flex gap-2">
            <Input
              placeholder="https://… or pick from library"
              value={(input[bgUrlField] as string) ?? ""}
              onChange={(e) => setField(bgUrlField, e.target.value)}
              className="flex-1"
            />
            <MediaPickerButton
              kind="video"
              label="Pick"
              onPick={(url) => setField(bgUrlField, url)}
            />
          </div>
        </div>
      ) : null}

      <details>
        <summary className="cursor-pointer text-xs text-zinc-400 hover:text-zinc-200">
          Edit raw JSON
        </summary>
        <Textarea
          rows={10}
          value={JSON.stringify(input, null, 2)}
          onChange={(e) => {
            try {
              setInput(JSON.parse(e.target.value));
              setError(null);
            } catch {
              setError("Invalid JSON — keep typing or fix syntax");
            }
          }}
          className="mt-2 font-mono text-xs"
        />
      </details>

      {error ? (
        <div className="rounded-md border border-red-900 bg-red-950/30 p-3 text-xs text-red-200">
          {error}
        </div>
      ) : null}

      <div className="flex items-center gap-3">
        <Button onClick={onSave} disabled={saving}>
          {saving ? "Saving…" : "Save & re-render below"}
        </Button>
        <span className="text-xs text-zinc-500">
          Saving updates the inputs; click <strong>Render</strong> to start a
          fresh render with the new inputs.
        </span>
      </div>
    </div>
  );
}
