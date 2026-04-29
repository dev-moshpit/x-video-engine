"""Template metadata + per-template input schemas.

Phase 1 shipped four templates (AI Story, Reddit Story, Voiceover,
Auto-Captions). Phase 2 adds six "viral expansion" templates (Fake
Text, Would You Rather, Split, Twitter, Top 5, Roblox Rant).

Each registry entry carries:
  - ``template_id``         stable id used in URLs and DB
  - ``name`` / ``description`` user-facing copy
  - ``category`` / ``tags`` filter tags for the gallery
  - ``input_model``         Pydantic class describing the form payload
  - ``has_plan_preview``    True if /api/projects/:id/plan generates a
                            VideoPlan; False for templates that go
                            straight from form to render.

The registry is the single source of truth — both the catalog endpoint
(/api/templates) and the project-create validator read from it. Worker
keeps a parity copy in ``apps/worker/template_inputs.py`` so it can be
deployed without the api package; a drift test guards the two from
diverging.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# Mirror of the worker's ``_CAPTION_LANG_PATTERN``. Both files validate
# the same shape so the schema-drift test stays green.
_CAPTION_LANG_PATTERN = r"^[a-z]{2}(-[A-Z]{2})?$"


# ─── Phase 1 input models ───────────────────────────────────────────────

class AIStoryInput(BaseModel):
    """Free-form prompt → cinematic 9:16 short with VO + captions + bg."""
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(..., min_length=10, max_length=2000)
    duration: float = Field(20.0, ge=8.0, le=60.0)
    aspect: Literal["9:16", "16:9", "1:1"] = "9:16"
    style: Optional[str] = Field(None, max_length=120)
    seed: Optional[int] = None
    voice_name: Optional[str] = None
    caption_style: Optional[str] = None
    caption_language: Optional[str] = Field(None, pattern=_CAPTION_LANG_PATTERN)
    music_bed: Optional[str] = Field(None, max_length=500)


class RedditStoryInput(BaseModel):
    """Reddit post (subreddit + title + body) → faceless story video."""
    model_config = ConfigDict(extra="forbid")

    subreddit: str = Field(..., min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=300)
    body: str = Field(..., min_length=10, max_length=8000)
    username: Optional[str] = Field(None, max_length=80)
    upvotes: int = Field(1200, ge=0)
    comments: int = Field(180, ge=0)
    duration: float = Field(30.0, ge=8.0, le=90.0)
    seed: Optional[int] = None
    voice_name: Optional[str] = None
    caption_style: Optional[str] = "kinetic_word"
    caption_language: Optional[str] = Field(None, pattern=_CAPTION_LANG_PATTERN)


class VoiceoverInput(BaseModel):
    """Bring-your-own script + AI voice + optional uploaded background."""
    model_config = ConfigDict(extra="forbid")

    script: str = Field(..., min_length=10, max_length=8000)
    background_color: str = Field("#0b0b0f", pattern=r"^#[0-9a-fA-F]{6}$")
    background_url: Optional[str] = None
    voice_name: Optional[str] = None
    caption_style: str = "clean_subtitle"
    caption_language: Optional[str] = Field(None, pattern=_CAPTION_LANG_PATTERN)
    aspect: Literal["9:16", "16:9", "1:1"] = "9:16"


class AutoCaptionsInput(BaseModel):
    """Auto-captions video.

    Phase 1 was script-only. Phase 2 adds optional ``audio_url`` /
    ``video_url`` overrides — when either is set and readable, the
    worker runs faster-whisper transcription against that media instead
    of synthesizing TTS from ``script``. ``script`` is still required so
    the form/JSON schema stays backward-compatible; clients uploading
    media can pass a one-line caption like "(transcribed)" — the worker
    will ignore it and use the upload.
    """
    model_config = ConfigDict(extra="forbid")

    script: str = Field(..., min_length=10, max_length=8000)
    audio_url: Optional[str] = None
    video_url: Optional[str] = None
    caption_style: str = "bold_word"
    # Whisper transcription language (pre-existing). caption_language is
    # the rendered caption language hint and may differ from the
    # transcription language once translation hooks land.
    language: str = Field("en", min_length=2, max_length=8)
    caption_language: Optional[str] = Field(None, pattern=_CAPTION_LANG_PATTERN)
    aspect: Literal["9:16", "16:9", "1:1"] = "9:16"
    voice_name: Optional[str] = None
    background_color: str = Field("#0b0b0f", pattern=r"^#[0-9a-fA-F]{6}$")
    background_url: Optional[str] = None


# ─── Phase 2 input models ───────────────────────────────────────────────

class FakeTextMessage(BaseModel):
    """One bubble in a Fake Text conversation."""
    model_config = ConfigDict(extra="forbid")

    sender: Literal["me", "them"]
    text: str = Field(..., min_length=1, max_length=1000)
    typing_ms: int = Field(800, ge=0, le=10_000)
    hold_ms: int = Field(1500, ge=100, le=15_000)


class FakeTextInput(BaseModel):
    """iOS / WhatsApp / Instagram / Tinder style chat-screen video."""
    model_config = ConfigDict(extra="forbid")

    style: Literal["ios", "whatsapp", "instagram", "tinder"] = "ios"
    theme: Literal["light", "dark"] = "light"
    chat_title: str = Field("Messages", min_length=1, max_length=80)
    messages: list[FakeTextMessage] = Field(..., min_length=1, max_length=40)
    background_color: str = Field("#111827", pattern=r"^#[0-9a-fA-F]{6}$")
    background_url: Optional[str] = None
    avatar_url: Optional[str] = None
    show_timestamps: bool = False
    aspect: Literal["9:16", "16:9", "1:1"] = "9:16"
    narrate: bool = False
    voice_name: Optional[str] = None
    caption_style: Optional[str] = "bold_word"
    caption_language: Optional[str] = Field(None, pattern=_CAPTION_LANG_PATTERN)


class WouldYouRatherInput(BaseModel):
    """Two-option poll video with reveal percentages."""
    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=10, max_length=300)
    option_a: str = Field(..., min_length=1, max_length=200)
    option_b: str = Field(..., min_length=1, max_length=200)
    color_a: str = Field("#1f6feb", pattern=r"^#[0-9a-fA-F]{6}$")
    color_b: str = Field("#dc2626", pattern=r"^#[0-9a-fA-F]{6}$")
    background_url: Optional[str] = None
    timer_seconds: int = Field(5, ge=3, le=15)
    reveal_percent_a: int = Field(50, ge=0, le=100)
    seed: Optional[int] = None
    aspect: Literal["9:16", "16:9", "1:1"] = "9:16"
    voice_name: Optional[str] = None
    # WYR already burns question + both options + a timer on screen.
    # impact_uppercase captions previously rendered on top of the timer
    # and the bottom panel header — default to no captions so panels
    # stay clean. Operators can opt back in via caption_style.
    caption_style: Optional[str] = None
    caption_language: Optional[str] = Field(None, pattern=_CAPTION_LANG_PATTERN)


class SplitVideoInput(BaseModel):
    """Top/bottom or L/R split — main clip + filler underneath."""
    model_config = ConfigDict(extra="forbid")

    layout: Literal["vertical", "horizontal"] = "vertical"
    main_position: Literal["first", "second"] = "first"
    crop_mode: Literal["cover", "contain"] = "cover"
    main_url: Optional[str] = None
    filler_url: Optional[str] = None
    script: str = Field(..., min_length=10, max_length=8000)
    duration: float = Field(30.0, ge=8.0, le=120.0)
    aspect: Literal["9:16", "16:9", "1:1"] = "9:16"
    voice_name: Optional[str] = None
    caption_style: Optional[str] = "bold_word"
    caption_language: Optional[str] = Field(None, pattern=_CAPTION_LANG_PATTERN)
    background_color: str = Field("#0b0b0f", pattern=r"^#[0-9a-fA-F]{6}$")


class TwitterInput(BaseModel):
    """Twitter/X tweet card video — single tweet or thread."""
    model_config = ConfigDict(extra="forbid")

    handle: str = Field(..., min_length=1, max_length=20)
    display_name: str = Field(..., min_length=1, max_length=50)
    text: str = Field(..., min_length=1, max_length=1000)
    thread: list[str] = Field(default_factory=list, max_length=10)
    likes: int = Field(0, ge=0)
    retweets: int = Field(0, ge=0)
    replies: int = Field(0, ge=0)
    views: int = Field(0, ge=0)
    verified: bool = False
    dark_mode: bool = True
    aspect: Literal["9:16", "16:9", "1:1"] = "9:16"
    voice_name: Optional[str] = None
    caption_style: Optional[str] = "bold_word"
    caption_language: Optional[str] = Field(None, pattern=_CAPTION_LANG_PATTERN)
    background_color: str = Field("#0b0b0f", pattern=r"^#[0-9a-fA-F]{6}$")
    background_url: Optional[str] = None


class TopFiveItem(BaseModel):
    """One ranked entry in a Top 5 / countdown video."""
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=140)
    description: Optional[str] = Field(None, max_length=500)


class TopFiveInput(BaseModel):
    """Numbered countdown video — 3 to 10 ranked items."""
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=200)
    items: list[TopFiveItem] = Field(..., min_length=3, max_length=10)
    per_item_seconds: float = Field(4.0, ge=2.0, le=15.0)
    aspect: Literal["9:16", "16:9", "1:1"] = "9:16"
    background_color: str = Field("#0b0b0f", pattern=r"^#[0-9a-fA-F]{6}$")
    background_url: Optional[str] = None
    voice_name: Optional[str] = None
    caption_style: Optional[str] = "impact_uppercase"
    caption_language: Optional[str] = Field(None, pattern=_CAPTION_LANG_PATTERN)


class RobloxRantInput(BaseModel):
    """Fast-paced rant video over a gameplay background."""
    model_config = ConfigDict(extra="forbid")

    script: str = Field(..., min_length=10, max_length=8000)
    background_url: Optional[str] = None
    background_color: str = Field("#0b0b0f", pattern=r"^#[0-9a-fA-F]{6}$")
    speech_rate: str = Field("+15%", pattern=r"^[+\-]\d{1,3}%$")
    aspect: Literal["9:16", "16:9", "1:1"] = "9:16"
    voice_name: Optional[str] = None
    caption_style: str = "impact_uppercase"
    caption_language: Optional[str] = Field(None, pattern=_CAPTION_LANG_PATTERN)


# ─── Registry ───────────────────────────────────────────────────────────

class TemplateMeta(BaseModel):
    """Public catalog entry — what /api/templates returns per template."""
    template_id: str
    name: str
    description: str
    category: str
    tags: list[str]
    has_plan_preview: bool


_REGISTRY: dict[str, tuple[TemplateMeta, type[BaseModel]]] = {
    "ai_story": (
        TemplateMeta(
            template_id="ai_story",
            name="AI Story Video",
            description=(
                "One prompt in, one cinematic 9:16 short out — generated "
                "scene plan, AI voiceover, burned captions, optional music."
            ),
            category="story",
            tags=["AI", "story", "viral", "cinematic"],
            has_plan_preview=True,
        ),
        AIStoryInput,
    ),
    "reddit_story": (
        TemplateMeta(
            template_id="reddit_story",
            name="Reddit Story Video",
            description=(
                "Drop a Reddit post (subreddit + title + body) and we "
                "narrate it dramatically over generated visuals."
            ),
            category="story",
            tags=["story", "reddit", "viral"],
            has_plan_preview=True,
        ),
        RedditStoryInput,
    ),
    "voiceover": (
        TemplateMeta(
            template_id="voiceover",
            name="Voiceover Video",
            description=(
                "Bring your script. We add the AI voice, captions, and a "
                "solid color or uploaded background."
            ),
            category="voiceover",
            tags=["voiceover", "captions"],
            has_plan_preview=False,
        ),
        VoiceoverInput,
    ),
    "auto_captions": (
        TemplateMeta(
            template_id="auto_captions",
            name="Auto-Captions Video",
            description=(
                "Script or uploaded audio/video → big bold burned captions. "
                "Phase 2 transcribes uploads with faster-whisper."
            ),
            category="captions",
            tags=["captions", "social", "transcription"],
            has_plan_preview=False,
        ),
        AutoCaptionsInput,
    ),
    "fake_text": (
        TemplateMeta(
            template_id="fake_text",
            name="Fake Text Conversation",
            description=(
                "iOS / WhatsApp / Instagram / Tinder chat-screen video "
                "with typing animation and optional voice narration."
            ),
            category="viral",
            tags=["chat", "fake-text", "viral"],
            has_plan_preview=False,
        ),
        FakeTextInput,
    ),
    "would_you_rather": (
        TemplateMeta(
            template_id="would_you_rather",
            name="Would You Rather",
            description=(
                "Two-option poll with timer countdown and percentage reveal "
                "— a viral engagement-bait format."
            ),
            category="viral",
            tags=["poll", "engagement", "viral"],
            has_plan_preview=False,
        ),
        WouldYouRatherInput,
    ),
    "split_video": (
        TemplateMeta(
            template_id="split_video",
            name="Split Video",
            description=(
                "Top/bottom or left/right split — main clip with filler "
                "gameplay underneath. Voice + captions overlaid."
            ),
            category="viral",
            tags=["split", "gameplay", "tiktok"],
            has_plan_preview=False,
        ),
        SplitVideoInput,
    ),
    "twitter": (
        TemplateMeta(
            template_id="twitter",
            name="Twitter / X Tweet Video",
            description=(
                "Render a tweet card (single or thread) with realistic "
                "metrics, voiceover, and captions."
            ),
            category="viral",
            tags=["twitter", "tweet", "viral"],
            has_plan_preview=False,
        ),
        TwitterInput,
    ),
    "top_five": (
        TemplateMeta(
            template_id="top_five",
            name="Top 5 / Countdown",
            description=(
                "Numbered countdown video: 3–10 ranked items, one clip per "
                "item with bold overlay, voiceover, and captions."
            ),
            category="viral",
            tags=["countdown", "list", "viral"],
            has_plan_preview=False,
        ),
        TopFiveInput,
    ),
    "roblox_rant": (
        TemplateMeta(
            template_id="roblox_rant",
            name="Roblox Rant",
            description=(
                "Fast-paced rant with bold impact captions over a gameplay "
                "background. Energy turned to 11."
            ),
            category="viral",
            tags=["rant", "gameplay", "tiktok"],
            has_plan_preview=False,
        ),
        RobloxRantInput,
    ),
}


VALID_TEMPLATE_IDS: list[str] = list(_REGISTRY.keys())


def template_meta(template_id: str) -> Optional[TemplateMeta]:
    entry = _REGISTRY.get(template_id)
    return entry[0] if entry else None


def template_input_model(template_id: str) -> Optional[type[BaseModel]]:
    entry = _REGISTRY.get(template_id)
    return entry[1] if entry else None


def all_templates_with_schema() -> list[dict]:
    """Catalog payload for GET /api/templates.

    Each entry is the public meta + the JSON Schema of the input model
    (derived via Pydantic's ``model_json_schema``).
    """
    out: list[dict] = []
    for meta, model in _REGISTRY.values():
        out.append({
            **meta.model_dump(),
            "input_schema": model.model_json_schema(),
        })
    return out


def validate_template_input(template_id: str, payload: dict) -> dict:
    """Validate + canonicalize a template_input dict.

    Returns the dict after Pydantic coercion (defaults filled in,
    types normalized). Raises ``ValueError`` with a readable message on
    unknown template or schema mismatch.
    """
    model = template_input_model(template_id)
    if model is None:
        raise ValueError(
            f"unknown template '{template_id}' — expected one of "
            f"{VALID_TEMPLATE_IDS}"
        )
    try:
        instance = model.model_validate(payload)
    except Exception as e:
        raise ValueError(
            f"invalid input for template '{template_id}': {e}"
        ) from e
    return instance.model_dump()


def template_supports_plan_preview(template_id: str) -> bool:
    meta = template_meta(template_id)
    return bool(meta and meta.has_plan_preview)
