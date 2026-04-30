"""Prompt-native video director.

Primary generation path of the LowPoly Shorts Engine. Each call produces a
complete `VideoPlan` from a free-form user prompt — title, concept, hook,
scene plan, voiceover lines, captions, CTA, negative prompt, and the seed
provenance. The plan is the single source of truth that downstream stages
(batch render, voiceover, captions, ffmpeg compose) consume.

Contract:
    prompt → original creative brief → original script → original visual
    scenes → render jobs → voiceover → captions → final MP4

The same prompt produces a *different* `VideoPlan` every time unless an
explicit seed is supplied. Variation comes from a combinatorial concept
graph (archetype × setting × time × tension × resolution × camera lens),
not from keyword swaps in a single template.

This module has no LLM dependency. It is deterministic given a seed,
fast, side-effect free, and importable from CLI / Streamlit / tests.

Existing pack-routed workflow still works (xvideo/prompt_planner.py and
content_packs/*) — that's the legacy/fallback path. Prompt-native is the
new default for `Generate New Video`.
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import asdict, dataclass, field
from typing import Iterable, Optional


# ─── Plan dataclasses ───────────────────────────────────────────────────


@dataclass
class Scene:
    """One shot in the final video."""
    scene_id: str
    duration: float
    visual_prompt: str
    camera_motion: str
    subject: str
    environment: str
    mood: str
    transition: str
    on_screen_caption: str
    narration_line: str


@dataclass
class VideoPlan:
    """A complete creative brief produced from a single user prompt."""
    title: str
    concept: str
    hook: str
    emotional_angle: str
    audience: str
    visual_style: str          # preset name (crystal | papercraft | neon_arcade | monument)
    color_palette: str
    pacing: str                # calm | medium | energetic
    voice_tone: str
    caption_style: str         # word | line
    scenes: list[Scene]
    voiceover_lines: list[str]
    cta: str
    negative_prompt: str
    seed: int
    prompt_hash: str
    # Provenance
    user_prompt: str = ""
    theme: str = ""
    variation_id: int = 0
    format_name: str = ""
    duration_target: float = 0.0
    aspect_ratio: str = "9:16"
    generation_mode: str = "prompt_native"

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ─── Theme profiles ─────────────────────────────────────────────────────
#
# A theme is a high-level intent (motivation, mystery, ai, ambient, ...)
# that selects a creative-direction pool. The pool itself is combinatorial:
# archetypes × settings × moments × tensions × resolutions are mixed by a
# seeded RNG so each variation is a fresh creative direction, not a
# keyword swap.

@dataclass
class ThemeProfile:
    name: str
    archetypes: list[str]
    settings: list[str]
    moments: list[str]
    tensions: list[str]
    resolutions: list[str]
    moods: list[str]
    visual_style_pool: list[str]              # preset names
    color_palette_pool: list[str]
    voice_tones: list[str]
    pacing_pool: list[str]                    # calm/medium/energetic
    hook_templates: list[str]
    cta_pool: list[str]
    audience: str
    title_templates: list[str]
    concept_templates: list[str]              # uses {archetype}, {setting}, {moment}, {tension}, {resolution}
    narration_templates: list[str]            # used for voiceover lines
    caption_templates: list[str]              # short, on-screen capable
    emotional_angles: list[str]
    extra_tags: list[str] = field(default_factory=list)


# Subject motion words that map to camera moves available to the parallax
# animator. Keep this small — the parallax stage only knows zoom/pan.
_CAMERA_MOTIONS = [
    "slow push-in",
    "slow pull-back",
    "drift left",
    "drift right",
    "rising tilt",
    "falling tilt",
    "static hold",
    "orbit",
]


_THEMES: dict[str, ThemeProfile] = {
    "motivation": ThemeProfile(
        name="motivation",
        archetypes=[
            "a lone boxer", "a student studying past midnight",
            "a tired worker", "a future self",
            "a soldier's morning routine", "a runner before sunrise",
            "a single mother", "an overlooked junior on the team",
            "a sober man on day 90", "a quiet veteran",
            "an injured athlete returning to the gym",
            "a comeback artist starting again at 40",
            "a programmer still typing at 3 a.m.",
            "a chef opening a kitchen at 4 a.m.",
            "a kid practicing alone in an empty parking lot",
        ],
        settings=[
            "a small apartment", "an empty gym", "a foggy mountain road",
            "an unlit kitchen", "a worn-down dojo", "a corner office at night",
            "a rooftop above the city", "a rusted iron staircase",
            "a snow-covered driveway", "a cold concrete garage",
            "an empty stadium", "a hospital hallway", "a tiny dorm room",
        ],
        moments=[
            "before sunrise", "at midnight", "in the rain",
            "during the first snowfall", "while the rest of the world sleeps",
            "the morning after losing", "the night before the test",
            "the day after relapse", "the hour before kickoff",
        ],
        tensions=[
            "fighting the urge to scroll the phone",
            "carrying the weight of yesterday's failure",
            "wanting to quit one more time",
            "feeling invisible to everyone",
            "doubting that any of it matters",
            "watching others celebrate without them",
            "missing the people who used to believe in them",
        ],
        resolutions=[
            "they take one more step",
            "they pick up the weight again",
            "they close the laptop and start over",
            "they put the phone face-down and breathe",
            "they tie their laces and walk to the door",
            "they whisper a vow no one will hear",
            "they make the small choice no one will ever applaud",
        ],
        moods=["raw", "resolute", "stoic", "burning", "still", "defiant"],
        visual_style_pool=["crystal", "monument", "neon_arcade"],
        color_palette_pool=["earth", "duotone", "monochrome", "neon"],
        voice_tones=[
            "low and steady", "measured and gravelly", "calm but unflinching",
            "quiet and certain", "rising and resolute",
        ],
        pacing_pool=["medium", "energetic", "calm"],
        hook_templates=[
            "Nobody's coming. Get up.",
            "This is the part nobody films.",
            "The decision is small. The cost is everything.",
            "While they slept, you started.",
            "The work doesn't care how you feel.",
            "This is what discipline actually looks like.",
            "The version of you they doubt is the version that wins.",
        ],
        cta_pool=[
            "Save this. Watch it tomorrow at 5 a.m.",
            "Send this to the one who needs it.",
            "Follow for the part of the story nobody romanticizes.",
            "Come back when you want to quit.",
        ],
        audience="people building a habit alone",
        title_templates=[
            "The part of {archetype}'s story you don't see",
            "{archetype}, {moment}",
            "What {archetype} chose when no one was watching",
            "The morning {archetype} stopped negotiating with themselves",
        ],
        concept_templates=[
            "{archetype} in {setting}, {moment}. {tension}. Then {resolution}.",
            "We meet {archetype} {moment}, alone in {setting}. The whole room is asking them to stop. {resolution}.",
            "Inside {setting}, {moment}, {archetype} is {tension}. The frame holds — until {resolution}.",
        ],
        narration_templates=[
            "{moment_cap}, the room is empty.",
            "Nobody is asking {archetype_short} to keep going.",
            "{tension_cap}.",
            "And still — {resolution}.",
            "This is where most people would stop.",
            "This is where the decision is actually made.",
            "Discipline isn't loud. It looks like this.",
        ],
        caption_templates=[
            "Nobody is watching.",
            "Do it anyway.",
            "{moment_short}.",
            "One more step.",
            "Quiet wins.",
            "This is the work.",
            "Keep going.",
        ],
        emotional_angles=[
            "the unseen private decision",
            "endurance over inspiration",
            "small choices compounding",
            "loneliness as proof of commitment",
        ],
        extra_tags=["cinematic", "stoic", "vertical 9:16"],
    ),
    "mystery": ThemeProfile(
        name="mystery",
        archetypes=[
            "a forgotten coastal village",
            "an abandoned research outpost",
            "a missing radio operator",
            "a sealed mountain monastery",
            "a buried desert temple",
            "a cold-case detective's last file",
            "a deep-sea cable repair crew",
            "a rural sheriff's unfiled report",
            "a midnight librarian",
        ],
        settings=[
            "an icy fjord", "a fogged forest at twilight",
            "a quiet observatory at 3 a.m.", "a long empty corridor",
            "a cliffside lighthouse", "a desert ravine after sundown",
            "a humid jungle ridge", "an underground archive",
        ],
        moments=[
            "the night the signal stopped",
            "the morning the door was found unlocked",
            "the day after they all left",
            "the year nobody wrote down",
            "the hour the lights flickered out",
        ],
        tensions=[
            "no one ever came back",
            "the radio went silent mid-sentence",
            "the door was locked from the inside",
            "every photograph stopped on the same day",
            "the records skip exactly one week",
        ],
        resolutions=[
            "and the question is still open",
            "and the answer is still missing",
            "and no investigator has explained it",
            "and the file is still classified",
            "and the witnesses changed their story before they died",
        ],
        moods=["uneasy", "still", "cold", "watchful", "haunted"],
        visual_style_pool=["monument", "papercraft", "crystal"],
        color_palette_pool=["monochrome", "duotone", "earth"],
        voice_tones=[
            "low and steady", "measured and quiet",
            "deliberate and careful", "calm and unsettling",
        ],
        pacing_pool=["calm", "medium"],
        hook_templates=[
            "Nobody ever explained it.",
            "The records simply stop.",
            "It's been {gap_years} years. The answer is still missing.",
            "One detail nobody could ever account for.",
        ],
        cta_pool=[
            "Follow for part 2. The next file is worse.",
            "Save this — read the witness statement at the end.",
            "Comment what you think actually happened.",
        ],
        audience="people who like cold-case threads",
        title_templates=[
            "Still unsolved: {archetype}",
            "The {archetype} case nobody talks about",
            "The night {archetype} went silent",
        ],
        concept_templates=[
            "{archetype} on {moment}: {tension}. {resolution}.",
            "We open on {setting}. The story begins {moment}. {tension}. {resolution}.",
        ],
        narration_templates=[
            "It started in {setting}.",
            "{moment_cap}, everything was normal.",
            "Then {tension}.",
            "{resolution}.",
            "Investigators called it a coincidence. They were wrong.",
        ],
        caption_templates=[
            "It's been a long time.",
            "The file is still open.",
            "Nobody can explain this.",
            "The detail nobody mentions.",
            "Watch closely.",
        ],
        emotional_angles=[
            "the detail that doesn't fit",
            "the witness who recanted",
            "the gap nobody filled in",
        ],
        extra_tags=["eerie", "cinematic", "vertical 9:16"],
    ),
    "ai_tech": ThemeProfile(
        name="ai_tech",
        archetypes=[
            "the first model trained without humans in the loop",
            "a chip the size of a fingernail",
            "the inference path of a single token",
            "an unsupervised clustering of every painting ever scanned",
            "an autonomous agent quietly editing its own memory",
            "a swarm of tiny robots learning to balance",
            "a neural net dreaming during fine-tuning",
        ],
        settings=[
            "a bare data center hallway", "a microscopic silicon lattice",
            "a glowing graph of attention heads", "a midnight server farm",
            "a humming GPU cluster", "a clean-room wafer line",
        ],
        moments=[
            "the first time the loss curve dropped past zero-shot baselines",
            "during the second week of training",
            "the moment compute was unplugged from supervision",
            "the first night the model talked to itself",
        ],
        tensions=[
            "no human had ever read the data it learned from",
            "the model's outputs began surprising its creators",
            "the system started compressing its own intermediate steps",
            "the agent stopped asking permission",
        ],
        resolutions=[
            "and the field changed forever",
            "and we still don't know why it works",
            "and the paper is now considered foundational",
            "and most labs quietly copied the trick",
        ],
        moods=["clean", "weighty", "futuristic", "watchful"],
        visual_style_pool=["neon_arcade", "crystal", "monument"],
        color_palette_pool=["neon", "duotone", "monochrome"],
        voice_tones=["measured and dry", "calm and curious", "matter-of-fact"],
        pacing_pool=["medium", "energetic"],
        hook_templates=[
            "This shouldn't have worked.",
            "Most people missed why this changed everything.",
            "One trick. Everything after it was different.",
        ],
        cta_pool=[
            "Follow for the visuals nobody else makes.",
            "Save this — the next one explains the math.",
            "Comment which paper to break down next.",
        ],
        audience="builders, researchers, curious technical readers",
        title_templates=[
            "Why this changed AI",
            "The detail behind {archetype}",
            "The quiet revolution: {archetype}",
        ],
        concept_templates=[
            "{archetype}, {moment}: {tension}. {resolution}.",
            "The story of {archetype}, told in {setting}. {tension}. {resolution}.",
        ],
        narration_templates=[
            "Most people skipped this.",
            "{moment_cap}, something unusual happened.",
            "{tension_cap}.",
            "{resolution}.",
            "It's why almost every system after it looks the way it does.",
        ],
        caption_templates=[
            "Watch this.",
            "The trick.",
            "What changed.",
            "Why it matters.",
            "Most people missed this.",
        ],
        emotional_angles=[
            "the mechanism behind the magic",
            "the moment the curve broke",
            "the elegance hidden under the abstraction",
        ],
        extra_tags=["clean", "futuristic", "vertical 9:16"],
    ),
    "product": ThemeProfile(
        name="product",
        archetypes=[
            "the new model", "the redesigned classic",
            "the limited edition", "the flagship",
            "the everyday carry", "the studio prototype",
        ],
        settings=[
            "a soft gradient stage", "a velvet pedestal",
            "a clean white cyclorama", "a misty black void",
            "a chrome-edged turntable", "a gallery wall under a single spot",
        ],
        moments=[
            "for the first time", "after three years of revisions",
            "ahead of release", "behind closed doors", "at first light",
        ],
        tensions=[
            "every detail was argued over",
            "the team rebuilt it twice",
            "they almost didn't ship",
            "the prototype outperformed the production line",
        ],
        resolutions=[
            "and now you can finally see it",
            "and it's quietly the best they've ever shipped",
            "and it's been worth the wait",
        ],
        moods=["clean", "premium", "intentional"],
        visual_style_pool=["crystal", "monument", "papercraft"],
        color_palette_pool=["pastel", "monochrome", "duotone"],
        voice_tones=["calm and confident", "warm and certain", "polished"],
        pacing_pool=["calm", "medium"],
        hook_templates=[
            "Three years. One redesign. {archetype_cap}.",
            "Built quietly. Worth the wait.",
            "{archetype_cap}. Reveal day.",
        ],
        cta_pool=[
            "Available now.",
            "Tap to be first in line.",
            "Save this for launch day.",
        ],
        audience="people considering an upgrade",
        title_templates=[
            "Presenting {archetype}",
            "{archetype_cap} — first look",
            "The new shape of {archetype}",
        ],
        concept_templates=[
            "{archetype_cap} on {setting}, {moment}. {tension}. {resolution}.",
            "We meet {archetype} {moment}: {tension}. {resolution}.",
        ],
        narration_templates=[
            "{archetype_cap}.",
            "{moment_cap}.",
            "{tension_cap}.",
            "{resolution_cap}.",
            "Designed without compromise.",
        ],
        caption_templates=[
            "Reveal.",
            "Quiet detail.",
            "Built carefully.",
            "Look closer.",
            "Available soon.",
        ],
        emotional_angles=[
            "design as restraint",
            "the detail you only see in person",
            "the work behind the simplicity",
        ],
        extra_tags=["premium", "clean", "vertical 9:16"],
    ),
    "ambient": ThemeProfile(
        name="ambient",
        archetypes=[
            "drifting facets", "soft pulses of light",
            "a slow cascade of crystals", "a single geometric monolith",
            "looping concentric rings", "a quiet mountain at first light",
        ],
        settings=[
            "a soft pastel void", "a glowing dawn sky",
            "a misty pale ocean", "a quiet snowfield",
            "a geometric garden under moonlight",
        ],
        moments=[
            "at the threshold of dawn", "in a long quiet hour",
            "between sleep and waking", "at the end of the day",
            "at the still point",
        ],
        tensions=[
            "the world is still asleep",
            "nothing is asking anything of you",
            "the noise has finally stopped",
            "there is nowhere to be",
        ],
        resolutions=[
            "and the loop just continues",
            "and the moment lingers",
            "and the breath slows down",
        ],
        moods=["dreamy", "serene", "ethereal", "still"],
        visual_style_pool=["crystal", "monument", "papercraft"],
        color_palette_pool=["pastel", "duotone", "monochrome"],
        voice_tones=["gentle and slow", "warm and quiet"],
        pacing_pool=["calm"],
        hook_templates=[
            "Slow down for 20 seconds.",
            "Loop this. Breathe with it.",
            "Put this on full screen.",
        ],
        cta_pool=[
            "More loops daily.",
            "Save this for late nights.",
            "Headphones recommended.",
        ],
        audience="anyone who needs a soft minute",
        title_templates=[
            "Loop: {archetype}",
            "Drift",
            "Stillness",
        ],
        concept_templates=[
            "{archetype_cap}, {moment}, in {setting}.",
            "{moment_cap}: {archetype} suspended in {setting}.",
        ],
        narration_templates=[
            "{moment_cap}.",
            "{tension_cap}.",
            "{resolution_cap}.",
        ],
        caption_templates=[
            "Breathe in.",
            "Slow down.",
            "Stay here for a moment.",
            "Just a minute.",
        ],
        emotional_angles=[
            "permission to slow down",
            "soft persistence",
        ],
        extra_tags=["dreamy", "minimal", "loop"],
    ),
    "horror": ThemeProfile(
        name="horror",
        archetypes=[
            "a man counting cash alone in a basement",
            "a janitor on the late shift of a casino floor",
            "a debt collector knocking at midnight",
            "a stranger who left a sealed briefcase on the bench",
            "a banker who hadn't slept in nine days",
            "a teller closing the vault for the last time",
            "a courier carrying a package no one will sign for",
            "a forensic accountant on the third audit",
            "a couple counting money they don't remember earning",
            "a landlord knocking on a door rent already paid",
            "a security guard reviewing the same minute of footage",
            "a tax inspector standing in an empty office",
            "a private investigator following the receipts backward",
            "a night-shift bookkeeper at an off-the-books desk",
            "a notary witnessing a signature no one signed",
        ],
        settings=[
            "an unlit underground parking lot",
            "an empty bank lobby after hours",
            "a long hallway with one buzzing fluorescent",
            "a basement under a single bare bulb",
            "an abandoned suburban kitchen",
            "an office tower at 2 a.m.",
            "a motel hallway with carpet that sticks",
            "a vault room with no visible door",
            "a dimly lit casino floor at 4 a.m.",
            "a back office above a closed pawnshop",
            "a stairwell that smells like old coins",
            "a corridor lined with safety deposit boxes",
        ],
        moments=[
            "the night the wire transfer cleared",
            "the morning the cash was missing",
            "the third night of the noise",
            "the day after the deposit",
            "the hour the lights cut out",
            "the week nobody could account for",
            "the moment the receipt printed twice",
            "the second the safe clicked on its own",
        ],
        tensions=[
            "the cash kept growing on its own",
            "every receipt had the same date and the same name",
            "the safe was already open when they got there",
            "the bank's records skipped exactly one week",
            "someone had been counting it before they got home",
            "the hundred-dollar bills weren't aging",
            "the deposits were arriving from accounts that didn't exist",
            "the camera footage had the same minute on a loop",
        ],
        resolutions=[
            "and they never told anyone",
            "and the money was gone by morning",
            "and the next envelope arrived a week later",
            "and the records have since vanished",
            "and the cameras conveniently stopped working",
            "and nobody from that branch can be reached",
            "and the only witness has stopped returning calls",
        ],
        moods=["cold", "watchful", "creeping", "uneasy", "still", "dreadful"],
        visual_style_pool=["monument", "neon_arcade", "papercraft"],
        color_palette_pool=["monochrome", "duotone", "neon"],
        voice_tones=[
            "hushed and deliberate", "low and quiet",
            "measured and cold", "calm and unsettling",
        ],
        pacing_pool=["calm", "medium"],
        hook_templates=[
            "Nobody could explain where it came from.",
            "It started small. Then it didn't.",
            "The money was real. That was the problem.",
            "It's been {gap_years} years. The account is still active.",
            "They counted it three times. It kept changing.",
            "This is the part the bank quietly removed from the file.",
        ],
        cta_pool=[
            "Save this — comment if this happened to you.",
            "Follow for part 2. The next case is worse.",
            "Share with someone who's seen something they can't explain.",
            "Do not screenshot the last frame.",
        ],
        audience="people who like cold-case + noir threads",
        title_templates=[
            "The night {archetype} happened",
            "Still unsolved: {archetype}",
            "What really happened with {archetype}",
            "The {archetype} case nobody talks about",
        ],
        concept_templates=[
            "{archetype_cap} on {moment}: {tension}. {resolution}.",
            "Inside {setting}, {moment}, we meet {archetype}. {tension}. {resolution}.",
            "{moment_cap}, in {setting}, {archetype} is found. {tension}. {resolution}.",
        ],
        narration_templates=[
            "It started in {setting}.",
            "{moment_cap}, everything looked normal.",
            "Then {tension}.",
            "The next morning, the room was the same. The numbers weren't.",
            "{resolution_cap}.",
            "Investigators called it a clerical error. They were wrong.",
            "Nobody on the floor would say the name out loud after that.",
        ],
        caption_templates=[
            "It's still happening.",
            "The receipt doesn't lie.",
            "Watch the corner of the frame.",
            "Count it again.",
            "Nobody can explain this.",
            "The detail nobody mentions.",
            "Don't look up.",
        ],
        emotional_angles=[
            "wealth as a thing that arrives, not a thing you earn",
            "the dread of money you cannot account for",
            "the quiet of rooms with too much cash in them",
            "the witness who stopped speaking",
        ],
        extra_tags=["cinematic", "noir", "uneasy", "vertical 9:16"],
    ),
    "story": ThemeProfile(
        name="story",
        archetypes=[
            "a stranger on the last train",
            "a child's first letter to their future self",
            "a courier with a sealed envelope",
            "a quiet pen pal who never met in person",
            "two travelers who shared one umbrella",
            "an old man feeding birds at the same bench every morning",
        ],
        settings=[
            "a long empty platform", "a small kitchen with one warm light",
            "a coastal cliff at dusk", "a city park in the off-season",
            "an attic full of unopened boxes",
        ],
        moments=[
            "the night nobody planned to remember",
            "the morning the letter finally arrived",
            "the year the envelope was opened",
            "the hour everything quietly changed",
        ],
        tensions=[
            "they almost never met",
            "they never spoke about it again",
            "the letter sat unopened for twenty years",
            "no one in the family ever asked",
        ],
        resolutions=[
            "and that single hour is why everything else happened",
            "and the rest of the story is still being lived",
            "and they only realized later what they had given each other",
        ],
        moods=["tender", "warm", "quiet", "earnest"],
        visual_style_pool=["papercraft", "crystal", "monument"],
        color_palette_pool=["earth", "pastel", "duotone"],
        voice_tones=["warm and gentle", "soft and unhurried"],
        pacing_pool=["calm", "medium"],
        hook_templates=[
            "This is a small story. Stay till the end.",
            "It only took an hour. It changed everything.",
            "They never spoke again. They never had to.",
        ],
        cta_pool=[
            "Send this to someone you owe a letter to.",
            "Save this for the next quiet evening.",
            "Follow for more small stories.",
        ],
        audience="anyone who likes quiet emotional shorts",
        title_templates=[
            "{archetype_cap}",
            "The hour {archetype}",
            "A small story about {archetype}",
        ],
        concept_templates=[
            "{archetype_cap} in {setting}, {moment}. {tension}. {resolution}.",
        ],
        narration_templates=[
            "{archetype_cap}.",
            "{moment_cap}.",
            "{tension_cap}.",
            "{resolution_cap}.",
        ],
        caption_templates=[
            "A small moment.",
            "Stay with it.",
            "It only took an hour.",
            "Quiet truth.",
        ],
        emotional_angles=[
            "the smallness of pivotal moments",
            "kindness as plot",
        ],
        extra_tags=["warm", "tender", "vertical 9:16"],
    ),
}


# ─── Theme detection ────────────────────────────────────────────────────

# Lightweight keyword routing into a theme. Order matters — earlier themes
# win on ties (e.g. "ai motivation" prefers ai_tech). Themes are a soft
# router: the *concept* itself is still generated combinatorially.
_THEME_KEYWORDS: dict[str, list[str]] = {
    "horror": [
        "scary", "horror", "creepy", "unsettling", "dread", "nightmare",
        "money", "cash", "debt", "wealth", "rich", "broke", "vault",
        "atm", "bank", "deposit", "withdrawal", "safe", "loan",
        "foreclosure", "midnight knock", "noir",
    ],
    "ai_tech": [
        "ai", "artificial intelligence", "neural", "gpu", "model",
        "robot", "robotic", "machine learning", "llm", "data", "tech",
        "automation", "algorithm", "silicon", "chip", "compute",
    ],
    "mystery": [
        "mystery", "mysteries", "unsolved", "ancient", "vanished",
        "lost", "eerie", "conspiracy", "haunted", "cold case", "ruins",
        "creepy", "paranormal", "cover-up",
    ],
    "product": [
        "product", "ad", "ads", "launch", "brand", "commercial", "promo",
        "teaser", "reveal", "drop", "store", "marketing", "e-commerce",
        "watch", "sneaker", "headphones", "gadget", "phone",
    ],
    "ambient": [
        "loop", "loops", "abstract", "ambient", "vibe", "vibes", "mood",
        "dreamy", "filler", "background", "minimal", "aesthetic", "pastel",
        "lofi", "lo-fi", "chill",
    ],
    "story": [
        "story", "letter", "memory", "memories", "stranger", "kindness",
        "tender", "small story", "narrative",
    ],
    "motivation": [
        "motivation", "motivational", "discipline", "grind", "growth",
        "success", "purpose", "resilience", "comeback", "win", "grit",
        "self-improvement", "mindset", "warrior", "hustle", "focus",
        "pain", "struggle", "rise", "peak", "courage", "fear", "habit",
    ],
}


def detect_theme(prompt: str) -> str:
    """Pick a theme from the prompt by keyword score.

    Returns "motivation" by default — it's the broadest concept pool.
    """
    text = prompt.lower()
    best, best_score = "motivation", 0
    for theme, kws in _THEME_KEYWORDS.items():
        score = 0
        for kw in kws:
            if " " in kw:
                if kw in text:
                    score += 2
            else:
                if re.search(rf"\b{re.escape(kw)}\b", text):
                    score += 1
        # Prefer earlier themes on tie (more specific routes first)
        if score > best_score:
            best, best_score = theme, score
    return best


# ─── Concept composition ────────────────────────────────────────────────

def _seed_for(prompt_hash: str, variation_id: int, user_seed: Optional[int]) -> int:
    """Combine prompt hash + variation_id (+ optional user seed) into a
    32-bit RNG seed. With user_seed=None, every call to the same prompt
    produces a *different* plan because variation_id is unique per call.
    """
    base = int(prompt_hash[:8], 16)
    if user_seed is not None:
        return (base ^ (int(user_seed) * 2654435761) ^ variation_id) & 0xFFFFFFFF
    return (base ^ (variation_id * 2654435761)) & 0xFFFFFFFF


def _capfirst(s: str) -> str:
    s = s.strip()
    return s[:1].upper() + s[1:] if s else s


def _archetype_short(archetype: str) -> str:
    """Strip leading article ('a ', 'an ', 'the ') for narration where the
    archetype is the subject of the next clause."""
    a = archetype.strip()
    for art in ("a ", "an ", "the "):
        if a.lower().startswith(art):
            return a[len(art):]
    return a


_PUNCT_TAIL = re.compile(r"[\s\.;,:]+$")


def _strip_tail(s: str) -> str:
    return _PUNCT_TAIL.sub("", s)


def _fill(template: str, ctx: dict) -> str:
    """Tiny string formatter that ignores missing keys."""
    def repl(m: re.Match) -> str:
        key = m.group(1)
        return str(ctx.get(key, m.group(0)))
    return re.sub(r"\{([a-zA-Z_]+)\}", repl, template)


def _build_context(theme: ThemeProfile, rng: random.Random) -> dict:
    archetype = rng.choice(theme.archetypes)
    setting = rng.choice(theme.settings)
    moment = rng.choice(theme.moments)
    tension = rng.choice(theme.tensions)
    resolution = rng.choice(theme.resolutions)
    mood = rng.choice(theme.moods)
    short = _archetype_short(archetype)
    moment_short = moment.split(",")[0].strip()
    return {
        "archetype": archetype,
        "archetype_cap": _capfirst(archetype),
        "archetype_short": short,
        "setting": setting,
        "setting_cap": _capfirst(setting),
        "moment": moment,
        "moment_cap": _capfirst(moment),
        "moment_short": moment_short,
        "tension": tension,
        "tension_cap": _capfirst(_strip_tail(tension)),
        "resolution": _strip_tail(resolution),
        "resolution_cap": _capfirst(_strip_tail(resolution)),
        "mood": mood,
        "gap_years": rng.choice([23, 41, 57, 64, 78, 102]),
    }


# ─── Visual prompt compilation ──────────────────────────────────────────

# Map a logical "camera_motion" string from the director to a parallax
# motion profile (calm/medium/energetic) the existing batch runner knows.
_MOTION_TO_PROFILE = {
    "static hold": "calm",
    "slow push-in": "calm",
    "slow pull-back": "calm",
    "drift left": "medium",
    "drift right": "medium",
    "rising tilt": "medium",
    "falling tilt": "medium",
    "orbit": "energetic",
}


def camera_motion_to_motion_profile(camera_motion: str) -> str:
    return _MOTION_TO_PROFILE.get(camera_motion, "medium")


def _build_visual_prompt(
    subject: str,
    environment: str,
    visual_style: str,
    color_palette: str,
    mood: str,
    camera_motion: str,
) -> str:
    """Compose a stable visual prompt for SDXL keyframe generation.

    Keeps the low-poly aesthetic at the front of the prompt so the style
    survives whatever the user prompt was about.
    """
    parts = [
        f"low poly 3d render of {subject}",
        environment,
        f"{color_palette} color palette",
        f"{mood} mood",
        f"{camera_motion} composition",
        "stylized minimalist, clean geometric edges, sharp polygon faces",
    ]
    return ", ".join(p for p in parts if p)


_NEGATIVE_BASE = (
    "photorealistic, smooth surfaces, organic textures, film grain, "
    "bokeh, lens flare, motion blur, high detail skin, hair strands, "
    "realistic lighting, ray tracing, subsurface scattering, noise, "
    "artifacts, blurry, watermark, text, signature, jpeg artifacts, "
    "deformed, ugly, duplicate, typography, on-screen text"
)


# ─── Style / preference parsing ─────────────────────────────────────────

# Style preference cues from the user prompt that should override the
# theme's random pool. ("intense" → energetic, "dreamy" → calm, etc.)
_STYLE_PREFS: dict[str, dict] = {
    "intense":   {"pacing": "energetic", "voice_tone": "rising and resolute"},
    "cinematic": {"pacing": "medium",    "voice_tone": "low and steady"},
    "epic":      {"pacing": "energetic", "voice_tone": "rising and resolute"},
    "calm":      {"pacing": "calm",      "voice_tone": "gentle and slow"},
    "dreamy":    {"pacing": "calm",      "color_palette": "pastel"},
    "warm":      {"pacing": "calm",      "color_palette": "earth"},
    "neon":      {"visual_style": "neon_arcade", "color_palette": "neon"},
    "monument":  {"visual_style": "monument"},
    "papercraft": {"visual_style": "papercraft"},
    "crystal":   {"visual_style": "crystal"},
    "pastel":    {"color_palette": "pastel"},
    "monochrome": {"color_palette": "monochrome"},
    "earth":     {"color_palette": "earth"},
}


def _apply_style_prefs(prompt: str, base: dict) -> dict:
    """Layer prompt-side style cues over the theme's random picks."""
    text = prompt.lower()
    out = dict(base)
    for cue, overrides in _STYLE_PREFS.items():
        if cue in text:
            out.update(overrides)
    return out


# Format → defaults that drive duration/pacing if the caller didn't pass
# them explicitly. Matches xvideo/formats/*.json so the prompt-native and
# pack-based paths agree on packaging.
_FORMAT_DEFAULTS: dict[str, dict] = {
    "shorts_clean":     {"duration": 20.0, "primary": "shorts"},
    "tiktok_fast":      {"duration": 15.0, "primary": "tiktok"},
    "reels_aesthetic":  {"duration": 18.0, "primary": "reels"},
}


def _resolve_format(format_name: str, duration_target: Optional[float]) -> tuple[float, str]:
    f = _FORMAT_DEFAULTS.get(format_name) or {}
    duration = float(duration_target) if duration_target else float(f.get("duration", 20.0))
    primary = f.get("primary", "shorts")
    return duration, primary


# ─── Scene plan generation ──────────────────────────────────────────────

def _scene_count_for(duration: float, pacing: str) -> int:
    """Pick a scene count that fits the duration and pacing.

    Each background clip is ~3-4s once finalized. Faster pacing = more
    scenes for the same duration.
    """
    per_scene = {"calm": 4.0, "medium": 3.5, "energetic": 2.8}.get(pacing, 3.5)
    n = max(3, min(7, round(duration / per_scene)))
    return n


def _scene_durations(total: float, n: int) -> list[float]:
    """Distribute total duration across n scenes with mild variation."""
    base = total / n
    out = [round(base, 2) for _ in range(n)]
    # First scene is slightly longer (hook holds), last scene slightly longer (CTA lands)
    if n >= 3:
        out[0] = round(base * 1.15, 2)
        out[-1] = round(base * 1.10, 2)
        slack = total - sum(out)
        for i in range(1, n - 1):
            out[i] = round(out[i] + slack / (n - 2), 2)
    return out


_TRANSITIONS = ["cut", "soft fade", "match cut", "whip pan", "dip to black"]


def _scene_subjects(theme: ThemeProfile, ctx: dict, n: int, rng: random.Random) -> list[tuple[str, str]]:
    """Pick (subject, environment) pairs for each scene.

    Subjects follow the concept arc: setup → tension → turn → resolution.
    We pick distinct settings for visual variety.
    """
    archetype = ctx["archetype"]
    setting_pool = list(theme.settings)
    rng.shuffle(setting_pool)
    settings = (setting_pool * (n // len(setting_pool) + 1))[:n]

    arc: list[tuple[str, str]] = []
    # Beat structure
    for i in range(n):
        if i == 0:
            arc.append((archetype, ctx["setting"]))                       # establish
        elif i == n - 1:
            arc.append((f"{_archetype_short(archetype)} alone", settings[i]))  # resolve
        else:
            # tension scenes: pick a charged sub-image
            tension_subjects = [
                f"{_archetype_short(archetype)} mid-action",
                f"the hands of {_archetype_short(archetype)}",
                f"the shoes of {_archetype_short(archetype)}",
                f"{_archetype_short(archetype)} catching their breath",
                f"a single object on the floor near {_archetype_short(archetype)}",
                f"{_archetype_short(archetype)} looking up",
            ]
            arc.append((rng.choice(tension_subjects), settings[i]))
    return arc


def _scene_camera_motion(i: int, n: int, pacing: str, rng: random.Random) -> str:
    """Camera motion that supports the beat (open / build / land)."""
    opener = ["slow push-in", "drift right", "rising tilt", "static hold"]
    middle = ["drift left", "drift right", "orbit", "rising tilt"]
    closer = ["slow pull-back", "static hold", "falling tilt"]
    if pacing == "energetic":
        opener = ["slow push-in", "orbit"]
        middle = ["orbit", "drift right", "rising tilt"]
        closer = ["slow pull-back", "static hold"]
    if i == 0:
        return rng.choice(opener)
    if i == n - 1:
        return rng.choice(closer)
    return rng.choice(middle)


def _build_scenes(
    theme: ThemeProfile,
    ctx: dict,
    voiceover_lines: list[str],
    captions: list[str],
    duration: float,
    pacing: str,
    visual_style: str,
    color_palette: str,
    rng: random.Random,
) -> list[Scene]:
    n = _scene_count_for(duration, pacing)
    durations = _scene_durations(duration, n)
    subjects = _scene_subjects(theme, ctx, n, rng)

    # Stretch/compress narration & captions to scene count
    narrations = list(voiceover_lines)
    if not narrations:
        narrations = [""]
    while len(narrations) < n:
        narrations.append(narrations[-1])
    narrations = narrations[:n]

    cap_pool = list(captions)
    if not cap_pool:
        cap_pool = [""]
    on_screen = []
    for i in range(n):
        on_screen.append(cap_pool[i % len(cap_pool)])

    scenes: list[Scene] = []
    for i, ((subj, env), dur) in enumerate(zip(subjects, durations)):
        cam = _scene_camera_motion(i, n, pacing, rng)
        mood = ctx.get("mood", "still")
        visual_prompt = _build_visual_prompt(
            subject=subj,
            environment=env,
            visual_style=visual_style,
            color_palette=color_palette,
            mood=mood,
            camera_motion=cam,
        )
        transition = "cut" if i == 0 else rng.choice(_TRANSITIONS)
        scenes.append(Scene(
            scene_id=f"s{i+1:02d}",
            duration=dur,
            visual_prompt=visual_prompt,
            camera_motion=cam,
            subject=subj,
            environment=env,
            mood=mood,
            transition=transition,
            on_screen_caption=on_screen[i],
            narration_line=narrations[i],
        ))
    return scenes


# ─── Voiceover + caption generation ─────────────────────────────────────

def _build_narration(theme: ThemeProfile, ctx: dict, rng: random.Random,
                     hook: str, cta: str, scene_count: int) -> list[str]:
    """Pick narration templates and fill them. The hook is the first line;
    the CTA is the last. Middle lines come from the theme's narration
    pool, scaled to scene_count.
    """
    pool = list(theme.narration_templates)
    rng.shuffle(pool)
    middle_target = max(1, scene_count - 2)
    middle_raw = pool[: middle_target * 2]  # take extra; we'll dedupe + trim

    middle: list[str] = []
    for tpl in middle_raw:
        line = _fill(tpl, ctx).strip()
        if line and line not in middle and line.lower() != hook.lower():
            middle.append(line)
        if len(middle) >= middle_target:
            break
    while len(middle) < middle_target:
        middle.append(_fill(rng.choice(theme.narration_templates), ctx))

    lines = [hook] + middle + [cta]
    # Dedupe contiguous duplicates
    out: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if out and out[-1].lower() == line.lower():
            continue
        out.append(line)
    return out


def _build_captions(theme: ThemeProfile, ctx: dict, rng: random.Random,
                     scene_count: int) -> list[str]:
    pool = list(theme.caption_templates)
    rng.shuffle(pool)
    out: list[str] = []
    for tpl in pool:
        c = _fill(tpl, ctx).strip()
        if c and c not in out:
            out.append(c)
        if len(out) >= scene_count:
            break
    while len(out) < scene_count:
        out.append(_fill(rng.choice(theme.caption_templates), ctx))
    return out[:scene_count]


# ─── Public API ─────────────────────────────────────────────────────────

def hash_prompt(user_prompt: str) -> str:
    return hashlib.sha256(user_prompt.strip().lower().encode("utf-8")).hexdigest()[:16]


def generate_video_plan(
    user_prompt: str,
    platform_format: str = "shorts_clean",
    duration_target: Optional[float] = None,
    style_preference: Optional[str] = None,
    seed: Optional[int] = None,
    variation_id: int = 0,
    aspect_ratio: str = "9:16",
) -> VideoPlan:
    """Produce a complete `VideoPlan` from a free-form user prompt.

    Same prompt produces a *different* VideoPlan every time `variation_id`
    changes, unless `seed` is fixed — in which case (seed, variation_id)
    is the deterministic axis.
    """
    if not user_prompt or not user_prompt.strip():
        raise ValueError("user_prompt must be non-empty")

    prompt_hash = hash_prompt(user_prompt)
    plan_seed = _seed_for(prompt_hash, variation_id, seed)
    rng = random.Random(plan_seed)

    theme_name = detect_theme(user_prompt)
    theme = _THEMES[theme_name]

    duration, _primary = _resolve_format(platform_format, duration_target)

    ctx = _build_context(theme, rng)

    base_choices = {
        "visual_style":  rng.choice(theme.visual_style_pool),
        "color_palette": rng.choice(theme.color_palette_pool),
        "pacing":        rng.choice(theme.pacing_pool),
        "voice_tone":    rng.choice(theme.voice_tones),
    }
    style_text = (style_preference or "") + " " + user_prompt
    resolved = _apply_style_prefs(style_text, base_choices)

    # Title / hook / concept / CTA
    title = _fill(rng.choice(theme.title_templates), ctx).strip().rstrip(".")
    hook = _fill(rng.choice(theme.hook_templates), ctx).strip()
    concept = _fill(rng.choice(theme.concept_templates), ctx).strip()
    cta = rng.choice(theme.cta_pool)
    audience = theme.audience
    emotional_angle = rng.choice(theme.emotional_angles)
    caption_style = "word"  # Shorts/TikTok default; line is legacy

    # Compute scenes' captions and narrations from the same RNG so the
    # whole plan is reproducible from (seed, variation_id, prompt_hash).
    scene_count = _scene_count_for(duration, resolved["pacing"])
    captions = _build_captions(theme, ctx, rng, scene_count)
    narration = _build_narration(theme, ctx, rng, hook, cta, scene_count)

    scenes = _build_scenes(
        theme=theme,
        ctx=ctx,
        voiceover_lines=narration,
        captions=captions,
        duration=duration,
        pacing=resolved["pacing"],
        visual_style=resolved["visual_style"],
        color_palette=resolved["color_palette"],
        rng=rng,
    )

    plan = VideoPlan(
        title=title,
        concept=concept,
        hook=hook,
        emotional_angle=emotional_angle,
        audience=audience,
        visual_style=resolved["visual_style"],
        color_palette=resolved["color_palette"],
        pacing=resolved["pacing"],
        voice_tone=resolved["voice_tone"],
        caption_style=caption_style,
        scenes=scenes,
        voiceover_lines=narration,
        cta=cta,
        negative_prompt=_NEGATIVE_BASE,
        seed=plan_seed,
        prompt_hash=prompt_hash,
        user_prompt=user_prompt,
        theme=theme_name,
        variation_id=variation_id,
        format_name=platform_format,
        duration_target=duration,
        aspect_ratio=aspect_ratio,
        generation_mode="prompt_native",
    )
    return plan


def generate_variations(
    user_prompt: str,
    n: int,
    platform_format: str = "shorts_clean",
    duration_target: Optional[float] = None,
    style_preference: Optional[str] = None,
    seed: Optional[int] = None,
    aspect_ratio: str = "9:16",
) -> list[VideoPlan]:
    """Produce `n` distinct VideoPlans from one prompt."""
    if n <= 0:
        raise ValueError("n must be positive")
    return [
        generate_video_plan(
            user_prompt=user_prompt,
            platform_format=platform_format,
            duration_target=duration_target,
            style_preference=style_preference,
            seed=seed,
            variation_id=i,
            aspect_ratio=aspect_ratio,
        )
        for i in range(n)
    ]


def available_themes() -> list[str]:
    return list(_THEMES.keys())
