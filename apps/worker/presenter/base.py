"""Base types for presenter / lipsync providers — Platform Phase 1."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable


class PresenterNotAvailable(RuntimeError):
    """Raised when the chosen lipsync provider isn't ready on this host."""

    def __init__(self, provider_id: str, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.provider_id = provider_id
        self.hint = hint


@dataclass
class PresenterRequest:
    """All knobs the user can flip on a presenter render.

    The pipeline is: TTS the script → run lipsync against the avatar →
    optionally apply a news-style lower-third overlay.
    """
    script: str
    avatar_image_url: str
    voice: Optional[str] = None        # edge-tts voice id
    voice_rate: str = "+0%"
    aspect_ratio: str = "9:16"
    headline: Optional[str] = None     # lower-third headline; None = skip
    ticker: Optional[str] = None       # scrolling ticker; None = skip
    extra: dict = field(default_factory=dict)


@dataclass
class PresenterResult:
    """What the provider produces."""
    video_path: Path
    audio_path: Path
    duration_sec: float


@dataclass
class PresenterProviderInfo:
    id: str
    name: str
    installed: bool
    install_hint: str
    error: Optional[str] = None
    cache_path: Optional[str] = None
    description: str = ""
    required_vram_gb: float = 0.0


@runtime_checkable
class PresenterProvider(Protocol):
    @property
    def info(self) -> PresenterProviderInfo: ...  # noqa: E704

    def render(
        self, req: PresenterRequest, work_dir: Path,
    ) -> PresenterResult: ...
