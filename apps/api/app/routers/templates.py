"""Static catalog endpoints — templates, voices, captions, styles, languages.

These are public reads (no auth) since they're build-time configuration.
Served from constants in code (templates registry, edge-tts voice list,
``CAPTION_STYLES`` from the engine, the worker's ``_style_presets``) —
not from the DB.
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.schemas.templates import all_templates_with_schema
from xvideo.prompt_native import CAPTION_STYLES, default_caption_style_for


router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/templates")
def list_templates() -> list[dict]:
    """Catalog of available video templates with their input JSON Schemas."""
    return all_templates_with_schema()


# ─── Voices ─────────────────────────────────────────────────────────────

VoiceCategory = Literal[
    "clear_female",
    "clear_male",
    "dramatic_narrator",
    "horror_narrator",
    "energetic_tiktok",
    "roblox_rant",
    "documentary",
    "calm_explainer",
    "kid_cartoon",
    "luxury_commercial",
]


class VoiceInfo(BaseModel):
    """Catalog entry for a TTS voice.

    ``provider`` is "edge" today; future providers (ElevenLabs, OpenAI,
    Azure direct) plug in via the same shape so the UI stays stable.
    """

    id: str
    name: str
    gender: Literal["female", "male", "neutral"]
    language: str
    category: VoiceCategory
    tone: list[str]              # free-form tags surfaced in UI
    provider: Literal["edge"] = "edge"
    is_default: bool = False
    preview_url: Optional[str] = None


# Curated edge-tts voices grouped by use-case. Each ``id`` is a real
# Microsoft neural voice — preview URLs left None for now (the worker
# can synthesise on demand). Tier-gating will hide / show entries via a
# future ``min_tier`` field.
_VOICES: list[VoiceInfo] = [
    # Clear female — default
    VoiceInfo(id="en-US-AriaNeural",   name="Aria",     gender="female", language="en-US",
              category="clear_female", tone=["clear", "warm"], is_default=True),
    VoiceInfo(id="en-US-JennyNeural",  name="Jenny",    gender="female", language="en-US",
              category="clear_female", tone=["friendly"]),
    VoiceInfo(id="en-GB-LibbyNeural",  name="Libby",    gender="female", language="en-GB",
              category="clear_female", tone=["british", "calm"]),

    # Clear male
    VoiceInfo(id="en-US-GuyNeural",    name="Guy",      gender="male",   language="en-US",
              category="clear_male",   tone=["confident"]),
    VoiceInfo(id="en-US-AndrewNeural", name="Andrew",   gender="male",   language="en-US",
              category="clear_male",   tone=["smooth"]),

    # Dramatic / story narrators
    VoiceInfo(id="en-US-RogerNeural",  name="Roger",    gender="male",   language="en-US",
              category="dramatic_narrator", tone=["dramatic", "deep"]),
    VoiceInfo(id="en-US-DavisNeural",  name="Davis",    gender="male",   language="en-US",
              category="dramatic_narrator", tone=["mature"]),

    # Horror narrator (slower, lower)
    VoiceInfo(id="en-US-EricNeural",   name="Eric",     gender="male",   language="en-US",
              category="horror_narrator",  tone=["dark", "slow"]),
    VoiceInfo(id="en-GB-RyanNeural",   name="Ryan",     gender="male",   language="en-GB",
              category="horror_narrator",  tone=["british", "ominous"]),

    # Energetic / TikTok
    VoiceInfo(id="en-US-AvaNeural",    name="Ava",      gender="female", language="en-US",
              category="energetic_tiktok", tone=["youthful", "punchy"]),
    VoiceInfo(id="en-US-CoraNeural",   name="Cora",     gender="female", language="en-US",
              category="energetic_tiktok", tone=["upbeat"]),

    # Roblox-rant (faster, edgier)
    VoiceInfo(id="en-US-BrandonNeural", name="Brandon",  gender="male",  language="en-US",
              category="roblox_rant",      tone=["fast", "edgy"]),
    VoiceInfo(id="en-US-ChristopherNeural", name="Christopher", gender="male", language="en-US",
              category="roblox_rant",      tone=["hyped"]),

    # Documentary
    VoiceInfo(id="en-US-TonyNeural",   name="Tony",     gender="male",   language="en-US",
              category="documentary",      tone=["documentary", "neutral"]),
    VoiceInfo(id="en-US-NancyNeural",  name="Nancy",    gender="female", language="en-US",
              category="documentary",      tone=["measured"]),

    # Calm explainer
    VoiceInfo(id="en-US-EmmaNeural",   name="Emma",     gender="female", language="en-US",
              category="calm_explainer",   tone=["calm", "warm"]),
    VoiceInfo(id="en-US-JaneNeural",   name="Jane",     gender="female", language="en-US",
              category="calm_explainer",   tone=["soft"]),

    # Kid / cartoon
    VoiceInfo(id="en-US-AnaNeural",    name="Ana",      gender="female", language="en-US",
              category="kid_cartoon",      tone=["kid", "playful"]),

    # Luxury commercial
    VoiceInfo(id="en-GB-SoniaNeural",  name="Sonia",    gender="female", language="en-GB",
              category="luxury_commercial", tone=["british", "premium"]),
    VoiceInfo(id="en-AU-WilliamNeural", name="William", gender="male",   language="en-AU",
              category="luxury_commercial", tone=["smooth", "premium"]),
]


@router.get("/voices", response_model=list[VoiceInfo])
def list_voices() -> list[VoiceInfo]:
    """Return the full voice catalog grouped by category in the order
    UI surfaces would display them."""
    return _VOICES


@router.get("/voices/categories")
def list_voice_categories() -> list[dict]:
    """Slim per-category summary the create-form can render as chips."""
    summary: dict[str, dict] = {}
    for v in _VOICES:
        bucket = summary.setdefault(v.category, {"id": v.category, "voice_ids": []})
        bucket["voice_ids"].append(v.id)
    # Friendly display labels (mirrors ``VoiceCategory`` ordering).
    labels = {
        "clear_female":       "Clear · Female",
        "clear_male":         "Clear · Male",
        "dramatic_narrator":  "Dramatic Narrator",
        "horror_narrator":    "Horror Narrator",
        "energetic_tiktok":   "Energetic / TikTok",
        "roblox_rant":        "Rant / Hype",
        "documentary":        "Documentary",
        "calm_explainer":     "Calm Explainer",
        "kid_cartoon":        "Kid / Cartoon",
        "luxury_commercial":  "Luxury Commercial",
    }
    out: list[dict] = []
    for cat_id, data in summary.items():
        out.append({
            "id": cat_id,
            "label": labels.get(cat_id, cat_id),
            "voice_ids": data["voice_ids"],
        })
    return out


# ─── Caption styles ─────────────────────────────────────────────────────

class CaptionStyleInfo(BaseModel):
    id: str
    default_for_format: dict[str, bool]   # format_name → is_default


_FORMATS = ["shorts_clean", "tiktok_fast", "reels_aesthetic"]


@router.get("/caption-styles", response_model=list[CaptionStyleInfo])
def list_caption_styles() -> list[CaptionStyleInfo]:
    out: list[CaptionStyleInfo] = []
    for style_id in CAPTION_STYLES:
        defaults = {
            fmt: default_caption_style_for(fmt) == style_id
            for fmt in _FORMATS
        }
        out.append(CaptionStyleInfo(id=style_id, default_for_format=defaults))
    return out


# ─── Caption languages ──────────────────────────────────────────────────

class LanguageInfo(BaseModel):
    code: str         # BCP-47-ish (en, es, ar, …)
    name: str         # English label
    native: str       # native script label
    rtl: bool = False


# A pragmatic starter set — covers the markets the SaaS targets in v1.
# Translation provider (DeepL / GoogleMT / on-device) plugs in later
# without changing this list. Captions burn whichever language the
# operator selects; auto_captions transcribes in this language.
_LANGUAGES: list[LanguageInfo] = [
    LanguageInfo(code="en",  name="English",      native="English"),
    LanguageInfo(code="es",  name="Spanish",      native="Español"),
    LanguageInfo(code="fr",  name="French",       native="Français"),
    LanguageInfo(code="de",  name="German",       native="Deutsch"),
    LanguageInfo(code="pt",  name="Portuguese",   native="Português"),
    LanguageInfo(code="it",  name="Italian",      native="Italiano"),
    LanguageInfo(code="nl",  name="Dutch",        native="Nederlands"),
    LanguageInfo(code="pl",  name="Polish",       native="Polski"),
    LanguageInfo(code="tr",  name="Turkish",      native="Türkçe"),
    LanguageInfo(code="ar",  name="Arabic",       native="العربية", rtl=True),
    LanguageInfo(code="he",  name="Hebrew",       native="עברית",   rtl=True),
    LanguageInfo(code="hi",  name="Hindi",        native="हिन्दी"),
    LanguageInfo(code="ur",  name="Urdu",         native="اردو",     rtl=True),
    LanguageInfo(code="bn",  name="Bengali",      native="বাংলা"),
    LanguageInfo(code="id",  name="Indonesian",   native="Bahasa Indonesia"),
    LanguageInfo(code="ms",  name="Malay",        native="Bahasa Melayu"),
    LanguageInfo(code="tl",  name="Filipino",     native="Filipino"),
    LanguageInfo(code="vi",  name="Vietnamese",   native="Tiếng Việt"),
    LanguageInfo(code="th",  name="Thai",         native="ไทย"),
    LanguageInfo(code="ja",  name="Japanese",     native="日本語"),
    LanguageInfo(code="ko",  name="Korean",       native="한국어"),
    LanguageInfo(code="zh",  name="Chinese",      native="中文"),
    LanguageInfo(code="ru",  name="Russian",      native="Русский"),
    LanguageInfo(code="uk",  name="Ukrainian",    native="Українська"),
    LanguageInfo(code="sv",  name="Swedish",      native="Svenska"),
    LanguageInfo(code="da",  name="Danish",       native="Dansk"),
    LanguageInfo(code="no",  name="Norwegian",    native="Norsk"),
    LanguageInfo(code="fi",  name="Finnish",      native="Suomi"),
]


@router.get("/caption-languages", response_model=list[LanguageInfo])
def list_caption_languages() -> list[LanguageInfo]:
    return _LANGUAGES


# ─── Visual style presets ───────────────────────────────────────────────

@router.get("/styles")
def list_styles() -> list[dict]:
    """Visual style presets the create-form can surface as chips.

    Sourced from the worker's ``_style_presets`` so the catalog stays
    in lock-step with what the worker actually understands.
    """
    # Lazy import — keeps the api boot path independent of the
    # worker's optional Pillow import chain when running tests.
    from apps.worker.render_adapters._style_presets import to_catalog_json
    return to_catalog_json()


# ─── Pacing presets ─────────────────────────────────────────────────────

@router.get("/pacing")
def list_pacing_presets() -> list[dict]:
    """Pacing knobs (calm / medium / fast / chaotic / cinematic).

    Adapters that respect pacing (top_five, ai_story, roblox_rant) read
    the resolved profile out of ``_motion.get_pacing``; this endpoint
    just exposes the catalog for the create form.
    """
    from apps.worker.render_adapters._motion import get_pacing, list_pacing
    out: list[dict] = []
    for pid in list_pacing():
        p = get_pacing(pid)
        out.append({
            "id": p.name,
            "label": p.name.title(),
            "zoom_start": p.zoom_start,
            "zoom_end": p.zoom_end,
            "pan_amount": p.pan_amount,
            "hold_seconds": p.hold_seconds,
            "transition_seconds": p.transition_seconds,
        })
    return out
