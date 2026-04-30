"""Publishing providers — Platform Phase 1.

Real upload paths to social platforms. Each provider is gated on
credentials being present in env. Without credentials the provider
reports ``configured=False`` and the api refuses to enqueue uploads
for it (UI shows the connect / setup guidance).

Phase 1 ships only YouTube Data API. TikTok / Instagram require app
review with their respective platforms; we'll add them after that
review lands so we never advertise a fake post path.
"""

from apps.worker.publishing.base import (
    PublishingNotConfigured,
    PublishingProviderInfo,
    PublishingRequest,
    PublishingResult,
)
from apps.worker.publishing.provider import (
    UnknownPublisher,
    get_publishing_provider,
    list_publishing_providers,
)

__all__ = [
    "PublishingNotConfigured",
    "PublishingProviderInfo",
    "PublishingRequest",
    "PublishingResult",
    "UnknownPublisher",
    "get_publishing_provider",
    "list_publishing_providers",
]
