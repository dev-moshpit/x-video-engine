"""Publishing helpers — Phase 7.

Generates title / description / hashtags + export-metadata for a
project so the operator can copy-paste into TikTok, Reels, or Shorts
without re-typing the same boilerplate every time.

Pure-function heuristics — no LLM call, no extra deps. The signal we
already have is rich enough:

  - the project's ``template_input`` (script / prompt / messages /
    items / question / etc.)
  - the latest VideoPlan (when the template produces one)
  - a template-aware base hashtag set so each template lands in the
    right For-You-Page lane (chat → #fakemessages, rant → #roblox …)

When the operator wants a different angle (longer descriptor, snarkier
title), they can ask Phase 4's recommendation surface for help — this
module's job is to ship a reasonable default.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Project, Render, VideoPlan


# ─── Per-template hashtag baselines ─────────────────────────────────────

_TEMPLATE_TAGS: dict[str, list[str]] = {
    "ai_story": ["aishorts", "aistory", "viralvideo", "shorts"],
    "reddit_story": ["redditstories", "askreddit", "storytime", "shorts"],
    "voiceover": ["voiceover", "shorts"],
    "auto_captions": ["captions", "subtitles", "shorts"],
    "fake_text": ["fakemessages", "textstory", "drama", "shorts"],
    "would_you_rather": ["wouldyourather", "wyr", "poll", "shorts"],
    "split_video": ["satisfying", "subwaysurfers", "asmr", "shorts"],
    "twitter": ["twitter", "tweet", "x", "shorts"],
    "top_five": ["top5", "countdown", "viralvideo", "shorts"],
    "roblox_rant": ["roblox", "rant", "gameplay", "shorts"],
}

_TITLE_FALLBACK = {
    "fake_text": "🚨 You won't believe these messages",
    "would_you_rather": "Would you rather…",
    "split_video": "Wait for it…",
    "twitter": "Tweet of the day",
    "top_five": "Top 5 you didn't know",
    "roblox_rant": "Why I'm DONE with this game",
    "voiceover": "Listen to this",
    "auto_captions": "Read this all the way through",
}


_STOPWORDS = {
    "the", "and", "or", "of", "in", "to", "for", "on", "at", "with",
    "is", "are", "was", "were", "be", "been", "by", "an", "a", "as",
    "this", "that", "it", "its", "their", "they", "you", "your", "i",
    "we", "us", "our", "but", "so", "if", "then", "than", "from",
    "can", "could", "would", "should", "do", "did", "have", "has",
    "had", "not", "no", "yes", "what", "when", "where", "who", "why",
    "how", "all", "any", "some", "more", "most", "other", "such",
    "only", "own", "same", "very", "out", "up", "down", "into", "over",
    "about", "just", "like", "also", "make", "made", "really", "well",
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z']+")


def _extract_keywords(text: str, *, max_n: int = 6) -> list[str]:
    """Return the most-frequent meaningful tokens from ``text``."""
    if not text:
        return []
    counts: Counter[str] = Counter()
    for w in _WORD_RE.findall(text.lower()):
        if len(w) <= 3 or w in _STOPWORDS:
            continue
        counts[w] += 1
    return [w for w, _ in counts.most_common(max_n)]


def _project_text_blob(project: Project) -> str:
    """Concatenate the user-authored text fields from template_input."""
    ti = project.template_input or {}
    parts: list[str] = []
    for key in (
        "prompt", "script", "body", "title", "question",
        "option_a", "option_b", "text", "chat_title",
    ):
        v = ti.get(key)
        if isinstance(v, str):
            parts.append(v)
    # Structured entries — flatten the text parts.
    for v in ti.get("messages", []) or []:
        if isinstance(v, dict) and isinstance(v.get("text"), str):
            parts.append(v["text"])
    for v in ti.get("items", []) or []:
        if isinstance(v, dict):
            if isinstance(v.get("title"), str):
                parts.append(v["title"])
            if isinstance(v.get("description"), str):
                parts.append(v["description"])
    return " ".join(parts)


def _latest_completed_plan(
    db: Session, project_id: uuid.UUID,
) -> Optional[dict]:
    """Most recent VideoPlan dict attached to a completed render, if any."""
    row = db.execute(
        select(VideoPlan)
        .join(Render, Render.id == VideoPlan.render_id)
        .where(Render.project_id == project_id)
        .where(Render.stage == "complete")
        .order_by(Render.completed_at.desc().nullslast())
    ).scalars().first()
    return row.plan_json if row else None


# ─── Public surface ─────────────────────────────────────────────────────

def generate_publish_metadata(
    db: Session, project: Project,
) -> dict:
    """Return ``{title, description, hashtags, alternates}`` for ``project``.

    ``alternates`` is a list of 2-3 alternative titles so the operator
    can pick a vibe (curiosity gap, listicle, direct).
    """
    ti = project.template_input or {}
    blob = _project_text_blob(project)
    keywords = _extract_keywords(blob, max_n=8)

    plan = _latest_completed_plan(db, project.id)

    # Title: prefer plan.title, fall back to a template-specific stinger
    # combined with the first sentence of the user's text.
    if plan and isinstance(plan.get("title"), str) and plan["title"].strip():
        title = plan["title"].strip()
    else:
        first_sentence = re.split(r"[.!?\n]", blob.strip(), maxsplit=1)[0][:80]
        title = first_sentence or _TITLE_FALLBACK.get(project.template, project.name)

    # Description: plan.hook + cta, or constructed from script + cta.
    if plan and isinstance(plan.get("hook"), str):
        desc_parts = [plan["hook"].strip()]
        cta = plan.get("cta")
        if isinstance(cta, str) and cta.strip():
            desc_parts.append(cta.strip())
        description = " ".join(desc_parts)
    else:
        # Take the first ~280 chars and append a soft CTA.
        snippet = blob.strip().replace("\n", " ")
        if len(snippet) > 280:
            snippet = snippet[:277].rstrip() + "…"
        description = snippet or project.name
        description += " Follow for more 🎬"

    # Hashtags: template baseline + extracted keywords (max 12).
    base = list(_TEMPLATE_TAGS.get(project.template, ["shorts"]))
    seen = set(base)
    for k in keywords:
        if len(base) >= 12:
            break
        if k not in seen:
            base.append(k)
            seen.add(k)
    hashtags = [f"#{t}" for t in base[:12]]

    # Alternate titles for vibe-shopping.
    alternates: list[str] = []
    if title and not title.startswith("🚨"):
        alternates.append(f"🚨 {title}")
    listicle = next(
        (s for s in [_TITLE_FALLBACK.get(project.template)] if s),
        None,
    )
    if listicle and listicle != title:
        alternates.append(listicle)
    if keywords:
        alternates.append(
            f"The truth about {keywords[0]} (no one tells you this)"
        )
    # De-dup and trim.
    alternates = [a for a in alternates if a and a != title][:3]

    return {
        "title": title[:120],
        "description": description[:1500],
        "hashtags": hashtags,
        "alternates": alternates,
    }
