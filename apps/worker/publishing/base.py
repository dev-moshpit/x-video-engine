"""Base types for publishing providers — Platform Phase 1."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


class PublishingNotConfigured(RuntimeError):
    """Raised when the chosen platform's OAuth/API credentials are missing.

    The api translates this to a 503 with the setup hint so the operator
    knows exactly which env vars to set or which OAuth flow to run.
    """

    def __init__(self, provider_id: str, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.provider_id = provider_id
        self.hint = hint


@dataclass
class PublishingRequest:
    """Inputs for a single upload."""
    provider_id: str
    video_url: str            # public mp4 url (R2/MinIO/HTTPS)
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    privacy: str = "private"   # YouTube: private / unlisted / public
    extra: dict = field(default_factory=dict)


@dataclass
class PublishingResult:
    """What a successful upload returns."""
    provider_id: str
    external_id: str           # platform-side id (YouTube videoId, etc.)
    external_url: str          # human-shareable URL
    raw_response: dict = field(default_factory=dict)


@dataclass
class PublishingProviderInfo:
    id: str
    name: str
    configured: bool
    setup_hint: str
    error: Optional[str] = None
    description: str = ""


@runtime_checkable
class PublishingProvider(Protocol):
    @property
    def info(self) -> PublishingProviderInfo: ...  # noqa: E704

    def upload(self, req: PublishingRequest) -> PublishingResult: ...
