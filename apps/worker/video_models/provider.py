"""Provider registry — Platform Phase 1.

Single source of truth for "what video-generation backends does the
platform know about?". Adding a new model is one line in
:data:`_REGISTRY` plus a new ``*_provider.py`` module.

The registry holds zero-arg factories so cold imports stay light —
the heavy diffusers / torch imports happen inside the provider's
``generate`` method, never at registry build time.
"""

from __future__ import annotations

from typing import Callable

from apps.worker.video_models.base import (
    ProviderInfo,
    VideoModelProvider,
)
from apps.worker.video_models.cogvideox_provider import CogVideoXProvider
from apps.worker.video_models.hunyuan_video_provider import (
    HunyuanVideoProvider,
)
from apps.worker.video_models.sdxl_parallax_provider import (
    SDXLParallaxProvider,
)
from apps.worker.video_models.svd_provider import SVDProvider
from apps.worker.video_models.wan21_provider import Wan21Provider


_REGISTRY: dict[str, Callable[[], VideoModelProvider]] = {
    "sdxl_parallax": SDXLParallaxProvider,
    "svd": SVDProvider,
    "wan21": Wan21Provider,
    "hunyuan_video": HunyuanVideoProvider,
    "cogvideox": CogVideoXProvider,
}


class UnknownProvider(KeyError):
    """The api asked for a provider id we don't have registered."""


def get_provider(provider_id: str) -> VideoModelProvider:
    """Return a fresh provider instance for ``provider_id``.

    Always builds a new instance — providers are stateless wrappers
    that lazily load their pipelines, so a fresh instance is cheap
    and avoids cross-request state leakage.
    """
    factory = _REGISTRY.get(provider_id)
    if factory is None:
        raise UnknownProvider(
            f"unknown video-model provider {provider_id!r}; "
            f"known: {sorted(_REGISTRY)}"
        )
    return factory()


def list_providers() -> list[ProviderInfo]:
    """Return a ProviderInfo for every registered provider.

    Each entry's ``installed`` reflects what the worker can actually
    do *right now* — not what the system *might* be able to do after
    pip install. The api ships this directly to /api/video-models.
    """
    out: list[ProviderInfo] = []
    for pid in _REGISTRY:
        out.append(get_provider(pid).info)
    return out
