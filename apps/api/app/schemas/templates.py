"""Template metadata + per-template input schemas.

Phase 1 ships four templates. Each has:
  - ``template_id``         stable id used in URLs and DB
  - ``name`` / ``description`` user-facing copy
  - ``category`` / ``tags`` filter tags for the gallery
  - ``input_model``         Pydantic class describing the form payload
  - ``has_plan_preview``    True if /api/projects/:id/plan generates
                            a VideoPlan; False for templates that go
                            straight from form to render (Voiceover,
                            Auto-Captions in PR 4 — the cheap path
                            doesn't compose a plan for those).

The registry is the single source of truth — both the catalog
endpoint (/api/templates) and the project-create validator read from
it. New templates added in Phase 2 (Fake Text, Would You Rather,
Split, Twitter, Top 5, Roblox Rant) just append entries here.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ─── Per-template input models ──────────────────────────────────────────

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


class RedditStoryInput(BaseModel):
    """Reddit post (subreddit + title + body) → faceless story video."""
    model_config = ConfigDict(extra="forbid")

    subreddit: str = Field(..., min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=300)
    body: str = Field(..., min_length=10, max_length=8000)
    duration: float = Field(30.0, ge=8.0, le=90.0)
    seed: Optional[int] = None
    voice_name: Optional[str] = None
    caption_style: Optional[str] = "kinetic_word"


class VoiceoverInput(BaseModel):
    """Bring-your-own script + AI voice + optional uploaded background."""
    model_config = ConfigDict(extra="forbid")

    script: str = Field(..., min_length=10, max_length=8000)
    background_color: str = Field("#0b0b0f", pattern=r"^#[0-9a-fA-F]{6}$")
    background_url: Optional[str] = None
    voice_name: Optional[str] = None
    caption_style: str = "bold_word"
    aspect: Literal["9:16", "16:9", "1:1"] = "9:16"


class AutoCaptionsInput(BaseModel):
    """Script-only auto-captions. Phase 1 doesn't ship audio transcription."""
    model_config = ConfigDict(extra="forbid")

    script: str = Field(..., min_length=10, max_length=8000)
    caption_style: str = "bold_word"
    language: str = Field("en", min_length=2, max_length=8)
    aspect: Literal["9:16", "16:9", "1:1"] = "9:16"
    voice_name: Optional[str] = None
    background_color: str = Field("#0b0b0f", pattern=r"^#[0-9a-fA-F]{6}$")


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
                "Script → AI voice → big bold burned captions over a flat "
                "background. Audio-upload + transcription lands in Phase 2."
            ),
            category="captions",
            tags=["captions", "social"],
            has_plan_preview=False,
        ),
        AutoCaptionsInput,
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
