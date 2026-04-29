"""Per-template input Pydantic models — worker copy.

Copied (not imported) from ``apps/api/app/schemas/templates.py`` so the
worker stays deployable to a separate machine without needing the api
package on its sys.path. Same precedent as ``worker_runtime/schemas.py``.

A drift test in ``tests/worker/test_render_dispatcher.py`` compares the
JSON Schemas of these models against the api's copies and fails if
they diverge — fix both sides if a field changes.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# Shared field. ``caption_language`` is a BCP-47-ish hint ("en", "es",
# "ar"…) the operator selects in the create form. The worker uses it
# to (a) pick a voice with matching language tag when ``voice_name``
# isn't pinned and (b) tag the burned ASS captions for downstream
# translation hooks. Pure plumbing for now — translation provider
# wires in later without schema changes.
_CAPTION_LANG_PATTERN = r"^[a-z]{2}(-[A-Z]{2})?$"


# ─── Phase 1 ────────────────────────────────────────────────────────────

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


# ─── Phase 2 ────────────────────────────────────────────────────────────

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
