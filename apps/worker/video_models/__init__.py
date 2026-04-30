"""Video-model provider abstraction — Platform Phase 1.

Single registry of every text-to-video / image-to-video backend the
worker knows about. Each backend is gated on availability — the
provider class checks that:

  1. its python runtime module is importable
  2. its weight cache is on disk

If either is missing, ``provider.generate()`` raises
:class:`ModelNotAvailable` with a clear hint. There is **no** silent
fallback — the api surfaces "this model isn't installed, here's the
install command" and refuses the render.

Public surface:

  list_providers()           → all known backends + installed flag
  get_provider(model_id)     → one backend (raises if unknown)
  ModelNotAvailable          → user-visible exception
  GenerationRequest          → input dataclass
"""

from apps.worker.video_models.base import (
    GenerationRequest,
    ModelNotAvailable,
    ProviderInfo,
    VideoModelProvider,
)
from apps.worker.video_models.provider import (
    get_provider,
    list_providers,
)

__all__ = [
    "GenerationRequest",
    "ModelNotAvailable",
    "ProviderInfo",
    "VideoModelProvider",
    "get_provider",
    "list_providers",
]
