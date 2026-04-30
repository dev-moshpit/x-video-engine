"""Prompt -> pack rows.

Converts a natural-language operator prompt like:

    "Make 10 motivational videos about discipline, pain, and comeback.
     Style should be intense and cinematic."

into a list of rows in a pack's CSV schema (the same schema `run_shorts_batch.py
--pack X --csv Y.csv` consumes). Everything downstream — batch runner, gallery,
selection export, final render — is untouched.

Architecture principle: prompt mode generates *pack rows*, not final prompts.
The pack's own row_transformer + style guards + publish templates still own
how those rows become rendered clips.

MVP: deterministic, no LLM. Future `--planner llm` can slot in by replacing
`plan_from_prompt` while keeping the return shape identical.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

# ─── Pack routing ───────────────────────────────────────────────────────

# Keyword -> list of packs that get +1. Score the user prompt against every
# pack's keyword bank; highest score wins (tie-break by declaration order).
PACK_KEYWORDS: dict[str, list[str]] = {
    "motivational_quotes": [
        "motivation", "motivational", "mindset", "discipline", "grind",
        "growth", "success", "purpose", "resilience", "comeback", "win",
        "grit", "self-improvement", "quote", "quotes", "wolf", "phoenix",
        "warrior", "hustle", "focus", "pain", "struggle", "rise", "peak",
    ],
    "ai_facts": [
        "ai", "artificial intelligence", "gpu", "robot", "neural", "algorithm",
        "machine learning", "llm", "data", "tech", "future", "computer",
        "automation", "model", "deep learning", "silicon", "chip",
    ],
    "history_mystery": [
        "mystery", "mysteries", "ancient", "unsolved", "vanished", "lost",
        "eerie", "conspiracy", "dark history", "forgotten", "cold case",
        "paranormal", "cursed", "haunted", "cover-up", "relic", "ruins",
    ],
    "product_teaser": [
        "product", "ad", "ads", "launch", "brand", "commercial", "promo",
        "teaser", "reveal", "drop", "store", "marketing", "e-commerce",
        "watch", "sneaker", "headphones", "gadget", "saas",
    ],
    "music_visualizer": [
        "music", "beat", "beats", "visualizer", "edm", "lofi", "lo-fi",
        "dj", "audio", "track", "tunnel", "neon grid", "pulse", "rhythm",
        "synthwave", "rave",
    ],
    "abstract_loop": [
        "aesthetic", "pastel", "loop", "loops", "abstract", "ambient",
        "vibe", "vibes", "mood", "dreamy", "filler", "background",
        "backdrop", "chill", "minimal",
    ],
}


def route_pack(user_prompt: str) -> tuple[str, dict[str, int]]:
    """Return (best_pack, scores). Ties broken by declaration order."""
    text = user_prompt.lower()
    scores: dict[str, int] = {}
    for pack, kws in PACK_KEYWORDS.items():
        score = 0
        for kw in kws:
            # word-boundary match for single words; substring match for multi
            if " " in kw:
                if kw in text:
                    score += 1
            else:
                if re.search(rf"\b{re.escape(kw)}\b", text):
                    score += 1
        scores[pack] = score
    best = max(PACK_KEYWORDS.keys(), key=lambda p: (scores[p], -list(PACK_KEYWORDS).index(p)))
    return best, scores


# ─── Style cue extraction ───────────────────────────────────────────────

# Per-pack: style words in prompt -> a value in the pack's relevant table.
# When the operator says "intense cinematic", we pick "fierce" for
# motivational_quotes, "bold" for product_teaser, "cautionary" for ai_facts…
PACK_STYLE_MAP: dict[str, dict[str, list[str]]] = {
    "motivational_quotes": {
        # tone value -> cue words
        "fierce":      ["intense", "fierce", "aggressive", "hard", "dark", "brutal", "grind", "pain", "raw"],
        "triumphant":  ["triumphant", "comeback", "rising", "peak", "win", "success", "victory", "epic"],
        "reflective":  ["reflective", "calm", "mindful", "thoughtful", "peaceful", "quiet", "introspective"],
        "peaceful":    ["peaceful", "serene", "gentle", "soft", "tranquil"],
        "grateful":    ["grateful", "gratitude", "thankful", "appreciation"],
        "resilient":   ["resilient", "resilience", "strong", "bounce back", "withstand"],
    },
    "ai_facts": {
        "mind-blowing": ["mind-blowing", "crazy", "wild", "shocking", "insane"],
        "wholesome":    ["wholesome", "friendly", "hopeful", "warm"],
        "cautionary":   ["cautionary", "dark", "ominous", "warning", "dystopian", "cinematic"],
        "curious":      ["curious", "interesting", "fun", "weird"],
        "future":       ["future", "futuristic", "tomorrow", "2030", "forward"],
        "historical":   ["historical", "history", "origin", "past", "retro"],
    },
    "history_mystery": {
        "unsolved":          ["unsolved", "mystery", "no one knows"],
        "forgotten":         ["forgotten", "lost", "ancient", "ruins"],
        "conspiracy":        ["conspiracy", "cover-up", "coverup", "hidden"],
        "lost_civilization": ["lost civilization", "civilization", "empire"],
        "eerie":             ["eerie", "creepy", "dark", "unsettling", "ominous"],
        "cover_up":          ["cover-up", "coverup", "classified"],
        "haunted":           ["haunted", "ghost", "spirit", "paranormal"],
    },
    "product_teaser": {
        "elegant":   ["elegant", "refined", "graceful"],
        "bold":      ["bold", "loud", "dramatic", "intense", "strong"],
        "playful":   ["playful", "fun", "bright", "happy"],
        "premium":   ["premium", "luxury", "high-end", "exclusive"],
        "clean":     ["clean", "minimal", "simple", "quiet"],
        "cinematic": ["cinematic", "filmic", "dramatic", "epic", "moody"],
    },
    "music_visualizer": {
        "dreamy":      ["dreamy", "soft", "ambient", "calm"],
        "sharp":       ["sharp", "synthwave", "hard", "cutting"],
        "driving":     ["driving", "intense", "fast", "edm", "dance"],
        "melancholic": ["melancholic", "sad", "slow", "lofi", "lo-fi"],
        "euphoric":    ["euphoric", "high", "peak", "ecstatic"],
    },
    "abstract_loop": {
        "dreamy":      ["dreamy", "soft", "pastel"],
        "sharp":       ["sharp", "neon", "hard"],
        "serene":      ["serene", "calm", "quiet", "still"],
        "ethereal":    ["ethereal", "glowing", "luminous"],
        "rhythmic":    ["rhythmic", "pulse", "rhythm"],
        "chaotic":     ["chaotic", "busy", "wild"],
        "melancholic": ["melancholic", "sad", "cool"],
    },
}


def extract_style(pack: str, user_prompt: str) -> str | None:
    """Return the pack-specific table value best matching the prompt's style
    cues, or None if nothing matched."""
    text = user_prompt.lower()
    best_val, best_hits = None, 0
    for val, cues in PACK_STYLE_MAP.get(pack, {}).items():
        hits = sum(1 for c in cues if c in text)
        if hits > best_hits:
            best_val, best_hits = val, hits
    return best_val


# ─── Topic extraction ───────────────────────────────────────────────────

_FILLER_WORDS = {
    "make", "create", "generate", "produce", "build", "videos", "video",
    "shorts", "short", "reels", "reel", "tiktoks", "tiktok", "clips",
    "clip", "about", "on", "the", "a", "an", "of", "for", "with", "and",
    "or", "to", "this", "that", "please", "use", "style", "should", "be",
    "quotes", "quote",
}


def extract_topics(user_prompt: str, max_topics: int = 20) -> list[str]:
    """Pull likely topic phrases out of a prompt.

    Strategy: split on sentence-final punctuation first, then split the
    segments that look like topic lists on commas / 'and' / 'or' / ';'.
    Drop filler words from single-word topics.
    """
    topics: list[str] = []
    # Find the "about ..." fragment if present; it's the most reliable topic list
    m = re.search(r"\babout\s+([^.!\n]+)", user_prompt, re.IGNORECASE)
    if m:
        frag = m.group(1)
        parts = re.split(r",|\band\b|\bor\b|;", frag, flags=re.IGNORECASE)
        topics = [p.strip(" .:") for p in parts if p.strip(" .:")]

    if not topics:
        # Fall back: try splitting the whole prompt and filter filler words
        parts = re.split(r",|\band\b|\bor\b|;|\n", user_prompt, flags=re.IGNORECASE)
        for p in parts:
            p = p.strip(" .:")
            # Keep phrases that have >= 1 non-filler word
            if p and any(
                w.lower() not in _FILLER_WORDS
                for w in re.findall(r"\w+", p)
            ):
                topics.append(p)

    # De-dupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for t in topics:
        key = t.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(t)
    return out[:max_topics]


# ─── Per-pack topic libraries ───────────────────────────────────────────
# Hand-curated seed pool. When the prompt mentions a known topic we lift
# the (quote, tone, visual_subject) triplet; otherwise we synthesize a
# generic row from the topic phrase. Tone from PACK_STYLE_MAP still wins
# if the operator specified a style.

MOTIVATIONAL_TOPIC_LIB: dict[str, dict] = {
    "discipline":    {"quote": "Discipline is freedom.",           "tone": "fierce",     "visual_subject": "a geometric lone wolf walking through dark mountains"},
    "pain":          {"quote": "The only way out is through.",     "tone": "fierce",     "visual_subject": "a figure pushing forward through heavy wind and rain"},
    "struggle":      {"quote": "The climb is the reward.",         "tone": "resilient",  "visual_subject": "a figure scaling a sheer rock face"},
    "comeback":      {"quote": "Your comeback starts now.",        "tone": "triumphant", "visual_subject": "a geometric phoenix rising from shattered stone"},
    "success":       {"quote": "Your moment is now.",              "tone": "triumphant", "visual_subject": "a lone figure at the summit, arms open"},
    "grind":         {"quote": "Outwork everyone.",                "tone": "fierce",     "visual_subject": "a runner pushing uphill at dawn"},
    "purpose":       {"quote": "Do it on purpose.",                "tone": "reflective", "visual_subject": "a single path cutting through a quiet forest"},
    "resilience":    {"quote": "Bend. Don't break.",               "tone": "resilient",  "visual_subject": "a lone tree bowing in heavy wind"},
    "focus":         {"quote": "Eyes forward. Always.",            "tone": "fierce",     "visual_subject": "a hawk staring toward the horizon"},
    "growth":        {"quote": "Small steps every day.",           "tone": "reflective", "visual_subject": "a figure on a mountain path at sunrise"},
    "courage":       {"quote": "Do it scared.",                    "tone": "fierce",     "visual_subject": "a warrior stepping into stormlight"},
    "gratitude":     {"quote": "Gratitude changes everything.",    "tone": "grateful",   "visual_subject": "a figure watching a warm sunrise over hills"},
    "peace":         {"quote": "Stillness is strength.",           "tone": "peaceful",   "visual_subject": "a small boat on calm water"},
    "rise":          {"quote": "Rise, and rise again.",            "tone": "triumphant", "visual_subject": "a phoenix emerging from pale light"},
    "fear":          {"quote": "Fear is the compass.",             "tone": "fierce",     "visual_subject": "a figure facing an approaching storm"},
    "mindset":       {"quote": "Your mindset is your edge.",       "tone": "fierce",     "visual_subject": "a geometric crown on a stone pedestal"},
}

AI_FACTS_TOPIC_LIB: dict[str, dict] = {
    "gpu":           {"angle": "future",       "visual_subject": "glowing interconnected neon circuits"},
    "neural":        {"angle": "mind-blowing", "visual_subject": "a complex web of glowing nodes"},
    "robot":         {"angle": "cautionary",   "visual_subject": "a faceted robot silhouette in dark space"},
    "ai":            {"angle": "future",       "visual_subject": "a glowing abstract brain made of geometry"},
    "llm":           {"angle": "mind-blowing", "visual_subject": "cascading glowing text threads"},
    "future":        {"angle": "future",       "visual_subject": "a geometric cityscape at dawn"},
    "algorithm":     {"angle": "curious",      "visual_subject": "interlocking rotating gears of light"},
    "data":          {"angle": "mind-blowing", "visual_subject": "a flowing river of glowing data points"},
    "automation":    {"angle": "cautionary",   "visual_subject": "a factory of geometric arms in motion"},
}

HISTORY_MYSTERY_TOPIC_LIB: dict[str, dict] = {
    "dyatlov":       {"mystery_angle": "unsolved",          "visual_subject": "a snowy silhouette with a single tent"},
    "roanoke":       {"mystery_angle": "forgotten",         "visual_subject": "a geometric fort ruin in morning mist"},
    "nazca":         {"mystery_angle": "lost_civilization", "visual_subject": "ancient patterns carved in desert"},
    "bermuda":       {"mystery_angle": "eerie",             "visual_subject": "a lone ship under strange clouds"},
    "area 51":       {"mystery_angle": "cover_up",          "visual_subject": "a desert bunker at dusk"},
    "pyramid":       {"mystery_angle": "lost_civilization", "visual_subject": "a geometric pyramid under harsh sun"},
    "atlantis":      {"mystery_angle": "lost_civilization", "visual_subject": "sunken columns in blue-green water"},
}

PRODUCT_TEASER_TOPIC_LIB: dict[str, dict] = {
    "watch":         {"category": "luxury",   "vibe": "premium",   "visual_subject": "a geometric watch floating on a dark pedestal"},
    "sneaker":       {"category": "fashion",  "vibe": "playful",   "visual_subject": "a faceted sneaker spinning in bright space"},
    "headphones":    {"category": "tech",     "vibe": "bold",      "visual_subject": "low-poly headphones emerging from mist"},
    "phone":         {"category": "tech",     "vibe": "clean",     "visual_subject": "a geometric phone rotating on a soft gradient"},
    "perfume":       {"category": "luxury",   "vibe": "elegant",   "visual_subject": "a geometric perfume bottle under spotlight"},
    "camera":        {"category": "gadget",   "vibe": "cinematic", "visual_subject": "a low-poly camera rotating with dramatic light"},
    "coffee":        {"category": "food",     "vibe": "playful",   "visual_subject": "a geometric coffee cup with steam"},
    "saas":          {"category": "saas",     "vibe": "clean",     "visual_subject": "a floating low-poly dashboard interface"},
}

MUSIC_VIS_TOPIC_LIB: dict[str, dict] = {
    "tunnel":        {"track_mood": "driving",     "energy": "high",   "color_bias": "neon", "visual_subject": "a neon tunnel rushing forward"},
    "crystal":       {"track_mood": "dreamy",      "energy": "low",    "color_bias": "pastel", "visual_subject": "floating faceted crystals in soft light"},
    "rain":          {"track_mood": "melancholic", "energy": "low",    "color_bias": "cool", "visual_subject": "geometric rain streaks over dark glass"},
    "sunrise":       {"track_mood": "euphoric",    "energy": "high",   "color_bias": "warm", "visual_subject": "geometric sun rays breaking over a ridge"},
    "grid":          {"track_mood": "sharp",       "energy": "medium", "color_bias": "neon", "visual_subject": "a neon grid pulsing to an unseen beat"},
}

ABSTRACT_LOOP_TOPIC_LIB: dict[str, dict] = {
    "drift":         {"mood": "dreamy",   "color_theme": "pastel", "visual_subject": "floating faceted crystals adrift"},
    "pulse":         {"mood": "sharp",    "color_theme": "neon",   "visual_subject": "a pulsing neon ring"},
    "stillness":     {"mood": "serene",   "color_theme": "mono",   "visual_subject": "a single geometric monolith under soft light"},
    "glow":          {"mood": "ethereal", "color_theme": "warm",   "visual_subject": "glowing faceted particles suspended"},
    "cycle":         {"mood": "rhythmic", "color_theme": "neon",   "visual_subject": "concentric neon rings looping"},
}

PACK_LIBRARIES: dict[str, dict[str, dict]] = {
    "motivational_quotes": MOTIVATIONAL_TOPIC_LIB,
    "ai_facts":            AI_FACTS_TOPIC_LIB,
    "history_mystery":     HISTORY_MYSTERY_TOPIC_LIB,
    "product_teaser":      PRODUCT_TEASER_TOPIC_LIB,
    "music_visualizer":    MUSIC_VIS_TOPIC_LIB,
    "abstract_loop":       ABSTRACT_LOOP_TOPIC_LIB,
}


def _match_library(pack: str, topic: str) -> dict | None:
    """Case-insensitive substring match of topic against pack library keys."""
    lib = PACK_LIBRARIES.get(pack, {})
    t = topic.lower()
    for key, entry in lib.items():
        if key in t:
            return entry
    return None


# ─── Row construction per pack ──────────────────────────────────────────

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(s: str, max_len: int = 24) -> str:
    out = _SLUG_RE.sub("_", s.lower()).strip("_")
    return out[:max_len] or "topic"


def _row_motivational(topic: str, style: str | None, seeds: str) -> dict:
    hit = _match_library("motivational_quotes", topic)
    tone = style or (hit.get("tone") if hit else "fierce")
    quote = hit["quote"] if hit else f"{topic.strip().capitalize()}."
    subject = hit["visual_subject"] if hit else f"a geometric scene of {topic}"
    return {
        "id": f"mq_{_slug(topic)}",
        "quote": quote, "tone": tone, "visual_subject": subject,
        "preset": "", "motion": "", "duration": "", "seeds": seeds,
    }


def _row_ai_facts(topic: str, style: str | None, seeds: str) -> dict:
    hit = _match_library("ai_facts", topic)
    angle = style or (hit.get("angle") if hit else "future")
    subject = hit["visual_subject"] if hit else f"a glowing geometric representation of {topic}"
    return {
        "id": f"ai_{_slug(topic)}",
        "topic": topic.strip(), "angle": angle, "visual_subject": subject,
        "preset": "", "motion": "", "duration": "", "seeds": seeds,
    }


def _row_history_mystery(topic: str, style: str | None, seeds: str) -> dict:
    hit = _match_library("history_mystery", topic)
    angle = style or (hit.get("mystery_angle") if hit else "unsolved")
    subject = hit["visual_subject"] if hit else f"a geometric scene evoking {topic}"
    return {
        "id": f"hm_{_slug(topic)}",
        "topic": topic.strip(), "mystery_angle": angle, "visual_subject": subject,
        "preset": "", "motion": "", "duration": "", "seeds": seeds,
    }


def _row_product_teaser(topic: str, style: str | None, seeds: str) -> dict:
    hit = _match_library("product_teaser", topic)
    category = hit.get("category") if hit else "gadget"
    vibe = style or (hit.get("vibe") if hit else "premium")
    subject = hit["visual_subject"] if hit else f"a low-poly {topic} on a pedestal"
    return {
        "id": f"pt_{_slug(topic)}",
        "product": topic.strip().title(), "category": category, "vibe": vibe,
        "visual_subject": subject,
        "preset": "", "motion": "", "duration": "", "seeds": seeds,
    }


def _row_music_visualizer(topic: str, style: str | None, seeds: str) -> dict:
    hit = _match_library("music_visualizer", topic)
    mood = style or (hit.get("track_mood") if hit else "driving")
    energy = hit.get("energy") if hit else "medium"
    color = hit.get("color_bias") if hit else "neon"
    subject = hit["visual_subject"] if hit else f"a geometric {topic} pulsing to an unseen beat"
    return {
        "id": f"mv_{_slug(topic)}",
        "track_mood": mood, "energy": energy, "color_bias": color,
        "visual_subject": subject,
        "preset": "", "motion": "", "duration": "", "seeds": seeds,
    }


def _row_abstract_loop(topic: str, style: str | None, seeds: str) -> dict:
    hit = _match_library("abstract_loop", topic)
    mood = style or (hit.get("mood") if hit else "dreamy")
    color = hit.get("color_theme") if hit else "pastel"
    subject = hit["visual_subject"] if hit else f"a soft geometric {topic}"
    return {
        "id": f"al_{_slug(topic)}",
        "mood": mood, "color_theme": color, "visual_subject": subject,
        "preset": "", "motion": "", "duration": "", "seeds": seeds,
    }


_ROW_BUILDERS = {
    "motivational_quotes": _row_motivational,
    "ai_facts":            _row_ai_facts,
    "history_mystery":     _row_history_mystery,
    "product_teaser":      _row_product_teaser,
    "music_visualizer":    _row_music_visualizer,
    "abstract_loop":       _row_abstract_loop,
}


# ─── Public API ─────────────────────────────────────────────────────────

@dataclass
class PlannerResult:
    pack: str
    rows: list[dict] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    style: str | None = None
    pack_scores: dict[str, int] = field(default_factory=dict)
    auto_routed: bool = False
    notes: list[str] = field(default_factory=list)


def plan_from_prompt(
    user_prompt: str,
    pack: str | None = None,
    count: int = 10,
    seeds: Iterable[int] = (42,),
) -> PlannerResult:
    """Generate `count` pack rows from a free-form operator prompt.

    Args:
        user_prompt: natural-language request
        pack: pack name, or None/"auto" to route by keyword score
        count: number of rows to produce
        seeds: seeds assigned to every row (as a comma-separated string)

    Returns:
        PlannerResult with the chosen pack, generated rows, and debug info.
    """
    if count <= 0:
        raise ValueError("count must be positive")

    auto = pack in (None, "", "auto")
    scores: dict[str, int] = {}
    if auto:
        pack, scores = route_pack(user_prompt)

    if pack not in _ROW_BUILDERS:
        raise ValueError(f"Unknown pack: {pack}. Valid: {list(_ROW_BUILDERS)}")

    style = extract_style(pack, user_prompt)
    topics = extract_topics(user_prompt)

    # If we have no topic hooks, fall back to packaging the whole prompt
    # as a single topic. This keeps the planner useful for terse prompts
    # ("make 5 dreamy abstract loops").
    if not topics:
        topics = [user_prompt.strip(" .?!,")[:60] or pack]

    seeds_str = ",".join(str(int(s)) for s in seeds) if seeds else "42"

    builder = _ROW_BUILDERS[pack]
    rows: list[dict] = []
    used_ids: set[str] = set()
    # Cycle topics until we hit `count`.
    i = 0
    attempts = 0
    while len(rows) < count and attempts < count * 4:
        topic = topics[i % len(topics)]
        row = builder(topic, style, seeds_str)
        # Suffix duplicate ids to keep them unique
        base_id = row["id"]
        suffix = 2
        while row["id"] in used_ids:
            row["id"] = f"{base_id}_{suffix:02d}"
            suffix += 1
        used_ids.add(row["id"])
        rows.append(row)
        i += 1
        attempts += 1

    notes: list[str] = []
    if auto:
        notes.append(f"auto-routed to pack `{pack}` (scores: "
                     + ", ".join(f"{p}={s}" for p, s in
                                  sorted(scores.items(), key=lambda x: -x[1])[:3])
                     + ")")
    if style:
        notes.append(f"style cue detected: `{style}`")
    else:
        notes.append("no style cue detected — using per-row defaults")
    notes.append(f"topics extracted: {topics}")

    return PlannerResult(
        pack=pack,
        rows=rows,
        topics=topics,
        style=style,
        pack_scores=scores,
        auto_routed=auto,
        notes=notes,
    )
