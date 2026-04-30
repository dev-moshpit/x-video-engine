"""Base types for video-model providers — Platform Phase 1."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable


class ModelNotAvailable(RuntimeError):
    """Raised by ``provider.generate`` when the runtime/weights aren't ready.

    The api translates this to a 503 with the provider's install hint
    so the operator knows exactly what to do. We never silently fall
    back to a different model — different models produce visibly
    different results, and the user picked this one.
    """

    def __init__(self, provider_id: str, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.provider_id = provider_id
        self.hint = hint


@dataclass
class GenerationRequest:
    """All knobs the user can flip on a generation call.

    ``image_url`` is only used by image-to-video providers (e.g. SVD).
    Text-to-video providers ignore it.
    """
    prompt: str
    duration_seconds: float = 4.0
    fps: int = 24
    seed: Optional[int] = None
    aspect_ratio: str = "9:16"     # "9:16" / "1:1" / "16:9"
    image_url: Optional[str] = None
    # Provider-specific knobs land in ``extra`` so the base interface
    # doesn't need to know every diffuser argument.
    extra: dict = field(default_factory=dict)


@dataclass
class ProviderInfo:
    """Static + live status for one provider, returned by /api/video-models.

    ``installed`` is the only field the UI uses to enable/disable the
    selector. ``error`` and ``hint`` populate when ``installed=False``
    so the operator sees exactly what to install.
    """
    id: str
    name: str
    mode: str                       # "text-to-video" / "image-to-video"
    required_vram_gb: float
    installed: bool
    install_hint: str
    error: Optional[str] = None
    cache_path: Optional[str] = None
    description: str = ""


@runtime_checkable
class VideoModelProvider(Protocol):
    """Minimal contract: every provider has ``info`` + ``generate``."""

    @property
    def info(self) -> ProviderInfo: ...  # noqa: E704

    def generate(
        self, req: GenerationRequest, work_dir: Path,
    ) -> Path:
        """Render ``req`` to an mp4 in ``work_dir``. Returns the path.

        Must raise :class:`ModelNotAvailable` if the provider can't
        actually run (missing module, missing weights, no GPU).
        """
        ...
