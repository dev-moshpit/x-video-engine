"""Visual style presets — palette, typography, motion, captions per look.

Each preset bundles the look-and-feel decisions a template makes when an
operator picks a "style" (Photorealistic Cinematic, 3D Cartoon, etc.).
The same preset is consumed by:

  - panel renderers (_panels.py / future _layout.py) for backgrounds,
    accent colors, font weights, card radius
  - the overlay helper for the caption style + safe-zone bias
  - the eventual SDXL prompt-native bridge (positive prefix + negative
    + camera-motion default) — that path lives in xvideo/ and is read
    via ``style_for_engine_prompt(name)`` so the worker can hand the
    string to the engine without xvideo/ needing a forward dependency.

Presets are intentionally code-defined rather than DB-backed — they
ship with the worker and version with the SaaS. New ones are an
explicit code change.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Iterable, Literal


CameraMotion = Literal["calm", "medium", "fast", "chaotic", "cinematic"]
MusicMood = Literal[
    "uplifting", "tense", "ambient", "dramatic", "whimsical",
    "energetic", "luxurious", "horror", "neutral",
]


@dataclass(frozen=True)
class StylePalette:
    """Five-color palette consumed by panel renderers."""

    background: str       # page bg fallback
    surface: str          # card surface
    primary: str          # accent / brand-like
    text_strong: str      # headlines
    text_muted: str       # meta / secondary copy


@dataclass(frozen=True)
class StylePreset:
    """Bundle of visual decisions for a named style."""

    id: str
    name: str
    description: str
    # Engine prompt (only consumed by SDXL-backed templates — the
    # other adapters ignore it). Kept descriptive (not trademarked) on
    # purpose: "anime-inspired 2D cel shading" rather than naming a
    # specific studio.
    positive_prefix: str
    negative_prompt: str
    palette: StylePalette
    camera_motion: CameraMotion
    default_caption_style: str
    music_mood: MusicMood
    # One-liner the operator-facing UI surfaces under the preset chip.
    render_notes: str
    # Optional tags so other code can filter ("dark", "kid_friendly", …).
    tags: tuple[str, ...] = ()


# ─── Catalog ────────────────────────────────────────────────────────────

_PRESETS: dict[str, StylePreset] = {}


def _register(p: StylePreset) -> StylePreset:
    if p.id in _PRESETS:
        raise ValueError(f"duplicate style preset id: {p.id}")
    _PRESETS[p.id] = p
    return p


# Photorealistic
_register(StylePreset(
    id="photorealistic_cinematic",
    name="Photorealistic Cinematic",
    description="Real-world cinematography, shallow depth of field, soft daylight or moody dusk.",
    positive_prefix=(
        "photorealistic cinematic still, 35mm film grain, anamorphic lens flare, "
        "shallow depth of field, natural lighting, color-graded teal and orange, "
        "sharp focus on subject"
    ),
    negative_prompt="cartoon, illustration, low detail, blurry, low contrast, watermark, text overlay",
    palette=StylePalette(
        background="#0d0d0f", surface="#1a1c20",
        primary="#e8b15a", text_strong="#f5f5f7", text_muted="#9aa0a6",
    ),
    camera_motion="cinematic",
    default_caption_style="clean_subtitle",
    music_mood="dramatic",
    render_notes="Best for product reveals, story shorts, premium reels.",
    tags=("realism", "premium"),
))

_register(StylePreset(
    id="documentary",
    name="Cinematic Documentary",
    description="Handheld feel, even daylight, journalistic framing.",
    positive_prefix=(
        "documentary photography, handheld feel, neutral grade, even daylight, "
        "subtle film grain, clear journalistic framing"
    ),
    negative_prompt="oversaturated, cartoon, illustration, anime, fantasy, neon",
    palette=StylePalette(
        background="#101418", surface="#1a2128",
        primary="#76a8e0", text_strong="#f0f2f5", text_muted="#90a0b0",
    ),
    camera_motion="medium",
    default_caption_style="clean_subtitle",
    music_mood="ambient",
    render_notes="History, mystery, explainer, news shorts.",
    tags=("realism", "explainer"),
))

# Animated / illustrative
_register(StylePreset(
    id="cartoon_3d",
    name="3D Cartoon",
    description="Pixar-adjacent 3D rendering — soft shading, big eyes, friendly proportions.",
    positive_prefix=(
        "stylised 3d cartoon, soft cel-shaded rendering, friendly character "
        "design, oversized eyes, smooth subsurface lighting, vibrant pastel palette"
    ),
    negative_prompt="photorealistic, anime, low-poly, gritty, horror",
    palette=StylePalette(
        background="#0e1726", surface="#1d2944",
        primary="#ffb84d", text_strong="#fffaf2", text_muted="#a4b1ce",
    ),
    camera_motion="medium",
    default_caption_style="bold_word",
    music_mood="whimsical",
    render_notes="Kid-friendly stories, fun explainers.",
    tags=("animation", "kid_friendly"),
))

_register(StylePreset(
    id="voxel_world",
    name="Voxel Game World",
    description="Original blocky voxel-styled scenes — generic, not tied to any specific game.",
    positive_prefix=(
        "voxel art, blocky 3d cubes, vibrant saturated palette, generic blocky world, "
        "sharp pixel-cube edges, ambient occlusion"
    ),
    negative_prompt=(
        "minecraft, copyrighted game logo, branded characters, photorealistic, "
        "smooth meshes"
    ),
    palette=StylePalette(
        background="#0e1411", surface="#1b2520",
        primary="#7ee787", text_strong="#f1f8f2", text_muted="#9bb5a4",
    ),
    camera_motion="fast",
    default_caption_style="impact_uppercase",
    music_mood="energetic",
    render_notes="Gameplay-style backdrops without trademarked assets.",
    tags=("game_inspired",),
))

_register(StylePreset(
    id="block_toy",
    name="Toy-Block World",
    description="Original brick-and-block toy aesthetic — generic, not tied to a specific brand.",
    positive_prefix=(
        "studio shot of generic interlocking plastic toy bricks, glossy plastic, "
        "macro detail, soft directional studio lighting, rich primary colors"
    ),
    negative_prompt=(
        "lego logo, branded characters, photorealistic humans, anime, "
        "illustration, cartoon"
    ),
    palette=StylePalette(
        background="#0f1620", surface="#1d2638",
        primary="#ffd166", text_strong="#fff8e1", text_muted="#a4afc1",
    ),
    camera_motion="medium",
    default_caption_style="bold_word",
    music_mood="whimsical",
    render_notes="Playful brand stories without licensed toy IP.",
    tags=("toy", "kid_friendly"),
))

_register(StylePreset(
    id="anime_inspired",
    name="Anime-Inspired",
    description="Original 2D cel-shaded look with anime-inspired palette and line work.",
    positive_prefix=(
        "2d cel-shaded illustration, dynamic linework, vivid hair color highlights, "
        "soft gradient skies, expressive eyes, action lines"
    ),
    negative_prompt="3d render, photorealistic, copyrighted character, blurry",
    palette=StylePalette(
        background="#0c0f1c", surface="#19223e",
        primary="#ff5d8f", text_strong="#fff5fa", text_muted="#a3a8c0",
    ),
    camera_motion="fast",
    default_caption_style="kinetic_word",
    music_mood="energetic",
    render_notes="Story shorts, fight sequences, hero reveals.",
    tags=("animation", "anime_like"),
))

_register(StylePreset(
    id="comic_book",
    name="Comic Book",
    description="Inked panels, halftone shading, kapow-style energy.",
    positive_prefix=(
        "comic book panel, bold ink lines, halftone dot shading, vivid pop colors, "
        "speed lines, dynamic action pose"
    ),
    negative_prompt="photorealistic, soft watercolor, anime cel, 3d render",
    palette=StylePalette(
        background="#101010", surface="#1c1c1c",
        primary="#ff3d68", text_strong="#fff8e7", text_muted="#a8a8a8",
    ),
    camera_motion="fast",
    default_caption_style="impact_uppercase",
    music_mood="energetic",
    render_notes="Hooks that read like a comic splash page.",
    tags=("animation",),
))

_register(StylePreset(
    id="low_poly",
    name="Low-Poly",
    description="Faceted geometric shapes with pastel palette and clear silhouettes.",
    positive_prefix=(
        "low-poly 3d render, faceted geometric shapes, pastel palette, clean "
        "ambient occlusion, isometric or three-quarter angle"
    ),
    negative_prompt="photorealistic, smooth subdivision, hyper-detail",
    palette=StylePalette(
        background="#11151c", surface="#1c2330",
        primary="#a4d8ff", text_strong="#f3f8ff", text_muted="#9aa9b8",
    ),
    camera_motion="calm",
    default_caption_style="bold_word",
    music_mood="ambient",
    render_notes="Calm explainers, motivational shorts.",
    tags=("animation", "calm"),
))

_register(StylePreset(
    id="claymation",
    name="Claymation",
    description="Stop-motion clay textures, fingerprint detail, warm tungsten lighting.",
    positive_prefix=(
        "claymation stop-motion still, visible thumbprint texture on clay, "
        "tungsten studio lighting, hand-sculpted props"
    ),
    negative_prompt="photorealistic, smooth cgi, anime, comic line art",
    palette=StylePalette(
        background="#1a130d", surface="#28201a",
        primary="#ffb070", text_strong="#fff3e3", text_muted="#b09a86",
    ),
    camera_motion="medium",
    default_caption_style="bold_word",
    music_mood="whimsical",
    render_notes="Whimsical brand stories, kids' stories.",
    tags=("animation",),
))

_register(StylePreset(
    id="papercraft",
    name="Papercraft",
    description="Folded-paper scenes, layered shadows, craft-paper textures.",
    positive_prefix=(
        "papercraft diorama, layered cut paper, soft natural shadows between "
        "layers, crisp folds, craft-paper texture"
    ),
    negative_prompt="photorealistic, anime, cgi gloss, neon",
    palette=StylePalette(
        background="#1d1812", surface="#2a221a",
        primary="#e9c987", text_strong="#fbf1de", text_muted="#a89a7e",
    ),
    camera_motion="calm",
    default_caption_style="minimal_lower_third",
    music_mood="ambient",
    render_notes="Calm story shorts, cozy nighttime narration.",
    tags=("animation", "calm"),
))

# Mood-driven
_register(StylePreset(
    id="dark_horror",
    name="Dark Horror",
    description="Low-key lighting, deep shadows, desaturated palette, unsettling negative space.",
    positive_prefix=(
        "dark horror cinematography, low-key lighting, deep shadows, desaturated "
        "palette, eerie negative space, subtle film grain, fog"
    ),
    negative_prompt="bright daylight, cartoon, kid friendly, neon, anime",
    palette=StylePalette(
        background="#06070a", surface="#10131a",
        primary="#cf2e2e", text_strong="#f4f4f7", text_muted="#7a7e88",
    ),
    camera_motion="medium",
    default_caption_style="impact_uppercase",
    music_mood="horror",
    render_notes="Reddit horror, scary stories, urban legends.",
    tags=("dark", "mature"),
))

_register(StylePreset(
    id="luxury_commercial",
    name="Luxury Commercial",
    description="High-contrast macro studio shots, glossy surfaces, gold accents.",
    positive_prefix=(
        "luxury commercial photography, macro detail, glossy surfaces, polished "
        "metal accents, controlled studio lighting, deep blacks, gold rim light"
    ),
    negative_prompt="cartoon, anime, low-poly, low contrast, snapshot lighting",
    palette=StylePalette(
        background="#08080a", surface="#13131a",
        primary="#d6ad60", text_strong="#fbfbfb", text_muted="#8a8a92",
    ),
    camera_motion="cinematic",
    default_caption_style="minimal_lower_third",
    music_mood="luxurious",
    render_notes="Product teasers, brand reveals, watch ads.",
    tags=("premium", "commercial"),
))

_register(StylePreset(
    id="neon_cyber",
    name="Neon Cyber",
    description="Wet streets, neon signage, retrowave color grading.",
    positive_prefix=(
        "neon cyberpunk city scene, wet streets, glowing pink and cyan signage, "
        "atmospheric haze, anamorphic lens flares, color graded magenta and teal"
    ),
    negative_prompt="daylight, soft pastel, cartoon, low contrast",
    palette=StylePalette(
        background="#06010a", surface="#160b1f",
        primary="#ff3df0", text_strong="#fff2ff", text_muted="#9c8eb3",
    ),
    camera_motion="fast",
    default_caption_style="kinetic_word",
    music_mood="energetic",
    render_notes="AI / tech / future-of-X shorts.",
    tags=("tech", "stylised"),
))

_register(StylePreset(
    id="clean_educational",
    name="Clean Educational",
    description="Bright, neutral palette, clean type, infographic feel.",
    positive_prefix=(
        "clean educational infographic style, neutral palette, gentle gradients, "
        "soft drop shadows, simple geometric shapes, friendly icons"
    ),
    negative_prompt="dark, horror, gritty, neon, photorealistic",
    palette=StylePalette(
        background="#f5f7fb", surface="#ffffff",
        primary="#3b82f6", text_strong="#0f172a", text_muted="#475569",
    ),
    camera_motion="calm",
    default_caption_style="clean_subtitle",
    music_mood="uplifting",
    render_notes="How-to, study, finance-101 shorts.",
    tags=("explainer", "calm"),
))


# ─── Public API ─────────────────────────────────────────────────────────

DEFAULT_STYLE_ID = "photorealistic_cinematic"


def list_presets() -> list[StylePreset]:
    """Return the catalog in registration order."""
    return list(_PRESETS.values())


def get_preset(style_id: str | None) -> StylePreset:
    """Look up a preset by id; falls back to the default when missing."""
    if style_id and style_id in _PRESETS:
        return _PRESETS[style_id]
    return _PRESETS[DEFAULT_STYLE_ID]


def style_ids() -> Iterable[str]:
    return _PRESETS.keys()


def to_catalog_json() -> list[dict]:
    """Serialised view for the /api/styles endpoint."""
    out = []
    for p in _PRESETS.values():
        d = asdict(p)
        # Drop the heavy engine prompts from the public catalog — UI
        # only needs name/description/palette/notes/tags.
        d.pop("positive_prefix", None)
        d.pop("negative_prompt", None)
        out.append(d)
    return out
