"""Publishing provider registry — Platform Phase 1."""

from __future__ import annotations

from typing import Callable

from apps.worker.publishing.base import (
    PublishingProvider,
    PublishingProviderInfo,
)
from apps.worker.publishing.youtube import YouTubeProvider


_REGISTRY: dict[str, Callable[[], PublishingProvider]] = {
    "youtube": YouTubeProvider,
}


class UnknownPublisher(KeyError):
    """The api asked for a publisher id we don't have registered."""


def get_publishing_provider(provider_id: str) -> PublishingProvider:
    factory = _REGISTRY.get(provider_id)
    if factory is None:
        raise UnknownPublisher(
            f"unknown publishing provider {provider_id!r}; "
            f"known: {sorted(_REGISTRY)}"
        )
    return factory()


def list_publishing_providers() -> list[PublishingProviderInfo]:
    return [get_publishing_provider(pid).info for pid in _REGISTRY]
