"""Static catalog endpoints — templates, voices, caption styles.

These are public reads (no auth) since they're build-time configuration.
They're served from constants in code (templates registry, edge-tts
voice list, ``CAPTION_STYLES`` from the engine) — not from the DB.
"""

from __future__ import annotations

from typing import Literal

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

class VoiceInfo(BaseModel):
    id: str
    name: str
    gender: Literal["female", "male", "neutral"]
    language: str
    is_default: bool = False


# Phase 1 catalog — the curated edge-tts voices the engine already uses
# under the hood. Future expansion: a fuller library gated by tier.
_VOICES: list[VoiceInfo] = [
    VoiceInfo(id="en-US-AriaNeural",   name="Aria",   gender="female", language="en-US", is_default=True),
    VoiceInfo(id="en-US-JennyNeural",  name="Jenny",  gender="female", language="en-US"),
    VoiceInfo(id="en-US-GuyNeural",    name="Guy",    gender="male",   language="en-US"),
    VoiceInfo(id="en-US-AndrewNeural", name="Andrew", gender="male",   language="en-US"),
]


@router.get("/voices", response_model=list[VoiceInfo])
def list_voices() -> list[VoiceInfo]:
    return _VOICES


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
