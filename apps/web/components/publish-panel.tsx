"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { getPublishMetadata, type PublishMetadata } from "@/lib/api";


/** Phase 7 — copy/paste-ready title, description, hashtags, plus 2-3
 * alternative title vibes. Renders only when the parent passes a
 * completed render's URL — no point generating publish copy for a
 * project that hasn't produced an MP4 yet.
 *
 * The user picks the title vibe they like, edits in place, then hits
 * a small Copy button per field. We don't auto-post anywhere yet
 * (Phase 7+ will add scheduled posting); the operator handles the
 * upload step manually for now. */
export function PublishPanel({
  projectId, finalMp4Url,
}: {
  projectId: string;
  finalMp4Url: string;
}) {
  const { getToken } = useAuth();
  const [meta, setMeta] = useState<PublishMetadata | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Local edits — let the operator tweak the suggested copy.
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [hashtags, setHashtags] = useState("");

  const fetchMeta = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) throw new Error("not signed in");
      const m = await getPublishMetadata(projectId, token);
      setMeta(m);
      setTitle(m.title);
      setDescription(m.description);
      setHashtags(m.hashtags.join(" "));
    } catch (e) {
      setError(e instanceof Error ? e.message : "load failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMeta();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const copy = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Publish</CardTitle>
          <Button variant="outline" onClick={fetchMeta} disabled={loading}>
            {loading ? "Generating…" : "Re-generate"}
          </Button>
        </div>
        <CardDescription>
          Suggested title, description, and hashtags for TikTok / Reels /
          Shorts. Tweak in-place, then copy and paste when uploading.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {error ? (
          <div className="rounded-md border border-red-900 bg-red-950/30 p-3 text-xs text-red-200">
            {error}
          </div>
        ) : null}

        <div className="grid gap-2">
          <div className="flex items-center justify-between">
            <Label>Title</Label>
            <button
              type="button"
              onClick={() => copy(title)}
              className="text-xs text-zinc-400 hover:text-zinc-100"
            >
              copy
            </button>
          </div>
          <Textarea
            rows={2}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={120}
          />
          {meta && meta.alternates.length > 0 ? (
            <div className="flex flex-wrap gap-2 text-xs">
              {meta.alternates.map((alt) => (
                <button
                  key={alt}
                  type="button"
                  onClick={() => setTitle(alt)}
                  className="rounded-md border border-zinc-800 bg-zinc-950/50 px-2 py-1 text-zinc-400 hover:border-blue-700 hover:text-zinc-100"
                  title="Use this alternate title"
                >
                  {alt}
                </button>
              ))}
            </div>
          ) : null}
        </div>

        <div className="grid gap-2">
          <div className="flex items-center justify-between">
            <Label>Description</Label>
            <button
              type="button"
              onClick={() => copy(description)}
              className="text-xs text-zinc-400 hover:text-zinc-100"
            >
              copy
            </button>
          </div>
          <Textarea
            rows={4}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={1500}
          />
        </div>

        <div className="grid gap-2">
          <div className="flex items-center justify-between">
            <Label>Hashtags</Label>
            <button
              type="button"
              onClick={() => copy(hashtags)}
              className="text-xs text-zinc-400 hover:text-zinc-100"
            >
              copy
            </button>
          </div>
          <Textarea
            rows={2}
            value={hashtags}
            onChange={(e) => setHashtags(e.target.value)}
          />
        </div>

        <div className="grid gap-2">
          <Label>Export metadata (JSON for batch tools)</Label>
          <Textarea
            rows={6}
            readOnly
            className="font-mono text-xs"
            value={JSON.stringify(
              {
                title,
                description,
                hashtags: hashtags
                  .split(/\s+/)
                  .map((h) => h.trim())
                  .filter(Boolean),
                video_url: finalMp4Url,
              },
              null,
              2,
            )}
          />
          <button
            type="button"
            onClick={() =>
              copy(
                JSON.stringify(
                  {
                    title,
                    description,
                    hashtags: hashtags
                      .split(/\s+/)
                      .map((h) => h.trim())
                      .filter(Boolean),
                    video_url: finalMp4Url,
                  },
                  null,
                  2,
                ),
              )
            }
            className="self-start rounded-md border border-zinc-800 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-900"
          >
            Copy JSON
          </button>
        </div>
      </CardContent>
    </Card>
  );
}
