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
